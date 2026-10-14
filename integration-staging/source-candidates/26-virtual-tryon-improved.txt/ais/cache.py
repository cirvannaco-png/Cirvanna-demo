import redis
import json
import hashlib
from typing import Optional
from urllib.parse import urlparse
from shared.body import BodyMesh
from .config import AISConfig

class BodyMeshCache:
    def __init__(self, config: AISConfig):
        parsed = urlparse(config.redis_url)
        self.redis_client = redis.Redis(
            host=parsed.hostname or "localhost",
            port=parsed.port or 6379,
            password=parsed.password,
            decode_responses=True
        )
        self.ttl = config.cache_ttl

    def generate_key(self, capture) -> str:
        content = {
            "images": capture.images,
            "height": capture.height_cm,
            "camera_metadata": capture.camera_metadata.dict()
        }
        if capture.optional_weight_kg:
            content["weight"] = capture.optional_weight_kg
        content_str = json.dumps(content, sort_keys=True)
        return hashlib.md5(content_str.encode()).hexdigest()

    def get(self, key: str) -> Optional[BodyMesh]:
        try:
            data = self.redis_client.get(f"body_mesh:{key}")
            if data:
                return BodyMesh.parse_raw(data)
        except Exception as e:
            print(f"Cache read error: {e}")
        return None

    def set(self, key: str, body_mesh: BodyMesh):
        try:
            self.redis_client.setex(f"body_mesh:{key}", self.ttl, body_mesh.json())
        except Exception as e:
            print(f"Cache write error: {e}")
        except Exception as e:
            print(f"Cache write error: {e}")

    def store_by_id(self, mesh_id: str, body_mesh: BodyMesh):
        try:
            self.redis_client.setex(f"body_mesh_id:{mesh_id}", self.ttl, body_mesh.json())
        except Exception as e:
            print(f"Cache write error: {e}")

    def get_by_id(self, mesh_id: str) -> Optional[BodyMesh]:
        try:
            data = self.redis_client.get(f"body_mesh_id:{mesh_id}")
            if data:
                return BodyMesh.parse_raw(data)
        except Exception as e:
            print(f"Cache read error: {e}")
        return None

    def delete_by_id(self, mesh_id: str) -> bool:
        try:
            result = self.redis_client.delete(f"body_mesh_id:{mesh_id}")
            return result > 0
        except Exception as e:
            print(f"Cache delete error: {e}")
            return False
