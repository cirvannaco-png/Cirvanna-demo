"""
Cirvanna Event Emitter
Typed event definitions for every significant platform action.
Emits to Postgres LISTEN/NOTIFY channel 'cirvanna_events'.
PAMASMMA's daemon listener picks these up and routes to cognitive systems.

Design: fire-and-forget from Cirvanna's perspective.
PAMASMMA responds async via pamasmma_responses table.
"""

from enum import Enum
from typing import Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field
import uuid
import asyncpg
import logging
import json

logger = logging.getLogger("cirvanna.events")

CIRVANNA_EVENTS_CHANNEL = "cirvanna_events"
PAMASMMA_RESPONSES_CHANNEL = "pamasmma_responses"


# ─── Event Type Registry ───────────────────────────────────────────────────────

class CirvannaEventType(str, Enum):
    # Customer events → S3 Relationship Management
    CUSTOMER_SUPPORT_NEEDED = "customer.support_needed"
    CUSTOMER_CART_ABANDONED = "customer.cart_abandoned"
    CUSTOMER_SIGNED_UP = "customer.signed_up"
    CUSTOMER_HIGH_VALUE = "customer.high_value_detected"

    # Brand events → S2 Marketing + S4 Narrative
    BRAND_ONBOARDED = "brand.onboarded"
    BRAND_PRODUCT_UPLOADED = "brand.product_uploaded"
    BRAND_PRODUCT_LIVE = "brand.product_live"
    BRAND_COMPLAINT = "brand.complaint"
    BRAND_REVENUE_MILESTONE = "brand.revenue_milestone"

    # Platform events → S1 Executive
    ANOMALY_ALERT = "platform.anomaly_alert"
    PLATFORM_DEGRADED = "platform.degraded"
    EMBEDDING_DRIFT_DETECTED = "platform.embedding_drift"
    RETRIEVAL_QUALITY_DROP = "platform.retrieval_quality_drop"
    REVENUE_THRESHOLD = "platform.revenue_threshold"

    # Content/campaign events → S5 Creator + S6 Audience
    CAMPAIGN_CREATED = "content.campaign_created"
    LOW_CTR_DETECTED = "content.low_ctr"
    VIRAL_SKU_DETECTED = "content.viral_sku"

    # System events → S10 Strategic
    WEEKLY_REVIEW_DUE = "system.weekly_review"
    FOUNDER_OVERRIDE_APPLIED = "system.founder_override"


# ─── Event Schema ──────────────────────────────────────────────────────────────

class CirvannaEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: CirvannaEventType
    source: str = "cirvanna"
    payload: dict[str, Any] = Field(default_factory=dict)
    user_id: Optional[str] = None
    brand_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Routing hint — PAMASMMA uses this to select cognitive system
    target_system: Optional[str] = None
    priority: str = "normal"  # critical | high | normal | low


# ─── Event→System Routing Map ─────────────────────────────────────────────────

EVENT_ROUTING: dict[CirvannaEventType, str] = {
    CirvannaEventType.CUSTOMER_SUPPORT_NEEDED: "relationship_management",
    CirvannaEventType.CUSTOMER_CART_ABANDONED: "behavioral_consistency",
    CirvannaEventType.CUSTOMER_SIGNED_UP: "audience_psychology",
    CirvannaEventType.CUSTOMER_HIGH_VALUE: "relationship_management",
    CirvannaEventType.BRAND_ONBOARDED: "marketing_intelligence",
    CirvannaEventType.BRAND_PRODUCT_UPLOADED: "narrative_governance",
    CirvannaEventType.BRAND_PRODUCT_LIVE: "creator_economy",
    CirvannaEventType.BRAND_COMPLAINT: "relationship_management",
    CirvannaEventType.BRAND_REVENUE_MILESTONE: "executive_operations",
    CirvannaEventType.ANOMALY_ALERT: "executive_operations",
    CirvannaEventType.PLATFORM_DEGRADED: "executive_operations",
    CirvannaEventType.EMBEDDING_DRIFT_DETECTED: "executive_operations",
    CirvannaEventType.RETRIEVAL_QUALITY_DROP: "executive_operations",
    CirvannaEventType.REVENUE_THRESHOLD: "executive_operations",
    CirvannaEventType.CAMPAIGN_CREATED: "creator_economy",
    CirvannaEventType.LOW_CTR_DETECTED: "marketing_intelligence",
    CirvannaEventType.VIRAL_SKU_DETECTED: "creator_economy",
    CirvannaEventType.WEEKLY_REVIEW_DUE: "strategic_narrative",
    CirvannaEventType.FOUNDER_OVERRIDE_APPLIED: "executive_operations",
}


# ─── Emitter ───────────────────────────────────────────────────────────────────

class CirvannaEventEmitter:
    """
    Singleton-style emitter. Acquire a single asyncpg connection per process.
    Emits events as NOTIFY payload to 'cirvanna_events'.
    """

    def __init__(self, dsn: str):
        self._dsn = dsn
        self._conn: Optional[asyncpg.Connection] = None

    async def connect(self):
        self._conn = await asyncpg.connect(self._dsn)
        logger.info("CirvannaEventEmitter: Postgres connection established")

    async def disconnect(self):
        if self._conn:
            await self._conn.close()

    async def emit(self, event: CirvannaEvent) -> str:
        """
        Fire-and-forget: NOTIFY cirvanna_events with JSON payload.
        Returns event_id for tracing.
        Also persists to cirvanna_events_log for audit.
        """
        if not self._conn:
            raise RuntimeError("EventEmitter not connected — call connect() first")

        # Auto-route if target_system not specified
        if not event.target_system:
            event.target_system = EVENT_ROUTING.get(event.event_type, "executive_operations")

        payload = event.model_dump_json()

        async with self._conn.transaction():
            # Persist to audit log
            await self._conn.execute(
                """
                INSERT INTO cirvanna_events_log
                  (event_id, event_type, source, payload, user_id, brand_id,
                   target_system, priority, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                event.event_id,
                event.event_type.value,
                event.source,
                event.payload,
                event.user_id,
                event.brand_id,
                event.target_system,
                event.priority,
                event.timestamp,
            )
            # NOTIFY PAMASMMA
            await self._conn.execute(
                f"SELECT pg_notify('{CIRVANNA_EVENTS_CHANNEL}', $1)",
                payload,
            )

        logger.info(
            f"Event emitted: type={event.event_type} id={event.event_id} "
            f"target={event.target_system} priority={event.priority}"
        )
        return event.event_id


# ─── Convenience Factories ─────────────────────────────────────────────────────

def customer_support_event(user_id: str, message: str, channel: str = "web") -> CirvannaEvent:
    return CirvannaEvent(
        event_type=CirvannaEventType.CUSTOMER_SUPPORT_NEEDED,
        user_id=user_id,
        payload={"message": message, "channel": channel},
        priority="high",
    )


def brand_onboarded_event(brand_id: str, brand_name: str, category: str) -> CirvannaEvent:
    return CirvannaEvent(
        event_type=CirvannaEventType.BRAND_ONBOARDED,
        brand_id=brand_id,
        payload={"brand_name": brand_name, "category": category},
        priority="high",
    )


def anomaly_alert_event(component: str, severity: str, details: dict) -> CirvannaEvent:
    return CirvannaEvent(
        event_type=CirvannaEventType.ANOMALY_ALERT,
        payload={"component": component, "severity": severity, "details": details},
        priority="critical",
    )


def embedding_drift_event(index_name: str, drift_score: float, threshold: float) -> CirvannaEvent:
    return CirvannaEvent(
        event_type=CirvannaEventType.EMBEDDING_DRIFT_DETECTED,
        payload={"index": index_name, "drift_score": drift_score, "threshold": threshold},
        priority="high",
    )
