"""
Secure hashing utilities
"""

import hashlib
from typing import Any
import orjson
from cryptography.hazmat.backends import default_backend


class SecureHasher:
    """Fast, secure hashing"""
    
    def __init__(self, secret_key: bytes):
        self.secret_key = secret_key
        self.backend = default_backend()
    
    def compute_hash(self, data: Any) -> str:
        """Compute secure hash of data"""
        if isinstance(data, (dict, list)):
            data = orjson.dumps(data)
        elif not isinstance(data, bytes):
            data = str(data).encode()
        
        h = hashlib.blake2b(
            data,
            key=self.secret_key[:64],
            digest_size=32
        )
        return h.hexdigest()
    
    def verify_hash(self, data: Any, expected_hash: str) -> bool:
        """Verify data integrity"""
        return self.compute_hash(data) == expected_hash
