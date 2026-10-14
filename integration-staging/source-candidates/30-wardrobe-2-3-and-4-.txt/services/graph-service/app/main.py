from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from common.config import settings
from common.errors import CirvannaError
from common.events import EventConsumer
from common.logging_config import configure_logging
from common.security import correlation_middleware, current_user
from common.telemetry import setup_telemetry

from .config import DEFAULT_LIMIT, DEFAULT_MIN_CONFIDENCE, EDGE_PRUNE_THRESHOLD, SERVICE_NAME
from .repository import GraphRepository
from .seeder import GraphSeeder

configure_logging(SERVICE_NAME, settings.log_level, settings.log_format)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    repo = GraphRepository()
    await repo.verify_connectivity()
    await repo.ensure_constraints()
    seeder = GraphSeeder(repo)
    app.state.repo = repo
    app.state.seeder = seeder

    async def on_event(routing_key: str, data: dict) -> None:
        if routing_key.startswith(("item.created", "wear.recorded")):
            await seeder.update_for_item(data["item_id"])

    conn = await EventConsumer.subscribe(
        "graph-service.queue",
        ["item.created", "wear.recorded"],
        on_event,
    )
    app.state.consumer_conn = conn
    logger.info("Graph service ready")
    yield
    await conn.close()
    await repo.close()


app = FastAPI(title="Cirvanna Graph Service", version="3.0.0", lifespan=lifespan)
app.middleware("http")(correlation_middleware)
setup_telemetry(app, SERVICE_NAME)
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


@app.exception_handler(CirvannaError)
async def _err(request: Request, exc: CirvannaError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


def get_repo() -> GraphRepository:
    return app.state.repo


Repo = Annotated[GraphRepository, Depends(get_repo)]
CurrentUser = Annotated[str, Depends(current_user)]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/compatible/{item_id}")
async def compatible(
    item_id: str,
    repo: Repo,
    user: CurrentUser,
    min_confidence: float = Query(DEFAULT_MIN_CONFIDENCE, ge=0.0, le=1.0),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=100),
) -> dict:
    return {"items": await repo.get_compatible(item_id, min_confidence, limit)}


@app.get("/stats")
async def stats(repo: Repo, user: CurrentUser) -> dict:
    return await repo.stats()


@app.post("/maintenance/decay")
async def decay(repo: Repo, user: CurrentUser, days: int = Query(7, ge=1, le=365)) -> dict:
    removed = await repo.decay_and_prune(days, EDGE_PRUNE_THRESHOLD)
    return {"removed": removed}
