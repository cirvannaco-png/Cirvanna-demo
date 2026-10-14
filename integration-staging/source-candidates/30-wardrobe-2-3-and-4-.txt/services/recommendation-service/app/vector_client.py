"""Qdrant client wrapper for item embeddings."""
from __future__ import annotations

import logging

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from .config import QDRANT_COLLECTION, QDRANT_URL, QDRANT_VECTOR_SIZE

logger = logging.getLogger(__name__)


class VectorClient:
    def __init__(self) -> None:
        self.client = AsyncQdrantClient(url=QDRANT_URL)
        self.collection = QDRANT_COLLECTION

    async def ensure_collection(self) -> None:
        cols = await self.client.get_collections()
        if self.collection not in [c.name for c in cols.collections]:
            await self.client.create_collection(
                self.collection,
                vectors_config=VectorParams(size=QDRANT_VECTOR_SIZE, distance=Distance.COSINE),
            )
            logger.info(f"Created Qdrant collection {self.collection}")

    async def upsert(self, item_id: str, vector: list[float], payload: dict) -> None:
        await self.client.upsert(
            self.collection,
            points=[PointStruct(id=item_id, vector=vector, payload=payload)],
        )

    async def search(
        self, vector: list[float], limit: int = 10, score_threshold: float | None = None
    ) -> list[dict]:
        results = await self.client.search(
            self.collection,
            query_vector=vector,
            limit=limit,
            score_threshold=score_threshold,
        )
        return [{"id": r.id, "score": r.score, "payload": r.payload} for r in results]

    async def close(self) -> None:
        await self.client.close()
