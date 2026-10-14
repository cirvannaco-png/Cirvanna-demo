from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from common.cache import RedisCache
from common.config import settings
from common.errors import CirvannaError, UpstreamError
from common.logging_config import configure_logging
from common.security import correlation_middleware, current_user
from common.telemetry import setup_telemetry

from .config import GRAPH_SERVICE_URL, ITEM_SERVICE_URL, SERVICE_NAME, SUGGESTION_CACHE_TTL
from .imperfection_engine import ImperfectionEngine
from .scoring import compute_outfit_scores
from .vector_client import VectorClient

configure_logging(SERVICE_NAME, settings.log_level, settings.log_format)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await RedisCache.init()
    vc = VectorClient()
    await vc.ensure_collection()
    app.state.vectors = vc
    app.state.imperfection = ImperfectionEngine()
    logger.info("Recommendation service ready")
    yield
    await vc.close()
    await RedisCache.close()


app = FastAPI(title="Cirvanna Recommendation Service", version="3.0.0", lifespan=lifespan)
app.middleware("http")(correlation_middleware)
setup_telemetry(app, SERVICE_NAME)
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


@app.exception_handler(CirvannaError)
async def _err(request: Request, exc: CirvannaError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


CurrentUser = Annotated[str, Depends(current_user)]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/suggestions/{item_id}")
async def suggestions(
    item_id: str,
    user: CurrentUser,
    exploration: bool = Query(False),
    limit: int = Query(5, ge=1, le=50),
) -> dict:
    cache_key = f"rec:sugg:{item_id}:{exploration}:{limit}"
    cached = await RedisCache.get_json(cache_key)
    if cached:
        return cached

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                f"{GRAPH_SERVICE_URL}/compatible/{item_id}",
                params={"min_confidence": 0.2 if exploration else 0.3, "limit": limit * 2},
            )
            r.raise_for_status()
            graph_items = r.json()["items"]
    except httpx.HTTPError as exc:
        raise UpstreamError(f"Graph service error: {exc}")

    response = {
        "item_id": item_id,
        "suggestions": [
            {
                "item_id": g["id"],
                "compatibility": g["weight"],
                "confidence": g["confidence"],
                "reason": "graph_compatible",
            }
            for g in graph_items[:limit]
        ],
    }
    await RedisCache.set_json(cache_key, response, ttl=SUGGESTION_CACHE_TTL)
    return response


@app.post("/evaluate/{item1_id}/{item2_id}")
async def evaluate(item1_id: str, item2_id: str, user: CurrentUser) -> dict:
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r1 = await client.get(f"{ITEM_SERVICE_URL}/items/{item1_id}")
            r2 = await client.get(f"{ITEM_SERVICE_URL}/items/{item2_id}")
    except httpx.HTTPError as exc:
        raise UpstreamError(f"Item service error: {exc}")

    if r1.status_code != 200 or r2.status_code != 200:
        raise HTTPException(404, "Item not found")

    raw = compute_outfit_scores(r1.json(), r2.json())
    final, meta = app.state.imperfection.process(raw)
    return {"scores": final, "meta": meta}
