"""Durable Cirvanna Intelligence Layer registry and policy gateway.

The service stores source rights, evidence references and consented outcomes.
It is not a CAL replacement: serving assessments are advisory inputs and a
verified CAL SHOW receipt remains mandatory at the caller.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import DateTime, Float, Integer, JSON, String, Text, UniqueConstraint, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from app.provider import ProviderNotConfigured, fetch_licensed_research

SERVICE = "cirvanna-intelligence-service"
PURPOSES = {"research", "model_evaluation", "product_enrichment", "commercial_recommendation",
            "recommendation_outcome_learning", "training"}
GRADES = {"E1", "E2", "E3", "E4", "E5", "E6"}
TOKEN_RE = re.compile(r"^hmac-sha256:[0-9a-f]{64}$")


def now() -> datetime:
    return datetime.now(timezone.utc)


def make_engine():
    url = os.getenv("CIL_DATABASE_URL", "sqlite:///./cil.db")
    options = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
        if url in {"sqlite://", "sqlite:///:memory:"}:
            options["poolclass"] = StaticPool
    return create_engine(url, **options)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "cil_sources"
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    owner: Mapped[str] = mapped_column(String(180), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    locator: Mapped[str] = mapped_column(Text, nullable=False)
    rights_status: Mapped[str] = mapped_column(String(32), nullable=False)
    rights_reference: Mapped[str] = mapped_column(Text, nullable=False)
    permitted_purposes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    attribution_required: Mapped[bool] = mapped_column(nullable=False, default=True)
    attribution_text: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)


class Evidence(Base):
    __tablename__ = "cil_evidence"
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    grade: Mapped[str] = mapped_column(String(2), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    locator: Mapped[str] = mapped_column(Text, nullable=False)
    limitations: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)


class Outcome(Base):
    __tablename__ = "cil_recommendation_outcomes"
    __table_args__ = (UniqueConstraint("event_id", name="uq_cil_outcome_event"),)
    event_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    context_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    contributor_token: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    suitability: Mapped[str] = mapped_column(String(24), nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(240))
    candidate_id: Mapped[str] = mapped_column(String(120), nullable=False)
    consent_receipt_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    cal_receipt_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)


class CALReview(Base):
    __tablename__ = "cil_cal_review_queue"
    __table_args__ = (UniqueConstraint("product_id", "context_key", "status", name="uq_cil_cal_review_cohort_status"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    product_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    context_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    unsuitable_share: Mapped[float] = mapped_column(Float, nullable=False)
    contributor_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    verdict: Mapped[str | None] = mapped_column(String(12))
    decision_reference: Mapped[str | None] = mapped_column(String(240))
    rationale: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceIn(StrictModel):
    source_id: str = Field(min_length=3, max_length=120)
    owner: str = Field(min_length=2, max_length=180)
    kind: Literal["public_research", "licensed_research", "licensed_provider_api",
                  "manufacturer", "merchant", "regulatory", "customer_aggregate"]
    locator: str = Field(min_length=8, max_length=2000)
    rights_status: Literal["public_domain", "open_license", "licensed", "api_terms",
                           "research_only", "permission_required", "unknown", "prohibited"]
    rights_reference: str = Field(min_length=5, max_length=2000)
    permitted_purposes: list[str] = Field(default_factory=list, max_length=6)
    attribution_required: bool = True
    attribution_text: str | None = Field(default=None, max_length=1000)
    expires_at: datetime | None = None
    reviewed_at: datetime

    @field_validator("permitted_purposes")
    @classmethod
    def valid_purposes(cls, values):
        if len(values) != len(set(values)) or any(v not in PURPOSES for v in values):
            raise ValueError("purposes must be unique recognized CIL purposes")
        return values


class ProviderResearchIn(StrictModel):
    source_id: str = Field(min_length=3, max_length=120)
    evidence_id: str = Field(min_length=3, max_length=120)
    owner: str = Field(min_length=2, max_length=180)
    path: str = Field(min_length=1, max_length=500)
    params: dict[str, str] = Field(default_factory=dict, max_length=30)
    rights_status: Literal["licensed", "api_terms", "research_only"]
    rights_reference: str = Field(min_length=5, max_length=2000)
    permitted_purposes: list[str] = Field(default_factory=list, max_length=6)
    grade: str
    scope: Literal["finished_product", "ingredient", "model", "general"]
    limitations: str = Field(min_length=10, max_length=2000)
    reviewed_at: datetime

    @field_validator("grade")
    @classmethod
    def provider_grade(cls, value):
        if value not in GRADES:
            raise ValueError("unknown evidence grade")
        return value

    @field_validator("permitted_purposes")
    @classmethod
    def provider_purposes(cls, values):
        if len(values) != len(set(values)) or any(v not in PURPOSES for v in values):
            raise ValueError("purposes must be unique recognized CIL purposes")
        if any(v in {"commercial_recommendation", "product_enrichment", "training"} for v in values) and not values:
            raise ValueError("commercial purposes require an explicit licence")
        return values


class EvidenceIn(StrictModel):
    evidence_id: str = Field(min_length=3, max_length=120)
    source_id: str = Field(min_length=3, max_length=120)
    grade: str
    scope: Literal["finished_product", "ingredient", "model", "general"]
    locator: str = Field(min_length=8, max_length=2000)
    limitations: str = Field(min_length=10, max_length=2000)

    @field_validator("grade")
    @classmethod
    def valid_grade(cls, value):
        if value not in GRADES:
            raise ValueError("unknown evidence grade")
        return value


class ServingAssessmentIn(StrictModel):
    purpose: Literal["product_enrichment", "commercial_recommendation"]
    product_id: str = Field(min_length=1, max_length=120)
    catalog_version: int = Field(ge=1)
    claims: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    ingredient_declarations: list[dict[str, Any]] = Field(default_factory=list, max_length=250)


class CALDecisionIn(StrictModel):
    verdict: Literal["SHOW", "BLOCK"]
    decision_reference: str = Field(min_length=3, max_length=240)
    rationale: str = Field(min_length=10, max_length=2000)


class OutcomeIn(StrictModel):
    event_id: str = Field(min_length=3, max_length=120)
    product_id: str = Field(min_length=1, max_length=120)
    context_key: str = Field(min_length=1, max_length=120)
    contributor_token: str
    action: Literal["rejected", "ignored", "opened", "saved", "purchased"]
    suitability: Literal["suitable", "unsuitable", "uncertain", "not_reported"]
    reason_codes: list[str] = Field(default_factory=list, max_length=12)
    model_version: str | None = Field(default=None, max_length=240)
    candidate_id: str = Field(min_length=1, max_length=120)
    observed_at: datetime
    consent_receipt: str
    cal_decision_receipt: str

    @field_validator("contributor_token")
    @classmethod
    def pseudonymous_token(cls, value):
        if not TOKEN_RE.fullmatch(value):
            raise ValueError("contributor_token must be a keyed HMAC-SHA256 pseudonym")
        return value


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _admin(authorization: str | None = Header(default=None)):
    expected = os.getenv("CIL_ADMIN_TOKEN", "").strip()
    if not expected or authorization != f"Bearer {expected}":
        raise HTTPException(401, "CIL admin bearer token required")


def _service(authorization: str | None = Header(default=None)):
    expected = os.getenv("CIL_SERVICE_TOKEN", "").strip()
    if not expected or authorization != f"Bearer {expected}":
        raise HTTPException(401, "CIL service bearer token required")


def _cal_service(authorization: str | None = Header(default=None)):
    expected = os.getenv("CIL_CAL_SERVICE_TOKEN", "").strip()
    if not expected or authorization != f"Bearer {expected}":
        raise HTTPException(401, "CAL service bearer token required")


def _receipt(value: str, expected_type: str, product_id: str) -> dict:
    key = os.getenv("CIL_RECEIPT_SIGNING_KEY", "").encode()
    if len(key) < 32:
        raise HTTPException(503, "CIL receipt verification is not configured")
    try:
        encoded, signature = value.split(".", 1)
        payload_bytes = __import__("base64").urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        payload = json.loads(payload_bytes)
    except Exception as exc:
        raise HTTPException(422, "Malformed signed receipt") from exc
    expected = hmac.new(key, encoded.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(403, "Invalid receipt signature")
    if payload.get("type") != expected_type or payload.get("product_id") != product_id:
        raise HTTPException(403, "Receipt scope does not match the event")
    if int(payload.get("expires_at", 0)) <= int(now().timestamp()):
        raise HTTPException(403, "Receipt expired")
    if expected_type == "consent" and payload.get("purpose") != "recommendation_outcome_learning":
        raise HTTPException(403, "Consent is not scoped to outcome learning")
    if expected_type == "cal" and payload.get("verdict") != "SHOW":
        raise HTTPException(403, "CAL receipt must authorize SHOW")
    return payload


def _source_permits(db: Session, source_id: str, purpose: str) -> tuple[bool, str]:
    source = db.get(Source, source_id)
    if source is None:
        return False, "SOURCE_NOT_REGISTERED"
    expiry = source.expires_at
    if expiry and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if source.rights_status not in {"public_domain", "open_license", "licensed", "api_terms"}:
        return False, "SOURCE_RIGHTS_NOT_COMMERCIAL"
    if expiry and expiry <= now():
        return False, "SOURCE_RIGHTS_EXPIRED"
    if purpose not in (source.permitted_purposes or []):
        return False, "PURPOSE_NOT_LICENSED"
    return True, "SOURCE_RIGHTS_VALID"


app = FastAPI(title="Cirvanna Intelligence Service", version="0.2.0")


@app.on_event("startup")
def create_schema():
    # For local/demo only. Production must provision tables with reviewed migrations.
    if os.getenv("CIL_AUTO_CREATE_SCHEMA", "true").lower() == "true":
        Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "alive", "service": SERVICE}


@app.get("/ready")
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(select(Source.id).limit(1))
    except Exception as exc:
        raise HTTPException(503, "CIL database unavailable") from exc
    return {"status": "ready", "database": "connected"}


@app.post("/sources", dependencies=[Depends(_admin)], status_code=201)
def register_source(payload: SourceIn, db: Session = Depends(get_db)):
    if payload.source_id in {row[0] for row in db.execute(select(Source.id)).all()}:
        raise HTTPException(409, "source_id already exists; source rights are immutable")
    if payload.rights_status in {"research_only", "permission_required", "unknown", "prohibited"}:
        if set(payload.permitted_purposes) - {"research", "model_evaluation"}:
            raise HTTPException(422, "restricted source cannot be used for commercial purposes")
    row = Source(**payload.model_dump())
    db.add(row)
    db.commit()
    return {"source_id": row.id, "rights_status": row.rights_status, "permitted_purposes": row.permitted_purposes}


@app.post("/providers/research", dependencies=[Depends(_admin)], status_code=201)
def ingest_licensed_provider_research(payload: ProviderResearchIn, db: Session = Depends(get_db)):
    """Fetch a contract-authorized JSON response and register its provenance.

    The payload itself is returned to the authenticated operator, not copied into
    the CIL evidence ledger. Only source/evidence references and limitations persist.
    """
    if db.get(Source, payload.source_id) or db.get(Evidence, payload.evidence_id):
        raise HTTPException(409, "source_id or evidence_id already exists")
    try:
        provider_result = fetch_licensed_research(path=payload.path, params=payload.params)
    except ProviderNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, "Licensed provider request failed") from exc
    if payload.rights_status == "research_only" and set(payload.permitted_purposes) - {"research", "model_evaluation"}:
        raise HTTPException(422, "research-only provider licence cannot authorize commercial use")
    provider_base = os.getenv("CIL_PROVIDER_BASE_URL", "").rstrip("/")
    source = Source(
        id=payload.source_id, owner=payload.owner, kind="licensed_provider_api",
        locator=f"{provider_base}/{payload.path}", rights_status=payload.rights_status,
        rights_reference=f"{payload.rights_reference} | {provider_result['terms_url']} | {provider_result['licence_id']}",
        permitted_purposes=payload.permitted_purposes, attribution_required=True,
        attribution_text=payload.owner, reviewed_at=payload.reviewed_at,
    )
    evidence = Evidence(
        id=payload.evidence_id, source_id=payload.source_id, grade=payload.grade,
        scope=payload.scope, locator=f"{provider_base}/{payload.path}",
        limitations=payload.limitations,
    )
    db.add(source)
    db.add(evidence)
    db.commit()
    return {"source_id": source.id, "evidence_id": evidence.id, "rights_status": source.rights_status,
            "permitted_purposes": source.permitted_purposes, "provider_payload": provider_result["payload"]}


@app.post("/evidence", dependencies=[Depends(_admin)], status_code=201)
def register_evidence(payload: EvidenceIn, db: Session = Depends(get_db)):
    if db.get(Evidence, payload.evidence_id):
        raise HTTPException(409, "evidence_id already exists; evidence records are immutable")
    if db.get(Source, payload.source_id) is None:
        raise HTTPException(422, "source_id is not registered")
    row = Evidence(**payload.model_dump())
    db.add(row)
    db.commit()
    return {"evidence_id": row.id, "source_id": row.source_id, "grade": row.grade, "scope": row.scope}


@app.post("/serving/assessment", dependencies=[Depends(_service)])
def assess_serving(payload: ServingAssessmentIn, db: Session = Depends(get_db)):
    """Return claim-level eligibility; unknown or unlicensed evidence fails closed."""
    decisions = []
    for kind, records in (("claim", payload.claims), ("ingredient", payload.ingredient_declarations)):
        for item in records:
            evidence = item.get("evidence") or {}
            evidence_id = evidence.get("evidence_id") or evidence.get("id")
            source_id = evidence.get("source_id")
            evidence_row = db.get(Evidence, evidence_id) if isinstance(evidence_id, str) else None
            if evidence_row is None and source_id:
                evidence_row = db.scalar(select(Evidence).where(Evidence.source_id == source_id).limit(1))
            if evidence_row is None:
                decisions.append({"item_id": item.get("claim_id", item.get("inci_name", "unknown")),
                                  "kind": kind, "eligible": False, "reason": "EVIDENCE_NOT_REGISTERED"})
                continue
            allowed, reason = _source_permits(db, evidence_row.source_id, payload.purpose)
            requested_scope = evidence.get("scope")
            claim_type = item.get("claim_type")
            required_scope = "finished_product" if kind == "ingredient" or claim_type == "finished_product_efficacy" else requested_scope
            scope_ok = (not required_scope or required_scope == evidence_row.scope) and (not requested_scope or requested_scope == evidence_row.scope)
            if evidence.get("source_id") and evidence.get("source_id") != evidence_row.source_id:
                scope_ok = False
            grade_ok = evidence_row.grade in ({"E1", "E2", "E4"} if claim_type == "finished_product_efficacy"
                                              else {"E1", "E2", "E3", "E4", "E5"})
            eligible = allowed and scope_ok and grade_ok
            decisions.append({"item_id": item.get("claim_id", item.get("inci_name", "unknown")),
                              "kind": kind, "eligible": eligible,
                              "reason": reason if not allowed else ("EVIDENCE_SCOPE_OR_GRADE_MISMATCH" if not (scope_ok and grade_ok) else "ELIGIBLE"),
                              "evidence_id": evidence_row.id})
    return {"product_id": payload.product_id, "catalog_version": payload.catalog_version,
            "purpose": payload.purpose, "decisions": decisions,
            "all_eligible": all(item["eligible"] for item in decisions)}


@app.post("/outcomes", dependencies=[Depends(_service)], status_code=201)
def record_outcome(payload: OutcomeIn, db: Session = Depends(get_db)):
    consent = _receipt(payload.consent_receipt, "consent", payload.product_id)
    cal = _receipt(payload.cal_decision_receipt, "cal", payload.product_id)
    if consent.get("subject_token") != payload.contributor_token:
        raise HTTPException(403, "Consent subject does not match the pseudonymous contributor")
    if cal.get("candidate_id") != payload.candidate_id:
        raise HTTPException(403, "CAL receipt candidate does not match the recommendation event")
    if payload.suitability == "not_reported" and payload.reason_codes:
        raise HTTPException(422, "reason codes require an explicit suitability report")
    if db.get(Outcome, payload.event_id):
        raise HTTPException(409, "event_id already recorded")
    row = Outcome(
        event_id=payload.event_id, product_id=payload.product_id, context_key=payload.context_key,
        contributor_token=payload.contributor_token, action=payload.action, suitability=payload.suitability,
        reason_codes=payload.reason_codes, model_version=payload.model_version, candidate_id=payload.candidate_id,
        consent_receipt_digest=hashlib.sha256(payload.consent_receipt.encode()).hexdigest(),
        cal_receipt_digest=hashlib.sha256(payload.cal_decision_receipt.encode()).hexdigest(),
        observed_at=payload.observed_at,
    )
    db.add(row)
    db.commit()
    return {"event_id": row.event_id, "stored": True, "consent_subject": consent.get("subject_token"),
            "cal_decision_id": cal.get("decision_id")}


@app.get("/outcomes/aggregate", dependencies=[Depends(_service)])
def aggregate_outcomes(product_id: str, context_key: str, db: Session = Depends(get_db)):
    rows = list(db.scalars(select(Outcome).where(
        Outcome.product_id == product_id, Outcome.context_key == context_key
    )).all())
    reported = [row for row in rows if row.suitability in {"suitable", "unsuitable"}]
    contributors = {row.contributor_token for row in reported}
    if len(contributors) < 30:
        return {"status": "suppressed", "minimum_contributors": 30, "contributor_count": len(contributors)}
    # One contributor counts once per cohort; duplicate reports cannot inflate the denominator.
    unique = {}
    for row in reported:
        unique.setdefault(row.contributor_token, row)
    suitable = sum(row.suitability == "suitable" for row in unique.values())
    unsuitable = sum(row.suitability == "unsuitable" for row in unique.values())
    denominator = suitable + unsuitable
    share = unsuitable / denominator if denominator else None
    threshold = float(os.getenv("CIL_UNSUITABLE_SHARE_REVIEW_THRESHOLD", "0.25"))
    if not 0.0 <= threshold <= 1.0:
        raise HTTPException(503, "CIL_UNSUITABLE_SHARE_REVIEW_THRESHOLD must be between 0 and 1")
    review_id = None
    review_status = None
    if share is not None and share >= threshold:
        pending = db.scalar(select(CALReview).where(
            CALReview.product_id == product_id,
            CALReview.context_key == context_key,
            CALReview.status == "pending",
        ))
        if pending is None:
            pending = CALReview(
                product_id=product_id, context_key=context_key, unsuitable_share=share,
                contributor_count=len(contributors), status="pending",
            )
            db.add(pending)
            db.commit()
            db.refresh(pending)
        review_id, review_status = pending.id, pending.status
    return {"status": "review_required" if share is not None and share >= threshold else "collecting",
            "contributor_count": len(contributors), "reported_count": denominator,
            "suitable_count": suitable, "unsuitable_count": unsuitable,
            "unsuitable_share": share,
            "cal_action": "REVIEW_REQUESTED" if review_id else "NO_CHANGE",
            "cal_review_id": review_id, "cal_review_status": review_status,
            "automatic_suppression": False}


@app.get("/cal/review-queue", dependencies=[Depends(_service)])
def cal_review_queue(db: Session = Depends(get_db)):
    rows = list(db.scalars(select(CALReview).where(CALReview.status == "pending")
                           .order_by(CALReview.created_at.asc()).limit(100)).all())
    return {"items": [{
        "review_id": row.id, "product_id": row.product_id, "context_key": row.context_key,
        "unsuitable_share": row.unsuitable_share, "contributor_count": row.contributor_count,
        "status": row.status, "created_at": row.created_at.isoformat(),
    } for row in rows]}


@app.post("/cal/review-queue/{review_id}/decision", dependencies=[Depends(_cal_service)])
def record_cal_decision(review_id: str, payload: CALDecisionIn, db: Session = Depends(get_db)):
    review = db.get(CALReview, review_id)
    if review is None:
        raise HTTPException(404, "CAL review request not found")
    if review.status != "pending":
        if review.decision_reference == payload.decision_reference and review.verdict == payload.verdict:
            return {"review_id": review.id, "status": review.status, "verdict": review.verdict}
        raise HTTPException(409, "CAL review request already has a final decision")
    review.status = "decided"
    review.verdict = payload.verdict
    review.decision_reference = payload.decision_reference
    review.rationale = payload.rationale
    review.decided_at = now()
    db.commit()
    return {"review_id": review.id, "status": review.status, "verdict": review.verdict,
            "decision_reference": review.decision_reference}


@app.get("/capabilities")
def capabilities():
    return {"durable_source_registry": True, "durable_evidence_registry": True,
            "consent_and_cal_receipt_verification": bool(os.getenv("CIL_RECEIPT_SIGNING_KEY")),
            "licensed_provider_adapter_configurable": all(os.getenv(k) for k in (
                "CIL_PROVIDER_BASE_URL", "CIL_PROVIDER_API_TOKEN", "CIL_PROVIDER_LICENCE_ID", "CIL_PROVIDER_TERMS_URL")),
            "catalog_serving_gateway_required": True, "cal_remains_final_authority": True}
