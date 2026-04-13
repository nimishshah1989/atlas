"""ATLAS FastAPI application — Market Intelligence Engine."""

import json
from pathlib import Path
from typing import Any, Callable, cast

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from backend.config import get_settings
from backend.routes import decisions, intelligence, query, stocks, system
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


app.include_router(stocks.router)
app.include_router(query.router)
app.include_router(decisions.router)
app.include_router(intelligence.router)
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


@app.on_event("shutdown")
async def shutdown() -> None:
    log.info("atlas_shutting_down")
