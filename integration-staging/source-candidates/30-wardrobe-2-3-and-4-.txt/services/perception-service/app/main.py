from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from common.config import settings
from common.logging_config import configure_logging
from common.security import correlation_middleware, current_user
from common.telemetry import setup_telemetry

from .config import SERVICE_NAME
from .tasks import analyze_image

configure_logging(SERVICE_NAME, settings.log_level, settings.log_format)

app = FastAPI(title="Cirvanna Perception Service", version="3.0.0")
app.middleware("http")(correlation_middleware)
setup_telemetry(app, SERVICE_NAME)
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

CurrentUser = Annotated[str, Depends(current_user)]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}


@app.post("/analyze")
async def analyze(
    item_id: str, image_url: str, user: CurrentUser, category_hint: str | None = None
) -> dict:
    task = analyze_image.delay(item_id, image_url, category_hint)
    return {"job_id": task.id, "status": "queued"}
