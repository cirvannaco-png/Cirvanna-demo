"""
Main FastAPI application with integrated lifespan.
"""
import os
import asyncio
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
import orjson
from ..config import TariConfig
from ..connection_pool import SecureConnectionPool
from ..middleware.security import SecurityMiddleware
from ..utils.warmup import warm_up_system, monitor_system_performance
from ..orchestrator.gateway import XyraGatewayOrchestrator
from ..orchestrator.agents.tryon_agent import TryOnAgent
from . import endpoints, health

@asynccontextmanager
async def lifespan(app: FastAPI):
    config = TariConfig()
    pool = SecureConnectionPool.get_instance(config)
    try:
        await pool.initialize()
        # Initialize gateway and start try-on workers
        cache = PredictiveCache(config)
        from ..privacy.manager import PrivacyManager
        privacy = PrivacyManager(config)
        gateway = XyraGatewayOrchestrator(config, cache, privacy, pool)
        await gateway.tryon_agent.start()
        app.state.gateway = gateway
        if config.ENABLE_FACE_ANALYSIS or config.ENABLE_BODY_CALIBRATION:
            await warm_up_system(pool, config)
        monitoring_task = asyncio.create_task(monitor_system_performance())
        yield
        monitoring_task.cancel()
        try:
            await monitoring_task
        except asyncio.CancelledError:
            pass
        await pool.close()
    except Exception as e:
        raise

app = FastAPI(
    title="Xyra V6 - Full Fashion Intelligence System",
    version="6.0.0",
    lifespan=lifespan,
    docs_url="/docs" if not os.getenv("PRODUCTION") else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=json.loads(os.getenv("ALLOWED_ORIGINS", '["*"]')),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

security_middleware = SecurityMiddleware(TariConfig())
app.middleware("http")(security_middleware)

@app.middleware("http")
async def deduplication_middleware(request, call_next):
    if request.method != "POST":
        return await call_next(request)
    import hashlib
    body = await request.body()
    fingerprint = hashlib.sha256(
        f"{request.url.path}:{body}".encode()
    ).hexdigest()
    cache_key = f"req_dedup:{fingerprint}"
    pool = await SecureConnectionPool.get_instance()
    async with pool.get_redis() as redis_pool:
        cached = await redis_pool.get(cache_key)
        if cached:
            return JSONResponse(orjson.loads(cached))
        response = await call_next(request)
        if response.status_code == 200:
            await redis_pool.setex(
                cache_key,
                2,
                orjson.dumps({
                    "status": response.status_code,
                    "body": response.body.decode() if hasattr(response.body, 'decode') else str(response.body)
                })
            )
        return response

app.include_router(endpoints.router)
app.include_router(health.router)
