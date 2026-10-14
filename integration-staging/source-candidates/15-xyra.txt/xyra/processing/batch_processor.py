"""
Adaptive batch processing with dynamic optimization.
"""
import asyncio
import time
from collections import deque
import numpy as np

class AdaptiveBatchProcessor:
    def __init__(self, config):
        self.config = config
        self.batch_size = config.VECTOR_SIMILARITY_BATCH_SIZE
        self.batch_size_history = deque(maxlen=100)
        self.processing_times = deque(maxlen=100)
        self.optimal_batch_size = config.VECTOR_SIMILARITY_BATCH_SIZE
        self.thresholds = {
            "fast": 10,
            "optimal": 50,
            "slow": 100
        }

    async def process_batch(self, items, processor):
        start_time = time.perf_counter()
        if len(items) <= self.batch_size:
            result = await processor(items)
            elapsed = (time.perf_counter() - start_time) * 1000
            self.record_processing_time(elapsed, len(items))
            self.adapt_batch_size()
            return result
        chunk_size = self.optimal_batch_size
        chunks = [
            items[i:i + chunk_size]
            for i in range(0, len(items), chunk_size)
        ]
        semaphore = asyncio.Semaphore(self.config.MAX_CONCURRENT_ML)
        async def process_with_limit(chunk):
            async with semaphore:
                return await processor(chunk)
        tasks = [process_with_limit(chunk) for chunk in chunks]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        combined = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                try:
                    fallback_result = await processor(chunks[i])
                    combined.extend(fallback_result)
                except Exception:
                    pass
                continue
            combined.extend(result)
        elapsed = (time.perf_counter() - start_time) * 1000
        self.record_processing_time(elapsed, len(items))
        self.adapt_batch_size()
        return combined

    def record_processing_time(self, elapsed_ms, batch_size):
        self.processing_times.append(elapsed_ms)
        self.batch_size_history.append(batch_size)

    def adapt_batch_size(self):
        if len(self.processing_times) < 5:
            return
        recent_times = list(self.processing_times)[-5:]
        recent_sizes = list(self.batch_size_history)[-5:]
        avg_time = np.mean(recent_times)
        avg_size = np.mean(recent_sizes)
        if avg_time < self.thresholds["fast"] and avg_size == self.optimal_batch_size:
            self.optimal_batch_size = min(
                self.config.MAX_BATCH_SIZE,
                int(self.optimal_batch_size * 1.5)
            )
        elif avg_time > self.thresholds["slow"]:
            self.optimal_batch_size = max(
                10,
                int(self.optimal_batch_size * 0.7)
            )

    def get_metrics(self):
        return {
            "optimal_batch_size": self.optimal_batch_size,
            "avg_processing_time": np.mean(self.processing_times) if self.processing_times else 0,
            "total_batches_processed": len(self.processing_times),
        }
