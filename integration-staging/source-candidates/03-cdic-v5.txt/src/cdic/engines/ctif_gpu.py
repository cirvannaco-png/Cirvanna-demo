import time
import uuid
from threading import RLock
from typing import Dict, Optional
from ..common.utils import lazy_import
from ..common.caches import LRUCache, _context_vector_cache
from ..common.enums import TrendAuthority

class CTIFEngineGPU:
    """GPU-accelerated Contextual Trend Influence Factor engine with CPU fallback."""
    def __init__(self, max_signals: int = 1000, vector_dim: int = 128, use_gpu: bool = True):
        self.max_signals = max_signals
        self.vector_dim = vector_dim
        self.use_gpu = use_gpu
        self.gpu_available = False
        if use_gpu:
            cp = lazy_import('cupy')
            self.gpu_available = cp is not None
            if self.gpu_available:
                cp = lazy_import('cupy')
                self.trend_vectors_gpu = cp.zeros((max_signals, vector_dim), dtype=cp.float32)
                self.influences_gpu = cp.zeros(max_signals, dtype=cp.float32)
                self.authority_levels_gpu = cp.zeros(max_signals, dtype=cp.int8)
                self.timestamps_gpu = cp.zeros(max_signals, dtype=cp.float64)
                self.masks_gpu = cp.zeros(max_signals, dtype=cp.bool_)
        # CPU fallback arrays
        np = lazy_import('numpy')
        self.trend_vectors = np.zeros((max_signals, vector_dim), dtype=np.float32)
        self.influences = np.zeros(max_signals, dtype=np.float32)
        self.authority_levels = np.zeros(max_signals, dtype=np.int8)
        self.timestamps = np.zeros(max_signals, dtype=np.float64)
        self.masks = np.zeros(max_signals, dtype=np.bool_)

        self.signal_count = 0
        self.signal_map = {}      # signal_id -> index
        self.index_map = {}       # index -> signal_id
        self.lock = RLock()
        self.vector_cache = _context_vector_cache
        self.similarity_cache = LRUCache(5000)
        self.stats = {'gpu_ops': 0, 'cpu_ops': 0, 'cache_hits': 0}
        self.similarity_threshold = 0.7
        self._warmup()

    def _warmup(self):
        common_contexts = [
            {'action': 'recommend', 'category': 'general'},
            {'action': 'filter', 'type': 'content'},
            {'action': 'search', 'scope': 'global'}
        ]
        for ctx in common_contexts:
            _ = self.compute_context_vector(ctx)

    def compute_context_vector(self, context: Dict) -> np.ndarray:
        context_hash = hash(frozenset(context.items()))
        cached = self.vector_cache.get(context_hash)
        if cached is not None:
            self.stats['cache_hits'] += 1
            return cached
        np = lazy_import('numpy')
        # Use context_hash as seed for deterministic randomness
        rng = np.random.RandomState(context_hash)
        vector = rng.randn(self.vector_dim).astype(np.float32)
        norm = np.sqrt(np.dot(vector, vector))
        if norm > 0:
            vector /= norm
        self.vector_cache.put(context_hash, vector)
        return vector

    def _hash_context(self, context: Dict) -> int:
        return hash(frozenset(context.items()))

    def add_signal(self, context: Dict, influence: float, authority: TrendAuthority) -> int:
        with self.lock:
            if self.signal_count >= self.max_signals:
                self._evict_oldest(10)
            idx = self.signal_count
            if idx >= self.max_signals:
                # Try to find free slot
                for i in range(self.max_signals):
                    if i not in self.index_map:
                        idx = i
                        break
                else:
                    idx = self.signal_count % self.max_signals
            signal_id = uuid.uuid4().int
            vector = self.compute_context_vector(context)
            if self.gpu_available:
                cp = lazy_import('cupy')
                self.trend_vectors_gpu[idx] = cp.asarray(vector)
                self.influences_gpu[idx] = influence
                self.authority_levels_gpu[idx] = authority.value
                self.timestamps_gpu[idx] = time.time()
                self.masks_gpu[idx] = True
            else:
                self.trend_vectors[idx] = vector
                self.influences[idx] = influence
                self.authority_levels[idx] = authority.value
                self.timestamps[idx] = time.time()
                self.masks[idx] = True
            self.signal_map[signal_id] = idx
            self.index_map[idx] = signal_id
            self.signal_count = max(self.signal_count, idx + 1)
            return signal_id

    def get_contextual_influence(self, context: Dict, max_signals: int = 50) -> float:
        start_time = time.perf_counter()
        if self.signal_count == 0:
            return 0.0
        context_vector = self.compute_context_vector(context)
        if self.gpu_available:
            cp = lazy_import('cupy')
            context_gpu = cp.asarray(context_vector)
            active_mask = self.masks_gpu[:self.signal_count]
            if not cp.any(active_mask):
                return 0.0
            active_indices = cp.where(active_mask)[0]
            active_vectors = self.trend_vectors_gpu[active_indices]
            active_influences = self.influences_gpu[active_indices]
            similarities = cp.dot(active_vectors, context_gpu)
            threshold_mask = similarities > self.similarity_threshold
            if not cp.any(threshold_mask):
                return 0.0
            valid_indices = cp.where(threshold_mask)[0]
            valid_similarities = similarities[valid_indices]
            valid_influences = active_influences[valid_indices]
            k = min(max_signals, len(valid_similarities))
            if k > 0:
                # get top k indices
                top_k_indices = cp.argpartition(-valid_similarities, k)[:k]
                top_similarities = valid_similarities[top_k_indices]
                top_influences = valid_influences[top_k_indices]
                # Check immutable authority
                top_authorities = self.authority_levels_gpu[active_indices[valid_indices[top_k_indices]]]
                immutable_mask = top_authorities == TrendAuthority.IMMUTABLE.value
                if cp.any(immutable_mask):
                    # If any immutable, take only those (or highest?)
                    # For simplicity, take highest influence among immutable
                    top_similarities = top_similarities[immutable_mask]
                    top_influences = top_influences[immutable_mask]
                weighted_sum = cp.sum(top_influences * top_similarities)
                count = len(top_similarities)
                result = float(cp.clip(weighted_sum / max(count, 1), -1.0, 1.0))
                self.stats['gpu_ops'] += 1
                return result
        else:
            # CPU fallback
            np = lazy_import('numpy')
            active_indices = np.where(self.masks[:self.signal_count])[0]
            if len(active_indices) == 0:
                return 0.0
            active_vectors = self.trend_vectors[active_indices]
            similarities = np.dot(active_vectors, context_vector)
            threshold_mask = similarities > self.similarity_threshold
            valid_indices = active_indices[threshold_mask]
            if len(valid_indices) == 0:
                return 0.0
            k = min(max_signals, len(valid_indices))
            # Sort by similarity descending
            order = np.argsort(similarities[threshold_mask])[::-1][:k]
            valid_indices = valid_indices[order]
            top_similarities = similarities[valid_indices]
            top_influences = self.influences[valid_indices]
            top_authorities = self.authority_levels[valid_indices]
            immutable_mask = top_authorities == TrendAuthority.IMMUTABLE.value
            if np.any(immutable_mask):
                top_similarities = top_similarities[immutable_mask]
                top_influences = top_influences[immutable_mask]
            weighted_sum = np.sum(top_influences * top_similarities)
            count = len(top_similarities)
            result = float(np.clip(weighted_sum / max(count, 1), -1.0, 1.0))
            self.stats['cpu_ops'] += 1
            return result
        return 0.0

    def _evict_oldest(self, count: int):
        with self.lock:
            if self.signal_count == 0:
                return
            # sort timestamps and evict oldest
            if self.gpu_available:
                cp = lazy_import('cupy')
                # get indices sorted by timestamp
                oldest_indices = cp.argsort(self.timestamps_gpu[:self.signal_count])[:count]
                oldest_indices = cp.asnumpy(oldest_indices)
            else:
                np = lazy_import('numpy')
                oldest_indices = np.argsort(self.timestamps[:self.signal_count])[:count]
            for idx in oldest_indices:
                self._remove_signal_at_index(int(idx))

    def _remove_signal_at_index(self, idx: int):
        if idx < self.max_signals:
            if self.gpu_available:
                cp = lazy_import('cupy')
                self.trend_vectors_gpu[idx] = 0
                self.influences_gpu[idx] = 0
                self.authority_levels_gpu[idx] = 0
                self.timestamps_gpu[idx] = 0
                self.masks_gpu[idx] = False
            else:
                self.trend_vectors[idx] = 0
                self.influences[idx] = 0
                self.authority_levels[idx] = 0
                self.timestamps[idx] = 0
                self.masks[idx] = False
            signal_id = self.index_map.pop(idx, None)
            if signal_id:
                self.signal_map.pop(signal_id, None)
            # decrement signal_count if idx was last
            if idx == self.signal_count - 1:
                while self.signal_count > 0 and not self.masks[self.signal_count - 1]:
                    self.signal_count -= 1
