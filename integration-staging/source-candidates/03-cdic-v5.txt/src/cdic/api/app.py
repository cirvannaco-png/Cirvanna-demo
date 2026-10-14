import os
import asyncio
from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks, Header
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from typing import Optional

from ..config import CDICConfig
from ..core.engine import CDICEngine
from ..common.structs import DecisionContext as DecisionContextModel
from .dependencies import get_engine

def create_app(config: CDICConfig = None):
    if config is None:
        config = CDICConfig(
            secret_key=os.environ.get("CDIC_SECRET_KEY", "default-secret-key-32-characters!!"),
            redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        )

    app = FastAPI(
        title="CDIC Decision Engine",
        version="5.0.0",
        docs_url="/docs" if config.log_level == "DEBUG" else None
    )

    # Middleware
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

    # Dependency override to inject engine
    app.dependency_overrides[get_engine] = lambda: engine

    # Authentication dependency
    async def verify_api_key(x_api_key: Optional[str] = Header(None)):
        if config.api_key_required and (not x_api_key or x_api_key != config.api_key):
            raise HTTPException(status_code=401, detail="Invalid API key")
        return x_api_key

    # Rate limiting middleware
    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        client_ip = request.client.host
        rate_key = f"rate:{client_ip}"
        if engine.redis:
            current = engine.redis.incr(rate_key)
            engine.redis.expire(rate_key, 60)
            if current > config.rate_limit_requests:
                return JSONResponse(status_code=429, content={"error": "Rate limit exceeded"})
        response = await call_next(request)
        return response

    # Routes
    @app.post("/v1/decide")
    async def decide(
        context: DecisionContextModel,
        background_tasks: BackgroundTasks,
        api_key: str = Depends(verify_api_key),
        engine: CDICEngine = Depends(get_engine)
    ):
        try:
            # Convert Pydantic model to internal DecisionContext
            ctx = DecisionContextModel.create(
                intent=context.intent,
                input_data=context.input_snapshot,
                user_id=context.user_id,
                session_id=context.session_id,
                cultural_context=context.cultural_context,
                coverage_required=context.coverage_required,
                exploration_allowed=context.exploration_allowed,
                temporal_scope=context.temporal_scope
            )
            result = await engine.process_decision(ctx, {})
            background_tasks.add_task(engine._log_async, "api_decision", {"request_id": ctx.request_id})
            return result
        except Exception as e:
            engine.logger.error(f"API decision failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/v1/metrics")
    async def metrics(engine: CDICEngine = Depends(get_engine)):
        if config.enable_prometheus:
            return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
        else:
            return engine.get_stats()

    @app.get("/health")
    async def health():
        return {"status": "healthy", "version": "5.0.0"}

    @app.get("/ready")
    async def ready(engine: CDICEngine = Depends(get_engine)):
        if engine.redis:
            try:
                engine.redis.ping()
            except Exception:
                raise HTTPException(status_code=503, detail="Redis unavailable")
        return {"status": "ready"}

    return app
