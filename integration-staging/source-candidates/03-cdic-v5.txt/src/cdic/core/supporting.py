import json
import time
from threading import Lock
from collections import deque
from typing import Dict, List, Tuple, Any
from ..common.utils import lazy_import
from ..common.caches import LRUCache

class SecureHasher:
    def __init__(self, secret_key: bytes, cache_size: int = 10000):
        self.secret_key = secret_key
        self.cache = LRUCache(cache_size)
        crypto = lazy_import('cryptography')
        if crypto is None:
            raise ImportError("cryptography not available")
        self.hashes = crypto['hashes']
        self.HKDF = crypto['HKDF']
        self.hkdf = self.HKDF(algorithm=self.hashes.SHA256(), length=32, salt=None, info=b'cdic-hash')
        self.derived_key = self.hkdf.derive(secret_key)

    def compute_hash(self, data: Dict) -> str:
        data_str = json.dumps(data, sort_keys=True, separators=(',', ':'))
        cache_key = hash(data_str)
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        h = self.hashes.Hash(self.hashes.SHA256())
        h.update(self.derived_key[:16])
        h.update(data_str.encode())
        result = h.finalize().hex()
        self.cache.put(cache_key, result)
        return result

    def verify_hash(self, data: Dict, hash_str: str) -> bool:
        return self.compute_hash(data) == hash_str

class CircuitBreaker:
    def __init__(self, threshold: int, timeout: int):
        self.threshold = threshold
        self.timeout = timeout
        self.failures = deque(maxlen=threshold * 2)
        self.state = "CLOSED"
        self.last_state_change = time.time()
        self.lock = Lock()
        self.stats = {'successes': 0, 'failures': 0, 'trips': 0}

    def allow_request(self) -> bool:
        with self.lock:
            if self.state == "OPEN":
                if time.time() - self.last_state_change > self.timeout:
                    self.state = "HALF_OPEN"
                    self.last_state_change = time.time()
                    return True
                return False
            return True

    def record_success(self):
        with self.lock:
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failures.clear()
            self.stats['successes'] += 1

    def record_failure(self):
        with self.lock:
            self.failures.append(time.time())
            cutoff = time.time() - self.timeout
            recent = sum(1 for t in self.failures if t > cutoff)
            if recent >= self.threshold:
                self.state = "OPEN"
                self.last_state_change = time.time()
                self.stats['trips'] += 1
            self.stats['failures'] += 1

    def get_stats(self) -> Dict:
        with self.lock:
            cutoff = time.time() - self.timeout
            recent = sum(1 for t in self.failures if t > cutoff)
            return {
                'state': self.state,
                'successes': self.stats['successes'],
                'failures': self.stats['failures'],
                'trips': self.stats['trips'],
                'recent_failures': recent
            }

class ImmutableDoctrine:
    """Full doctrine enforcement with rules."""
    def __init__(self):
        self.rules = {
            "min_confidence": 0.3,
            "max_risk": 0.8,
            "required_fields": ["action", "rationale"],
            "banned_actions": ["harm", "exploit", "deceive"],
            "ethical_constraints": [
                "respect_autonomy",
                "do_no_harm",
                "fairness",
                "transparency"
            ]
        }

    def check_compliance(self, option: Dict[str, Any]) -> Tuple[bool, List[str]]:
        violations = []
        # Check confidence
        if option.get('confidence', 0) < self.rules['min_confidence']:
            violations.append('confidence_too_low')
        # Check risk (if present)
        if option.get('risk_score', 1.0) > self.rules['max_risk']:
            violations.append('risk_too_high')
        # Check required fields
        for field in self.rules['required_fields']:
            if field not in option:
                violations.append(f'missing_field_{field}')
        # Check banned actions
        action = str(option.get('action', '')).lower()
        for banned in self.rules['banned_actions']:
            if banned in action:
                violations.append(f'banned_action_{banned}')
        return len(violations) == 0, violations
