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
    intelligence,
    mf,
    portfolio,
    query,
    simulate,
    stocks,
    system,
)
from backend.routes.system import health as _health_impl
from backend.routes.system import ready as _ready_impl
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
app.include_router(mf.router)
app.include_router(simulate.router)
app.include_router(portfolio.router)
app.include_router(system.router)


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
    import asyncio as _asyncio

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

    log.info("cache_prewarm_done")


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
