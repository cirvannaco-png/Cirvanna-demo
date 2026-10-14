"""
FastAPI application for CDIC v4.0
"""

import os
from typing import Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from .config import CDICConfig
from .models import DecisionContext, CDICResponse
from .engine import CDICEngine


def create_app(config: Optional[CDICConfig] = None) -> FastAPI:
    """Create FastAPI application with CDIC engine"""
    if config is None:
        config = CDICConfig(
            secret_key=os.environ["CDIC_SECRET_KEY"],
            redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        )
    
    app = FastAPI(
        title="CDIC Decision Engine",
        version="4.0.0",
        docs_url="/docs" if config.log_level == "DEBUG" else None,
        redoc_url="/redoc" if config.log_level == "DEBUG" else None
    )
    
    # Add middleware
    if config.enable_compression:
        app.add_middleware(GZipMiddleware, minimum_size=1000)
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=config.trusted_hosts
    )
    
    # Create engine instance
    engine = CDICEngine(config)
    
    # Dependency
    def get_engine() -> CDICEngine:
        return engine
    
    # Rate limiting middleware
    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        client_ip = request.client.host
        path = request.url.path
        
        # Simple rate limiting
        try:
            rate_key = f"rate:{client_ip}:{path}"
            current = int(engine.distributed_lock.redis.incr(rate_key))
            engine.distributed_lock.redis.expire(rate_key, 60)
            
            if current > config.rate_limit_requests:
                return JSONResponse(
                    status_code=429,
                    content={"error": "Rate limit exceeded"}
                )
        except Exception:
            # If Redis fails, continue without rate limiting
            pass
        
        response = await call_next(request)
        return response
    
    # Routes
    @app.post("/v1/decide", response_model=CDICResponse)
    async def decide(
        context: DecisionContext,
        background_tasks: BackgroundTasks,
        engine: CDICEngine = Depends(get_engine)
    ):
        """Make a decision - CDIC only provides options, not final decisions"""
        try:
            result = engine.process_decision(context, {})
            
            # Background logging
            background_tasks.add_task(
                engine._log_audit,
                "api_decision",
                {
                    "request_id": context.request_id,
                    "user_id": context.user_id,
                    "intent": context.intent,
                    "success": True,
                    "clarification_needed": result.clarification_needed
                }
            )
            
            return result
        
        except Exception as e:
            engine.logger.error("api_decision_failed", error=str(e))
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/v1/metrics")
    async def metrics(engine: CDICEngine = Depends(get_engine)):
        """Get metrics"""
        if config.enable_prometheus:
            return Response(
                content=generate_latest(),
                media_type=CONTENT_TYPE_LATEST
            )
        else:
            return engine.get_metrics()
    
    @app.get("/health")
    async def health():
        """Health check"""
        return {
            "status": "healthy",
            "version": "4.0.0",
            "timestamp": datetime.utcnow().isoformat()
        }
    
    @app.get("/ready")
    async def ready(engine: CDICEngine = Depends(get_engine)):
        """Readiness check"""
        try:
            # Check Redis connection
            engine.distributed_lock.redis.ping()
            return {
                "status": "ready",
                "services": ["redis", "engine"],
                "clarification_budget_config": config.clarification_budget_per_session
            }
        except Exception as e:
            raise HTTPException(status_code=503, detail=str(e))
    
    @app.get("/v1/clarification/budget/{session_id}")
    async def get_clarification_budget(
        session_id: str,
        engine: CDICEngine = Depends(get_engine)
    ):
        """Get remaining clarification budget for session"""
        budget_exceeded, remaining = engine._check_clarification_budget(session_id)
        return {
            "session_id": session_id,
            "remaining_budget": remaining,
            "budget_exceeded": budget_exceeded,
            "max_budget": config.clarification_budget_per_session
        }
    
    return app
