"""
CompressionManager – Simple gzip compression.
"""
import gzip
from typing import Tuple

class CompressionManager:
    async def compress(self, data: bytes, data_type: str = 'generic') -> Tuple[bytes, str]:
        if len(data) > 1024:
            return gzip.compress(data), 'gzip'
        return data, 'none'

    async def decompress(self, data: bytes, algorithm: str) -> bytes:
        if algorithm == 'gzip':
            return gzip.decompress(data)
        return data
