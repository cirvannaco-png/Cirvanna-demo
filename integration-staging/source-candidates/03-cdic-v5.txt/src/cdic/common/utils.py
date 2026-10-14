import warnings
import importlib
from threading import Lock

_import_cache = {}
_import_lock = Lock()

def lazy_import(name: str):
    """Thread-safe lazy import with caching."""
    with _import_lock:
        if name not in _import_cache:
            try:
                if name == 'numpy':
                    import numpy as np
                    _import_cache[name] = np
                elif name == 'numba':
                    import numba
                    _import_cache[name] = numba
                elif name == 'cupy':
                    try:
                        import cupy as cp
                        _import_cache[name] = cp
                    except ImportError:
                        _import_cache[name] = None
                elif name == 'redis':
                    import redis
                    _import_cache[name] = redis
                elif name == 'msgpack':
                    import msgpack
                    _import_cache[name] = msgpack
                elif name == 'cryptography':
                    from cryptography.hazmat.primitives import hashes, hmac
                    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
                    _import_cache[name] = {'hashes': hashes, 'hmac': hmac, 'HKDF': HKDF}
                elif name == 'psutil':
                    import psutil
                    _import_cache[name] = psutil
                else:
                    module = importlib.import_module(name)
                    _import_cache[name] = module
            except ImportError as e:
                warnings.warn(f"Failed to import {name}: {e}")
                _import_cache[name] = None
        return _import_cache[name]
