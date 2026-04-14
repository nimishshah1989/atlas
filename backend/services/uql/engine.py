"""UQL engine dispatcher — orchestrates safety → optimize → execute → compose.

Pure dispatcher: every translator, safety check, include resolver, and
``_meta`` builder lives in a sibling module. ``execute`` is the single
seam between the FastAPI route layer and the SQL pipeline; everything
that touches a request body flows through here.

Five guarantees ``execute`` enforces, in order:

1. ``entity_type`` resolves against :data:`registry.REGISTRY` or raises
   :class:`UQLError(INVALID_ENTITY_TYPE)`.
2. Payload limits (filter / aggregation / limit ceilings, snapshot
   ``fields`` rule) and full-scan rejection run BEFORE any SQL is built.
3. Mode dispatch picks exactly one optimizer:
   ``translate_timeseries`` (timeseries), ``translate_aggregation``
   (``group_by`` set), or ``translate_snapshot`` (default).
4. After the base query runs, ``include`` modules attach via
   ``includes.resolve``, batched one statement per module so the FR-022
   N+1 ceiling holds.
5. ``data_as_of`` is resolved from the JIP freshness API; a missing
   partition raises :class:`UQLError(ENTITY_PARTITION_MISSING, 503)`
   per FR-019.

Every dispatch path — success, validation rejection, downstream error —
emits exactly one ``uql.execute`` structured log event with the FR-015
field set (``entity_type``, ``mode``, ``filter_count``, ``agg_count``,
``query_ms``, ``record_count``, ``dispatch``, ``status``). The
``dispatch`` field carries the template name for ``execute_template``
calls and ``"raw"`` otherwise so log scrapers can tell the two apart
(FR-015 explicit requirement).

Wired in V2-UQL-AGG-13 per ``specs/004-uql-aggregations/tasks.md`` (T010,
T014, T018, T037).
"""

from __future__ import annotations

from time import perf_counter
from typing import Any, Mapping, Optional, Protocol, Sequence

import structlog

from backend.models.schemas import (
    ResponseMeta,
    UQLRequest,
    UQLResponse,
)
from backend.services.uql import includes, meta, safety, templates
from backend.services.uql.errors import (
    ENTITY_PARTITION_MISSING,
    INVALID_ENTITY_TYPE,
    UQLError,
)
from backend.services.uql.optimizer import (
    SQLPlan,
    translate_aggregation,
    translate_snapshot,
)
from backend.services.uql.registry import REGISTRY, EntityDef
from backend.services.uql.timeseries import translate_timeseries

__all__ = ["execute", "execute_template", "build_from_legacy", "JipPort"]

log = structlog.get_logger()


class JipPort(Protocol):
    """Minimal JIP surface the engine depends on.

    Production wiring uses :class:`backend.clients.jip_data_service.JIPDataService`;
    unit tests pass a dataclass that records calls and returns canned
    rows. Keeping the contract narrow here means engine tests do not
    drag the whole JIP service graph into ``tests/unit``.
    """

    async def execute_sql_plan(self, plan: SQLPlan) -> tuple[list[dict[str, Any]], int]: ...

    async def get_data_freshness(self) -> dict[str, Any]: ...


def _resolve_entity(entity_type: str) -> EntityDef:
    try:
        return REGISTRY[entity_type]
    except KeyError:
        raise UQLError(
            INVALID_ENTITY_TYPE,
            f"Unsupported entity_type '{entity_type}'",
            f"Use one of: {sorted(REGISTRY)}.",
        ) from None


def _classify_mode(request: UQLRequest) -> str:
    if request.mode == "timeseries":
        return "timeseries"
    if request.group_by:
        return "aggregation"
    return "snapshot"


def _translate(request: UQLRequest, entity_def: EntityDef, mode: str) -> SQLPlan:
    if mode == "timeseries":
        return translate_timeseries(request, entity_def)
    if mode == "aggregation":
        return translate_aggregation(request, entity_def)
    return translate_snapshot(request, entity_def)


def _make_fetcher(jip: JipPort) -> includes.SqlFetcher:
    async def _fetch(sql: str, params: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
        rows, _ = await jip.execute_sql_plan(SQLPlan(sql=sql, params=dict(params)))
        return rows

    return _fetch


def _attach_includes(
    rows: list[dict[str, Any]],
    payloads: dict[str, dict[str, dict[str, Any]]],
    pk_field: str,
) -> None:
    for row in rows:
        pk_value = row.get(pk_field)
        if pk_value is None:
            continue
        per_id = payloads.get(str(pk_value), {})
        for module_name, module_payload in per_id.items():
            if module_name == "identity":
                continue
            row[module_name] = module_payload


async def _resolve_and_attach_includes(
    request: UQLRequest,
    entity_def: EntityDef,
    rows: list[dict[str, Any]],
    jip: JipPort,
) -> Optional[list[str]]:
    if not request.include:
        return None
    pk_field = entity_def.primary_key
    ids = [str(row[pk_field]) for row in rows if row.get(pk_field) is not None]
    fetcher = _make_fetcher(jip)
    payloads = await includes.resolve(ids, request.include, fetcher)
    _attach_includes(rows, payloads, pk_field)
    if ids:
        return list(payloads[ids[0]].keys())
    return includes.validate_modules(request.include)


async def _dispatch(request: UQLRequest, *, jip: JipPort, dispatch: str) -> UQLResponse:
    """Run a fully-validated request and emit exactly one ``uql.execute`` log.

    The log event fires from a single ``finally`` block so success,
    validation rejection, and downstream errors all leave the same
    breadcrumb shape (FR-015). ``dispatch`` is the template name for
    template calls and ``"raw"`` for direct ``execute`` callers.
    """

    started = perf_counter()
    log_fields: dict[str, Any] = {
        "entity_type": request.entity_type,
        "mode": _classify_mode(request),
        "filter_count": len(request.filters),
        "agg_count": len(request.aggregations),
        "query_ms": 0,
        "record_count": 0,
        "dispatch": dispatch,
        "status": "ok",
    }
    try:
        entity_def = _resolve_entity(request.entity_type)
        safety.validate_limits(request)
        safety.validate_full_scan(request, entity_def)

        plan = _translate(request, entity_def, log_fields["mode"])
        rows, total_count = await jip.execute_sql_plan(plan)

        includes_loaded = await _resolve_and_attach_includes(request, entity_def, rows, jip)

        data_as_of = await meta.resolve_data_as_of(jip, request.entity_type)
        if data_as_of is None:
            raise UQLError(
                ENTITY_PARTITION_MISSING,
                f"No loaded partition for entity '{request.entity_type}'",
                "Wait for the next pipeline run or pick an entity with loaded data.",
            )

        query_ms = int((perf_counter() - started) * 1000)
        log_fields["query_ms"] = query_ms
        log_fields["record_count"] = len(rows)

        response_meta: ResponseMeta = meta.build_meta(
            request,
            rows,
            total_count,
            query_ms,
            data_as_of,
            includes_loaded,
        )
        return UQLResponse(records=rows, total=total_count, meta=response_meta)
    except UQLError as exc:
        log_fields["status"] = "error"
        log_fields["error_code"] = exc.code
        raise
    except Exception as exc:  # pragma: no cover - defensive
        log_fields["status"] = "error"
        log_fields["error_code"] = type(exc).__name__
        raise
    finally:
        log_fields["query_ms"] = int((perf_counter() - started) * 1000)
        log.info("uql.execute", **log_fields)


async def execute(request: UQLRequest, *, jip: JipPort) -> UQLResponse:
    """Execute a raw :class:`UQLRequest` end-to-end.

    See module docstring for the five enforced guarantees and the FR-015
    log contract. Callers in ``backend/routes/`` build a
    :class:`UQLRequest` from the JSON body and pass the request-scoped
    JIP service via ``jip``; the engine returns a fully-shaped
    :class:`UQLResponse`.
    """

    return await _dispatch(request, jip=jip, dispatch="raw")


async def execute_template(
    name: str, params: Optional[dict[str, Any]], *, jip: JipPort
) -> UQLResponse:
    """Resolve a named template and run it through :func:`execute`.

    Unknown names surface as :class:`UQLError(TEMPLATE_NOT_FOUND, 404)`
    via :func:`templates.get_template`; missing required params surface
    as :class:`UQLError(TEMPLATE_PARAM_MISSING)` from the builder. The
    log event carries the template name in ``dispatch`` so FR-015
    "raw vs template" is observable from a single field.
    """

    builder = templates.get_template(name)
    request = builder(params or {})
    return await _dispatch(request, jip=jip, dispatch=name)


def build_from_legacy(endpoint_id: str, params: dict[str, Any]) -> UQLRequest:
    """Translate a legacy fixed-endpoint call into a :class:`UQLRequest`.

    Stub — wired in V2-UQL-AGG-15 / V2-UQL-AGG-16 when the stocks and mf
    handlers are transpiled to thin shims over the engine.
    """

    raise NotImplementedError("uql.engine.build_from_legacy is wired in V2-UQL-AGG-15/16")
