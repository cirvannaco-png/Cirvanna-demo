"""
Simulated S3 client for event log storage.
"""
import uuid
from typing import Dict, List

class S3Client:
    _bucket: Dict[str, List[Dict]] = {}

    async def put_event(self, user_id: str, event: Dict) -> str:
        key = f"events/{user_id}/{uuid.uuid4()}.json"
        if user_id not in self._bucket:
            self._bucket[user_id] = []
        self._bucket[user_id].append(event)
        return key

    async def get_events_since(self, user_id: str, timestamp: float) -> List[Dict]:
        if user_id not in self._bucket:
            return []
        return [e for e in self._bucket[user_id] if e.get('timestamp', 0) > timestamp]
