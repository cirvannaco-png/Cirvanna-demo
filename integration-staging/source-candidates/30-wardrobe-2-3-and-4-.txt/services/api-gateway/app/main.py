from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from prometheus_fastapi_instrumentator import Instrumentator

from common.cache import RedisCache
from common.config import settings
from common.errors import CirvannaError, CircuitOpenError, UpstreamError
from common.logging_config import configure_logging
from common.security import correlation_middleware
from common.telemetry import setup_telemetry

from .circuit_breaker import SlidingCircuitBreaker
from .config import CB_FAILURE_THRESHOLD, CB_INITIAL_RATIO, CB_RECOVERY_TIMEOUT, ROUTES, SERVICE_NAME
from .rate_limiter import EndpointRateLimiter

configure_logging(SERVICE_NAME, settings.log_level, settings.log_format)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await RedisCache.init()
    app.state.breakers = {
        name: SlidingCircuitBreaker(
            name=name,
            failure_threshold=CB_FAILURE_THRESHOLD,
            recovery_timeout=CB_RECOVERY_TIMEOUT,
            initial_ratio=CB_INITIAL_RATIO,
        )
        for name in ROUTES
    }
    app.state.client = httpx.AsyncClient(timeout=30.0)
    logger.info("API gateway ready")
    yield
    await app.state.client.aclose()
    await RedisCache.close()


app = FastAPI(title="Cirvanna API Gateway", version="3.0.0", lifespan=lifespan)
app.middleware("http")(correlation_middleware)
setup_telemetry(app, SERVICE_NAME)
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


@app.exception_handler(CirvannaError)
async def _err(request: Request, exc: CirvannaError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.get("/health")
async def health(request: Request) -> dict:
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "breakers": {n: b.snapshot() for n, b in request.app.state.breakers.items()},
    }


@app.get("/auth/dev")
async def dev_token(user_id: str = "dev_user") -> dict:
    """Development-only token issuer. Remove/disable in production."""
    from common.security import issue_token

    if settings.is_production:
        raise CircuitOpenError("Not available in production")
    return {"token": issue_token(user_id)}


@app.api_route(
    "/{service}/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def proxy(request: Request, service: str, path: str) -> Respo
