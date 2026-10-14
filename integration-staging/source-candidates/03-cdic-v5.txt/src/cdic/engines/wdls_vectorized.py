import time
import uuid
import pickle
from collections import deque
from threading import RLock, Thread
from typing import Optional, Dict
from ..common.utils import lazy_import

class WDLSEngineVectorized:
    """Vectorized WDLS engine with 100-signal cap, background decay, and cold store."""
    def __init__(self, max_realtime: int = 100, cold_store=None):
        self.max_realtime = max_realtime
        self.cold_store = cold_store
        np = lazy_import('numpy')
        self.weights = np.zeros(max_realtime, dtype=np.float32)
        self.trend_impacts = np.zeros(max_realtime, dtype=np.float64)
        self.timestamps = np.zeros(max_realtime, dtype=np.float32)
        self.decay_rates = np.zeros(max_realtime, dtype=np.float32)
        self.intent_hashes = np.zeros(max_realtime, dtype=np.int64)
        self.response_codes = np.zeros(max_realtime, dtype=np.int8)
        self.pattern_hashes = np.zeros(max_realtime, dtype=np.int64)
        self.signal_ids = np.zeros(max_realtime, dtype=np.int64)
        self.active_mask = np.zeros(max_realtime, dtype=np.bool_)

        self.signal_count = 0
        self.free_indices = deque(range(max_realtime))
        self.id_to_index = {}
        self.lock = RLock()

        # Background threads
        self.decay_thread = Thread(target=self._background_decay_worker, daemon=True)
        self.eviction_thread = Thread(target=self._background_eviction_worker, daemon=True)
        self.decay_thread.start()
        self.eviction_thread.start()

        self._compile_numba_functions()

    def _compile_numba_functions(self):
        try:
            numba = lazy_import('numba')
            np = lazy_import('numpy')
            @numba.njit(fastmath=True, parallel=True, cache=True)
            def apply_decay_batch(weights, decay_rates, timestamps, current_time, count):
                for i in numba.prange(count):
                    if weights[i] > 0:
                        elapsed = (current_time - timestamps[i]) / 86400.0
                        decay_factor = 1.0 / (1.0 + decay_rates[i] * elapsed)
                        weights[i] *= decay_factor
                        timestamps[i] = current_time
                # No return, in-place modification
            self._apply_decay_batch_numba = apply_decay_batch

            @numba.njit(fastmath=True, cache=True)
            def compute_influence(intent_hash, intent_hashes, trend_impacts, weights,
                                  active_mask, count, max_cap):
                total_weight = 0.0
                total_influence = 0.0
                for i in range(count):
                    if (active_mask[i] and intent_hashes[i] == intent_hash and weights[i] > 0.01):
                        total_influence += trend_impacts[i] * weights[i]
                        total_weight += weights[i]
                if total_weight > 0:
                    weighted = total_influence / total_weight
                    if weighted > max_cap:
                        return max_cap
                    elif weighted < -max_cap:
                        return -max_cap
                    return weighted
                return 0.0
            self._compute_influence_numba = compute_influence
        except Exception:
            self._apply_decay_batch_numba = None
            self._compute_influence_numba = None

    def add_signal(self, intent_hash: int, pattern_hash: int, response_code: int,
                   weight: float, trend_impact: float) -> Optional[int]:
        with self.lock:
            if len(self.free_indices) == 0:
                self._evict_weakest(5)
            if len(self.free_indices) == 0:
                # fallback: evict oldest
                np = lazy_import('numpy')
                oldest = np.argmin(self.timestamps)
                self._remove_signal_at_index(oldest)
                self.free_indices.append(oldest)
            idx = self.free_indices.popleft()
            signal_id = uuid.uuid4().int
            self.weights[idx] = weight
            self.trend_impacts[idx] = trend_impact
            self.timestamps[idx] = time.time()
            self.decay_rates[idx] = 0.1
            self.intent_hashes[idx] = intent_hash
            self.response_codes[idx] = response_code
            self.pattern_hashes[idx] = pattern_hash
            self.signal_ids[idx] = signal_id
            self.active_mask[idx] = True
            self.id_to_index[signal_id] = idx
            self.signal_count += 1
            return signal_id

    def get_influence(self, intent_hash: int, max_cap: float = 0.15) -> float:
        if self.signal_count == 0:
            return 0.0
        current_time = time.time()
        np = lazy_import('numpy')
        # apply decay if last decay > 1 hour
        active_timestamps = self.timestamps[self.active_mask]
        if len(active_timestamps) > 0 and current_time - np.max(active_timestamps) > 3600:
            self._apply_batch_decay(current_time)
        if self._compute_influence_numba:
            influence = self._compute_influence_numba(
                intent_hash, self.intent_hashes, self.trend_impacts,
                self.weights, self.active_mask, self.max_realtime, max_cap
            )
        else:
            influence = self._compute_influence_python(intent_hash, max_cap)
        return influence

    def _compute_influence_python(self, intent_hash: int, max_cap: float) -> float:
        total_weight = 0.0
        total_influence = 0.0
        for i in range(self.max_realtime):
            if self.active_mask[i] and self.intent_hashes[i] == intent_hash and self.weights[i] > 0.01:
                total_influence += self.trend_impacts[i] * self.weights[i]
                total_weight += self.weights[i]
        if total_weight > 0:
            weighted = total_influence / total_weight
            return max(-max_cap, min(max_cap, weighted))
        return 0.0

    def _apply_batch_decay(self, current_time: float):
        if self._apply_decay_batch_numba:
            # Numba function modifies arrays in place
            self._apply_decay_batch_numba(
                self.weights, self.decay_rates, self.timestamps,
                current_time, self.max_realtime
            )
        else:
            for i in range(self.max_realtime):
                if self.active_mask[i] and self.weights[i] > 0:
                    elapsed = (current_time - self.timestamps[i]) / 86400.0
                    decay_factor = 1.0 / (1.0 + self.decay_rates[i] * elapsed)
                    self.weights[i] *= decay_factor
                    self.timestamps[i] = current_time

    def _evict_weakest(self, count: int):
        with self.lock:
            if self.signal_count == 0:
                return
            np = lazy_import('numpy')
            active_indices = np.where(self.active_mask)[0]
            if len(active_indices) == 0:
                return
            # sort by weight ascending
            sorted_idx = active_indices[np.argsort(self.weights[active_indices])]
            to_evict = sorted_idx[:min(count, len(sorted_idx))]
            for idx in to_evict:
                self._remove_signal_at_index(idx)

    def _remove_signal_at_index(self, idx: int):
        if idx < self.max_realtime and self.active_mask[idx]:
            if self.cold_store and self.weights[idx] > 0.05:
                self._move_to_cold_store(idx)
            # Clear arrays
            self.weights[idx] = 0
            self.trend_impacts[idx] = 0
            self.timestamps[idx] = 0
            self.decay_rates[idx] = 0
            self.intent_hashes[idx] = 0
            self.response_codes[idx] = 0
            self.pattern_hashes[idx] = 0
            self.signal_ids[idx] = 0
            self.active_mask[idx] = False
            # remove from mapping
            signal_id = next((sid for sid, i in self.id_to_index.items() if i == idx), None)
            if signal_id:
                del self.id_to_index[signal_id]
            self.signal_count = max(0, self.signal_count - 1)
            self.free_indices.append(idx)

    def _move_to_cold_store(self, idx: int):
        if not self.cold_store:
            return
        signal_data = {
            'weight': float(self.weights[idx]),
            'trend_impact': float(self.trend_impacts[idx]),
            'timestamp': float(self.timestamps[idx]),
            'intent_hash': int(self.intent_hashes[idx]),
            'response_code': int(self.response_codes[idx]),
            'pattern_hash': int(self.pattern_hashes[idx])
        }
        key = f"wdls_cold:{self.signal_ids[idx]}"
        try:
            self.cold_store.setex(key, 86400 * 30, pickle.dumps(signal_data))
        except Exception:
            pass

    def _background_decay_worker(self):
        while True:
            time.sleep(3600)  # hourly
            with self.lock:
                self._apply_batch_decay(time.time())

    def _background_eviction_worker(self):
        while True:
            time.sleep(1800)  # every 30 minutes
            with self.lock:
                if self.signal_count > self.max_realtime * 0.8:
                    self._evict_weakest(self.signal_count - int(self.max_realtime * 0.7))
