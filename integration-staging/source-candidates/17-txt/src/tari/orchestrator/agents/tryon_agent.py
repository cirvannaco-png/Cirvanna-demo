"""
Try-On Agent – async queue for virtual try-on rendering.
"""
import asyncio
import uuid
import time
from typing import Dict, Any, Optional, List
from ...config import TariConfig
from ...cache.predictive_cache import PredictiveCache
from ...privacy.manager import PrivacyManager
from ...connection_pool import SecureConnectionPool

class TryOnAgent:
    def __init__(self, config: TariConfig, cache: PredictiveCache,
                 privacy_manager: PrivacyManager, pool: SecureConnectionPool):
        self.config = config
        self.cache = cache
        self.privacy_manager = privacy_manager
        self.pool = pool
        self._job_queue = asyncio.Queue()
        self._workers = []
        self._render_cache = {}

    async def start(self):
        for _ in range(self.config.TRYON_GPU_WORKERS):
            worker = asyncio.create_task(self._worker_loop())
            self._workers.append(worker)

    async def queue_tryon(self, user_id: str, outfit: Dict, context: Dict) -> Dict:
        """Submit a try-on job to the async queue."""
        job_id = str(uuid.uuid4())
        resolution = self.config.FREE_TIER_TRYON_RESOLUTION
        if context.get("tier") == "premium":
            resolution = self.config.PREMIUM_TIER_TRYON_RESOLUTION
        job = {
            "job_id": job_id,
            "user_id": user_id,
            "outfit": outfit,
            "context": context,
            "resolution": resolution,
            "status": "queued",
            "created_at": time.time()
        }
        await self._job_queue.put(job)
        await self._store_job(job)
        return {"job_id": job_id, "status": "queued", "estimated_time_ms": self.config.MAX_TRYON_QUEUE_DELAY_MS}

    async def _worker_loop(self):
        while True:
            try:
                job = await self._job_queue.get()
                await self._process_job(job)
            except asyncio.CancelledError:
                break
            except Exception as e:
                job["status"] = "failed"
                job["error"] = str(e)
                await self._update_job(job)

    async def _process_job(self, job: Dict):
        job["status"] = "rendering"
        await self._update_job(job)
        # Simulate rendering (place – call actual try-on model)
        await asyncio.sleep(2)
        # For simplicity, generate dummy image URL
        render_url = f"https://render.xyra.ai/{job['job_id']}.png"
        job["status"] = "completed"
        job["render_url"] = render_url
        job["completed_at"] = time.time()
        await self._update_job(job)
        # Cache result
        self._render_cache[job["job_id"]] = job

    async def get_result(self, job_id: str) -> Optional[Dict]:
        if job_id in self._render_cache:
            return self._render_cache[job_id]
        # Check storage
        return await self._fetch_job(job_id)

    async def _store_job(self, job: Dict):
        pool = await SecureConnectionPool.get_instance()
        async with pool.get_redis() as redis_pool:
            await redis_pool.setex(f"tryon_job:{job['job_id']}", 3600, orjson.dumps(job))

    async def _update_job(self, job: Dict):
        pool = await SecureConnectionPool.get_instance()
        async with pool.get_redis() as redis_pool:
            await redis_pool.setex(f"tryon_job:{job['job_id']}", 3600, orjson.dumps(job))

    async def _fetch_job(self, job_id: str) -> Optional[Dict]:
        pool = await SecureConnectionPool.get_instance()
        async with pool.get_redis() as redis_pool:
            data = await redis_pool.get(f"tryon_job:{job_id}")
            if data:
                return orjson.loads(data)
        return None

    async def health(self) -> Dict:
        return {"agent": "tryon", "queue_size": self._job_queue.qsize(), "workers": len(self._workers)}
