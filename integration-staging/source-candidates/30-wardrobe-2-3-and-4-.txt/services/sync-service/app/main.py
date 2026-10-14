from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from common.config import settings
from common.errors import CirvannaError, UpstreamError
from common.logging_config import configure_logging
from common.security import correlation_middleware, current_user
from common.telemetry import setup_telemetry

from .config import ITEM_SERVICE_URL, SERVICE_NAME
from .db import dispose, get_engine, get_session
from .models import Base
from .offline_queue import OfflineQueue

configure_logging(SERVICE_NAME, settings.log_level, settings.log_format)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Sync service ready")
    yield
    await dispose()


app = FastAPI(title="Cirvanna Sync Service", version="3.0.0", lifespan=lifespan)
app.middleware("http")(correlation_middleware)
setup_telemetry(app, SERVICE_NAME)
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


@app.exception_handler(CirvannaError)
async def _err(request: Request, exc: CirvannaError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


class EventPayload(BaseModel):
    event_type: str = Field(min_length=1, max_length=32)
    payload: dict


def get_queue(session: Annotated[AsyncSession, Depends(get_session)]) -> OfflineQueue:
    return OfflineQueue(session)


Queue = Annotated[OfflineQueue, Depends(get_queue)]
CurrentUser = Annotated[str, Depends(current_user)]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}


@app.post("/offline/{user_id}/event", status_code=202)
async def enqueue(user_id: str, ev: EventPayload, queue: Queue, user: CurrentUser) -> dict:
    eid = await queue.enqueue(user_id, ev.event_type, ev.payload)
    await queue.session.commit()
    return {"event_id": eid, "status": "queued"}


@app.get("/offline/{user_id}/stats")
async def stats(user_id: str, queue: Queue, user: CurrentUser) -> dict:
    return await queue.stats(user_id)


@app.post("/replay/{user_id}")
async def replay(user_id: str, queue: Queue, user: CurrentUser) -> dict:
    async def handler(uid: str, etype: str, payload: dict) -> None:
        async with httpx.AsyncClient(timeout=10.0) as c:
            if etype == "wear_event":
                r = await c.post(
                    f"{ITEM_SERVICE_URL}/items/{payload['item_id']}/wear",
                    json={
                        "accepted": payload["accepted"],
                        "duration_minutes": payload["duration_minutes"],
                        "event_type": payload.get("event_type", "wear"),
                    },
                )
            elif etype == "add_item":
                r = await c.post(f"{ITEM_SERVICE_URL}/items", json=payload)
            else:
                logger.warning(f"Unknown offline event type: {etype}")
                return
            r.raise_for_status()

    return await queue.replay(user_id, handler)
