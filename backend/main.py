"""ATLAS FastAPI application — Market Intelligence Engine."""

import json
from pathlib import Path
from typing import Any, Callable, cast

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from backend.config import get_settings
from backend.routes import (
    decisions,
    errors as uql_errors,
    global_intel,
    intelligence,
    mf,
    portfolio,
    query,
    simulate,
    stocks,
    system,
    system_probes,
    tv,
    watchlists,
    webhooks,
)
from backend.routes.system_probes import health as _health_impl
from backend.routes.system_probes import ready as _ready_impl
from backend.version import GIT_SHA, VERSION

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
)

settings = get_settings()
log = structlog.get_logger()

ALLOWED_ORIGINS: list[str] = settings.cors_origin_list

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.rate_limit_default],
    strategy="fixed-window",
)

app = FastAPI(
    title="ATLAS — Market Intelligence Engine",
    description="Jhaveri Intelligence Platform — Market → Sector → Stock → Decision",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, cast(Callable[..., Any], _rate_limit_exceeded_handler))
app.add_middleware(SlowAPIMiddleware)

# CORS — explicit allowlist sourced from settings.cors_origins (never "*").
app.add_middleware(
    CORSMiddleware,
    allow_origins=[*ALLOWED_ORIGINS],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)


@app.middleware("http")
async def _enforce_api_rate_limit(request: Request, call_next: Any) -> Any:
    # slowapi middleware already applies default_limits; this hook exists so
    # future per-route overrides on /api/v1/* can attach to request.state.
    return await call_next(request)


uql_errors.register(app)

app.include_router(stocks.router)
app.include_router(query.router)
app.include_router(decisions.router)
app.include_router(intelligence.router)
app.include_router(global_intel.router)
app.include_router(mf.router)
app.include_router(simulate.router)
app.include_router(portfolio.router)
app.include_router(system.router)
app.include_router(system_probes.probes_router)
app.include_router(tv.router)
app.include_router(watchlists.router)
app.include_router(webhooks.router)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {
        "service": "atlas-backend",
        "version": VERSION,
        "git_sha": GIT_SHA,
        "docs": "/docs",
        "health": "/health",
        "ready": "/ready",
    }


# Bare-path aliases for load balancers / systemd / k8s probes that don't
# want to know about the /api/v1 prefix.
app.add_api_route("/health", _health_impl, methods=["GET"], tags=["system"])
app.add_api_route("/ready", _ready_impl, methods=["GET"], tags=["system"])


@app.get("/api/v1/openapi.json", include_in_schema=False)
async def api_v1_openapi() -> JSONResponse:
    return JSONResponse(app.openapi())


@app.get("/api/v1/docs", include_in_schema=False)
async def api_v1_docs() -> HTMLResponse:
    return get_swagger_ui_html(
        openapi_url="/api/v1/openapi.json",
        title="ATLAS — API v1 docs",
    )


@app.on_event("startup")
async def startup() -> None:
    import asyncio as _asyncio

    # Prewarm completion tracking. /ready returns 503 until this is set,
    # so callers (quality gate, systemd, k8s) can block until the first
    # request won't hit a cold JIP aggregate query.
    app.state.prewarm_done = _asyncio.Event()

    try:
        spec_path = Path(__file__).resolve().parent / "openapi.json"
        spec_path.write_text(json.dumps(app.openapi(), indent=2))
    except OSError as exc:
        log.warning("openapi_export_failed", error=str(exc))

    log.info(
        "atlas_starting",
        port=settings.atlas_api_port,
        cors_origins=ALLOWED_ORIGINS,
        rate_limit=settings.rate_limit_default,
        version=VERSION,
        git_sha=GIT_SHA,
    )

    # Start in-process auto-loop scheduler for V3-7
    try:
        from backend.db.session import async_session_factory
        from backend.services.simulation.scheduler import scheduler as sim_scheduler

        sim_scheduler.start(async_session_factory)
        log.info("simulation_scheduler_started")
    except Exception as exc:
        log.warning("simulation_scheduler_start_failed", error=str(exc))

    # Cache pre-warming: kick off the heavy aggregate queries on a
    # background task so the first user request hits a populated cache
    # instead of a cold 200-second JIP query that would 504 via nginx.
    # Errors are logged but never block startup.
    _asyncio.create_task(_prewarm_caches())


async def _prewarm_caches() -> None:
    """Fire-and-forget warm-up of equity + MF aggregate caches at boot.

    Each step runs in its own session so a timeout in one cannot poison the
    rest, and each session relaxes statement_timeout to 60s so the slow cold
    queries can complete and populate the cache. User-facing requests still
    use the default 15s ceiling — only this one-shot warmup is allowed to
    take longer.
    """
    from sqlalchemy import text as _text
    from sqlalchemy.exc import SQLAlchemyError

    from backend.clients.jip_data_service import JIPDataService
    from backend.db.session import async_session_factory

    log.info("cache_prewarm_start")

    async def _warm(label: str, fn_name: str, *args: Any, **kwargs: Any) -> None:
        try:
            async with async_session_factory() as session:
                # Relax statement_timeout to 180s for this prewarm session
                # (default is 15s). 180s is required because some MF
                # aggregate queries do double DISTINCT ON over de_rs_scores
                # without a covering index on the JIP side; remove once
                # JIP ships ix_de_rs_scores_entity_type_id_date.
                await session.execute(_text("SET statement_timeout = '180000'"))
                try:
                    svc = JIPDataService(session)
                    target = getattr(svc, fn_name, None) or getattr(svc._mf, fn_name)
                    await target(*args, **kwargs)
                    log.info(f"cache_prewarm_{label}_ok")
                finally:
                    try:
                        await session.execute(_text("SET statement_timeout = '15000'"))
                    except SQLAlchemyError:
                        pass
        except SQLAlchemyError as exc:
            log.warning(f"cache_prewarm_{label}_failed", error=str(exc)[:300])

    # Sequential, not parallel. Empirically, parallel prewarm caused JIP
    # contention that made the equity query 25× slower (3s → 76s). Sequential
    # gives equity 3s, universe 17s, categories instant. rs_momentum is
    # deliberately NOT prewarmed here — it requires a JIP-side index that
    # doesn't exist yet, so atlas-side warming is futile. Routes that depend
    # on rs_momentum already wrap the call in a try/except and degrade
    # gracefully (quadrant=None) if the query fails.
    await _warm("equity", "get_equity_universe", benchmark="NIFTY 500")
    await _warm("mf_universe", "get_mf_universe", active_only=True)
    await _warm("mf_categories", "get_mf_categories")
    # get_mf_data_freshness() runs on the universe + deep-dive hot path but
    # was previously unwarmed — cold-first-request caught a 300–800ms JIP
    # freshness query that tipped deep-dive over its 500ms budget (v2-09).
    await _warm("mf_freshness", "get_mf_data_freshness")

    # Warm one representative stock deep-dive and one MF deep-dive so the
    # first real /stocks/{symbol} and /mf/{mstar_id} hit hot PG shared
    # buffers for the big JOIN path. Subsequent calls to OTHER symbols/funds
    # also benefit — the expensive tables (de_equity_technical_daily,
    # de_mf_derived_daily, etc.) are paged in once and shared across
    # queries. Without this, the first end-user request sees a 5–7s cold
    # query that blows past the 500ms deep-dive latency budget.
    await _warm_stock_detail()
    await _warm_mf_deep_dive()

    # Seed the rs_momentum_batch negative cache. JIP lacks a covering
    # index on de_rs_scores(entity_type, entity_id, date), so the query
    # reliably hits statement_timeout. The client has a negative-cache
    # path that returns {} instantly on subsequent calls — but only once
    # it has seen one failure. Without this warmup, the FIRST user hitting
    # /mf/universe burns 15s on that timeout before getting an answer.
    # Calling it here swallows the 15s hit at deploy time instead.
    await _warm_rs_momentum_negative_cache()

    log.info("cache_prewarm_done")
    # Signal readiness — /ready flips to 200 only now.
    try:
        app.state.prewarm_done.set()
    except Exception as exc:
        log.warning("prewarm_done_signal_failed", error=str(exc))


async def _warm_stock_detail() -> None:
    """Warm PG buffers for the equity deep-dive JOIN path.

    Uses a nifty_50 symbol (RELIANCE) that is guaranteed to exist. Errors
    are swallowed — this is a cold-path warmup, not a correctness check.
    """
    from sqlalchemy import text as _text
    from sqlalchemy.exc import SQLAlchemyError

    from backend.clients.jip_data_service import JIPDataService
    from backend.db.session import async_session_factory

    try:
        async with async_session_factory() as session:
            await session.execute(_text("SET statement_timeout = '60000'"))
            svc = JIPDataService(session)
            await svc.get_stock_detail("RELIANCE")
            log.info("cache_prewarm_stock_detail_ok")
    except (SQLAlchemyError, AttributeError) as exc:
        log.warning("cache_prewarm_stock_detail_failed", error=str(exc)[:200])


async def _warm_rs_momentum_negative_cache() -> None:
    """Trigger the rs_momentum_batch client so its negative cache populates.

    The call is expected to raise (JIP-side statement_timeout), which the
    client catches and records in `_mf_rs_momentum_last_failure`. That
    stamp makes subsequent calls return {} instantly for 60s — long
    enough for any reasonable burst of /mf/universe traffic right after
    deploy. If JIP later ships the missing index, this warmup will
    succeed and the positive cache populates instead — either way, the
    first user request no longer blocks on a 15s timeout.
    """
    from sqlalchemy.exc import SQLAlchemyError

    from backend.clients.jip_data_service import JIPDataService
    from backend.db.session import async_session_factory

    try:
        async with async_session_factory() as session:
            svc = JIPDataService(session)
            try:
                await svc._mf.get_mf_rs_momentum_batch()
                log.info("cache_prewarm_rs_momentum_ok")
            except (SQLAlchemyError, RuntimeError) as inner:
                log.info(
                    "cache_prewarm_rs_momentum_negative_cached",
                    reason=str(inner)[:200],
                )
            try:
                await session.rollback()
            except SQLAlchemyError:
                pass
    except SQLAlchemyError as exc:
        log.warning("cache_prewarm_rs_momentum_session_failed", error=str(exc)[:200])


async def _warm_mf_deep_dive() -> None:
    """Warm PG buffers for the MF deep-dive JOIN path.

    Picks the first mstar_id from the already-cached universe result so
    we don't hard-code a specific fund that might be delisted. No-op if
    the universe cache is empty (universe prewarm failed upstream).
    """
    from sqlalchemy import text as _text
    from sqlalchemy.exc import SQLAlchemyError

    from backend.clients.jip_data_service import JIPDataService
    from backend.db.session import async_session_factory

    try:
        async with async_session_factory() as session:
            await session.execute(_text("SET statement_timeout = '60000'"))
            svc = JIPDataService(session)
            universe = await svc.get_mf_universe(active_only=True)
            if not universe:
                log.info("cache_prewarm_mf_deep_dive_skip", reason="empty_universe")
                return
            mstar_id = universe[0].get("mstar_id")
            if not mstar_id:
                log.info("cache_prewarm_mf_deep_dive_skip", reason="no_mstar_id")
                return
            await svc.get_fund_detail(mstar_id)
            log.info("cache_prewarm_mf_deep_dive_ok", mstar_id=mstar_id)
    except (SQLAlchemyError, AttributeError) as exc:
        log.warning("cache_prewarm_mf_deep_dive_failed", error=str(exc)[:200])


@app.on_event("shutdown")
async def shutdown() -> None:
    log.info("atlas_shutting_down")

    # Stop the simulation scheduler cleanly
    try:
        from backend.services.simulation.scheduler import scheduler as sim_scheduler

        await sim_scheduler.stop()
        log.info("simulation_scheduler_stopped")
    except Exception as exc:
        log.warning("simulation_scheduler_stop_failed", error=str(exc))
