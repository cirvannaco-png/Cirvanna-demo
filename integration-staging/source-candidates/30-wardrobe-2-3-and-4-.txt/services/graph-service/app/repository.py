"""Neo4j repository — the only place Cypher is written."""
from __future__ import annotations

import logging
from typing import Any

from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession

from common.config import settings

logger = logging.getLogger(__name__)


class GraphRepository:
    def __init__(self) -> None:
        self.driver: AsyncDriver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
            max_connection_pool_size=settings.neo4j_max_pool_size,
        )

    async def close(self) -> None:
        await self.driver.close()

    async def verify_connectivity(self) -> None:
        await self.driver.verify_connectivity()

    async def ensure_constraints(self) -> None:
        async with self.driver.session() as s:
            await s.run("CREATE CONSTRAINT item_id IF NOT EXISTS FOR (i:Item) REQUIRE i.id IS UNIQUE")
            await s.run(
                "CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE"
            )

    async def upsert_item(self, item_id: str, owner_id: str, category: str) -> None:
        async with self.driver.session() as s:
            await s.run(
                """
                MERGE (u:User {id: $owner})
                MERGE (i:Item {id: $id})
                SET i.category = $cat, i.owner_id = $owner
                MERGE (u)-[:OWNS]->(i)
                """,
                id=item_id, owner=owner_id, cat=category,
            )

    async def create_edge(
        self, from_id: str, to_id: str, weight: float, confidence: float
    ) -> None:
        async with self.driver.session() as s:
            await s.run(
                """
                MATCH (a:Item {id: $f}), (b:Item {id: $t})
                MERGE (a)-[r:COMPATIBLE_WITH]->(b)
                SET r.weight = $w, r.confidence = $c, r.updated_at = datetime()
                """,
                f=from_id, t=to_id, w=weight, c=confidence,
            )

    async def get_compatible(
        self, item_id: str, min_confidence: float, limit: int
    ) -> list[dict[str, Any]]:
        async with self.driver.session() as s:
            result = await s.run(
                """
                MATCH (a:Item {id: $id})-[r:COMPATIBLE_WITH]->(b:Item)
                WHERE r.confidence >= $mc
                RETURN b.id AS id, b.category AS category,
                       r.weight AS weight, r.confidence AS confidence
                ORDER BY r.weight DESC
                LIMIT $l
                """,
                id=item_id, mc=min_confidence, l=limit,
            )
            return [dict(rec) async for rec in result]

    async def decay_and_prune(self, days: int, prune_below: float) -> int:
        async with self.driver.session() as s:
            result = await s.run(
                """
                MATCH ()-[r:COMPATIBLE_WITH]->()
                SET r.weight = r.weight * ($decay ^ ($d / 30.0))
                WITH r WHERE r.weight < $th
                DELETE r
                RETURN count(r) AS removed
                """,
                decay=0.97, d=days, th=prune_below,
            )
            record = await result.single()
            return int(record["removed"]) if record else 0

    async def stats(self) -> dict[str, int]:
        async with self.driver.session() as s:
            r = await s.run("MATCH (i:Item) RETURN count(i) AS items")
            items = (await r.single())["items"]
            r = await s.run("MATCH ()-[e:COMPATIBLE_WITH]->() RETURN count(e) AS edges")
            edges = (await r.single())["edges"]
            return {"items": int(items), "edges": int(edges)}
