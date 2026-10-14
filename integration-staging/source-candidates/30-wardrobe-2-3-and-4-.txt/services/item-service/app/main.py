"""FastAPI application entrypoint."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Query, Request, status
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi.errors import RateLimitExceeded
from sqlalchemy.ext.asyncio import AsyncSession

from common.cache import RedisCache
from common.config import settings
from common.errors import CirvannaError, NotFoundError
from common.events import EventPublisher
from common.logging_config import configure_logging
from common.security import correlation_middleware, current_user, limiter
from common.telemetry import setup_telemetry

from .config import MAX_LIST_LIMIT, SERVICE_NAME
from .db import dispose_engine, get_session
from .models import (
    Base,
    ItemCreate,
    ItemListResponse,
    ItemRow,
    ItemSummary,
    WearRequest,
)
from .repositories import ItemRepository, WearRepository
from .services import ItemService

configure_logging(SERVICE_NAME, settings.log_level, settings.log_format)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .db import get_engine

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await RedisCache.init()
    await EventPublisher.init()
    logger.info("Item service started")
    yield
    await EventPublisher.close()
    await RedisCache.close()
    await dispose_engine()
    logger.info("Item service stopped")


app = FastAPI(
    title="Cirvanna Item Service",
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)
app.state.limiter = limiter
app.middleware("http")(correlation_middleware)
setup_telemetry(app, SERVICE_NAME)
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


@app.exception_handler(RateLimitExceeded)
async def _rl_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(status_code=429, content={"error": "rate_limit_exceeded"})


@app.exception_handler(CirvannaError)
async def _domain_err_handler(request: Request, exc: CirvannaError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


def get_item_service(session: Annotated[AsyncSession, Depends(get_session)]) -> ItemService:
    return ItemService(ItemRepository(session), WearRepository(session))


ItemSvc = Annotated[ItemService, Depends(get_item_service)]
CurrentUser = Annotated[str, Depends(current_user)]


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/ready", include_in_schema=False)
async def ready() -> dict[str, str]:
    return {"status": "ready"}


@app.post("/items", status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
async def create_item(
    request: Request, payload: ItemCreate, svc: ItemSvc, user: CurrentUser
) -> dict:
    domain = await svc.create(payload)
    return domain.to_dict()


@app.get("/items/{item_id}")
async def get_item(item_id: str, svc: ItemSvc, user: CurrentUser) -> dict:
    return (await svc.get(item_id)).to_dict()


@app.get("/items", response_model=ItemListResponse)
async def list_items(
    svc: ItemSvc,
    user: CurrentUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=MAX_LIST_LIMIT),
    category: str | None = None,
) -> ItemListResponse:
    items, total = await svc.list_for_owner(user, skip, limit, category)
    return ItemListResponse(items=items, total=total, skip=skip, limit=limit)


@app.post("/items/{item_id}/wear", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("100/minute")
async def record_wear(
    request: Request, item_id: str, payload: WearRequest, svc: ItemSvc, user: CurrentUser
) -> dict:
    domain = await svc.record_wear(item_id, payload)
    return {"status": "accepted", "total_wears": domain.total_wears}


@app.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def retire_item(item_id: str, svc: ItemSvc, user: CurrentUser) -> None:
    await svc.retire(item_id)


@app.post("/admin/seed")
async def seed_demo(svc: ItemSvc, user: CurrentUser) -> dict:
    """Create 20 demo items for the current user."""
    cats = ["top", "bottom", "outerwear", "footwear", "accessory"]
    created = 0
    for i in range(20):
        await svc.create(
            ItemCreate(
                owner_id=user,
                ingestion_method="manual",
                primary_category=cats[i % len(cats)],
                bootstrap_confidence=0.15,
            )
        )
        created += 1
    return {"created": created}
