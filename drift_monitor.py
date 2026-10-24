"""
Embedding Freshness + Retrieval Drift Monitor
Surfaces AI infrastructure health in the Founder Control Panel.
Detects: stale embeddings, retrieval quality degradation, ranking decay.

Backed by APScheduler jobs that run every 6h:
- Compute embedding freshness per index
- Probe retrieval quality with canary queries
- Emit events if drift exceeds threshold
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, timedelta
import asyncpg
import logging

logger = logging.getLogger("cirvanna.monitoring")

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

DRIFT_THRESHOLD = 0.15          # 15% degradation triggers alert
STALENESS_THRESHOLD_HOURS = 24  # Embeddings older than 24h need refresh


# ─── Schema ────────────────────────────────────────────────────────────────────

class IndexHealth(BaseModel):
    index_name: str
    vector_count: int
    oldest_embedding_hours: float
    freshness_score: float          # 0.0–1.0 (1.0 = fully fresh)
    is_stale: bool
    last_refreshed_at: Optional[datetime]
    recommended_action: Optional[str]


class RetrievalQualitySnapshot(BaseModel):
    snapshot_id: str
    query_probe: str
    expected_top_result: str
    actual_top_result: str
    similarity_score: float
    drift_from_baseline: float      # Positive = degraded
    is_drifted: bool
    measured_at: datetime


class AIInfrastructureHealth(BaseModel):
    overall_status: str             # healthy | degraded | critical
    indexes: list[IndexHealth]
    retrieval_snapshots: list[RetrievalQualitySnapshot]
    active_alerts: list[dict]
    last_audit_at: datetime
    next_audit_at: datetime


# ─── Monitoring Routes (Founder Panel) ─────────────────────────────────────────

@router.get("/ai-health", response_model=AIInfrastructureHealth)
async def get_ai_infrastructure_health():
    """
    Full AI infrastructure health report for the Founder Panel.
    Aggregates: embedding freshness, retrieval quality, active drift alerts.
    """
    now = datetime.now(timezone.utc)

    # In production: query from monitoring_snapshots table
    indexes = [
        IndexHealth(
            index_name="cirvanna_products",
            vector_count=12450,
            oldest_embedding_hours=8.3,
            freshness_score=0.91,
            is_stale=False,
            last_refreshed_at=now - timedelta(hours=8),
            recommended_action=None,
        ),
        IndexHealth(
            index_name="cirvanna_users_usi",
            vector_count=3210,
            oldest_embedding_hours=26.1,
            freshness_score=0.62,
            is_stale=True,
            last_refreshed_at=now - timedelta(hours=26),
            recommended_action="Schedule USI re-embedding run — staleness exceeds 24h threshold",
        ),
    ]

    snapshots = [
        RetrievalQualitySnapshot(
            snapshot_id="snap_001",
            query_probe="minimalist black leather jacket",
            expected_top_result="SKU-LEATHER-MINI-001",
            actual_top_result="SKU-LEATHER-MINI-001",
            similarity_score=0.94,
            drift_from_baseline=0.02,
            is_drifted=False,
            measured_at=now - timedelta(hours=1),
        ),
    ]

    stale_count = sum(1 for i in indexes if i.is_stale)
    overall = "healthy" if stale_count == 0 else ("degraded" if stale_count == 1 else "critical")

    return AIInfrastructureHealth(
        overall_status=overall,
        indexes=indexes,
        retrieval_snapshots=snapshots,
        active_alerts=[
            {
                "alert_id": "alert_001",
                "type": "embedding_staleness",
                "index": "cirvanna_users_usi",
                "message": "USI index stale — oldest embedding 26h",
                "severity": "medium",
                "triggered_at": (now - timedelta(hours=2)).isoformat(),
            }
        ] if stale_count > 0 else [],
        last_audit_at=now - timedelta(hours=1),
        next_audit_at=now + timedelta(hours=5),
    )


@router.post("/trigger-refresh/{index_name}")
async def trigger_embedding_refresh(index_name: str):
    """
    Manually trigger an embedding refresh for a specific index.
    Emits a platform event that PAMASMMA S1 acknowledges.
    In production: enqueue a background job via APScheduler.
    """
    logger.info(f"Manual embedding refresh triggered: index={index_name}")
    return {
        "status": "queued",
        "index_name": index_name,
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "estimated_duration_minutes": 8,
    }


# ─── APScheduler Job Definitions ───────────────────────────────────────────────

async def audit_embedding_freshness(dsn: str, emitter):
    """
    APScheduler job: runs every 6 hours.
    Checks embedding age across all Qdrant indexes.
    Emits EMBEDDING_DRIFT_DETECTED event if any index exceeds threshold.
    """
    from backend.cirvanna_events.emitter import embedding_drift_event

    logger.info("Embedding freshness audit starting")

    # In production: query Qdrant metadata or pgvector for oldest vector timestamp
    # Simulate: USI index is stale
    stale_indexes = [
        {"index": "cirvanna_users_usi", "oldest_hours": 26.1, "drift_score": 0.38}
    ]

    for idx in stale_indexes:
        if idx["oldest_hours"] > STALENESS_THRESHOLD_HOURS:
            event = embedding_drift_event(
                index_name=idx["index"],
                drift_score=idx["drift_score"],
                threshold=DRIFT_THRESHOLD,
            )
            await emitter.emit(event)
            logger.warning(f"Embedding drift event emitted: index={idx['index']}")


async def probe_retrieval_quality(dsn: str, emitter):
    """
    APScheduler job: runs every 12 hours.
    Fires canary queries against vector DB and measures similarity degradation.
    """
    from backend.cirvanna_events.emitter import (
        CirvannaEvent, CirvannaEventType
    )

    # Canary query set — expected top results pre-defined
    canaries = [
        ("minimalist black leather jacket", "SKU-LEATHER-MINI-001"),
        ("sustainable streetwear hoodie", "SKU-STREET-ECO-007"),
        ("bold print dress nairobi", "SKU-PRINT-NBI-003"),
    ]

    degraded = []
    for query, expected in canaries:
        # In production: run query against Qdrant, measure actual similarity vs baseline
        actual_similarity = 0.94  # Mock
        baseline = 0.96
        drift = baseline - actual_similarity

        if drift > DRIFT_THRESHOLD:
            degraded.append({"query": query, "drift": drift})

    if degraded:
        event = CirvannaEvent(
            event_type=CirvannaEventType.RETRIEVAL_QUALITY_DROP,
            payload={"degraded_queries": degraded, "count": len(degraded)},
            priority="high",
        )
        await emitter.emit(event)
        logger.warning(f"Retrieval quality drop detected: {len(degraded)} queries degraded")


# ─── Monitoring DB Schema ───────────────────────────────────────────────────────

MONITORING_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS embedding_freshness_log (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    index_name      TEXT NOT NULL,
    vector_count    INTEGER,
    oldest_hours    FLOAT,
    freshness_score FLOAT,
    is_stale        BOOLEAN DEFAULT FALSE,
    audited_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS retrieval_quality_log (
    id                  TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    query_probe         TEXT NOT NULL,
    expected_result     TEXT,
    actual_result       TEXT,
    similarity_score    FLOAT,
    drift_from_baseline FLOAT,
    is_drifted          BOOLEAN DEFAULT FALSE,
    measured_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_freshness_index ON embedding_freshness_log (index_name, audited_at DESC);
CREATE INDEX IF NOT EXISTS idx_quality_drifted ON retrieval_quality_log (is_drifted, measured_at DESC);
"""
