"""
API endpoints for recommendations, dialogue, try-on, and marketplace.
"""
import time
import base64
import numpy as np
import cv2
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, List, Any

from ..config import TariConfig
from ..cache.predictive_cache import PredictiveCache
from ..recommendation.engine import PrivacyFirstRecommendationEngine
from ..orchestrator.gateway import XyraGatewayOrchestrator
from ..orchestrator.agents.tryon_agent import TryOnAgent
from ..middleware.security import security
from ..logging.metrics import METRICS

router = APIRouter()

class ConversationRequest(BaseModel):
    user_id: str
    query: str
    context: Dict = Field(default_factory=dict)

class TryOnStatusRequest(BaseModel):
    user_id: str
    job_id: str

# Dependencies
async def get_gateway():
    config = TariConfig()
    cache = PredictiveCache(config)
    from ..privacy.manager import PrivacyManager
    from ..connection_pool import SecureConnectionPool
    privacy = PrivacyManager(config)
    pool = await SecureConnectionPool.get_instance()
    gateway = XyraGatewayOrchestrator(config, cache, privacy, pool)
    return gateway

@router.post("/api/v6/converse")
async def converse(
    req: ConversationRequest,
    gateway: XyraGatewayOrchestrator = Depends(get_gateway),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    METRICS["active_requests"].inc()
    start_time = time.perf_counter()
    try:
        result = await gateway.process(req.user_id, req.query, req.context)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        result["performance"] = {"elapsed_ms": elapsed_ms}
        return result
    except Exception as e:
        METRICS["error_rate"].labels(type=type(e).__name__, severity="high").inc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        METRICS["active_requests"].dec()

@router.get("/api/v6/tryon/status/{job_id}")
async def get_tryon_status(
    job_id: str,
    user_id: str,
    gateway: XyraGatewayOrchestrator = Depends(get_gateway),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    result = await gateway.tryon_agent.get_result(job_id)
    if not result:
        raise HTTPException(status_code=404, detail="Job not found")
    return result

@router.post("/api/v6/tryon/render")
async def render_tryon(
    outfit: Dict,
    user_id: str,
    context: Dict,
    gateway: XyraGatewayOrchestrator = Depends(get_gateway),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    job = await gateway.tryon_agent.queue_tryon(user_id, outfit, context)
    return job

@router.post("/api/v6/feedback")
async def submit_feedback(
    user_id: str,
    interaction_type: str,
    product_id: str,
    rating: Optional[int] = None,
    gateway: XyraGatewayOrchestrator = Depends(get_gateway),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    await gateway.learning_agent.record_interaction(
        user_id, "", {"product_id": product_id}, {"feedback": rating}
    )
    await gateway.memory_service.update_memory(user_id, {
        "type": interaction_type,
        "product_id": product_id,
        "rating": rating
    })
    return {"status": "recorded"}

@router.get("/api/v6/health/detailed")
async def detailed_health(
    gateway: XyraGatewayOrchestrator = Depends(get_gateway),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    return await gateway.health_check()
