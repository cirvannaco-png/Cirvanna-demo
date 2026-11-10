"""Cirvanna canonical product catalog API foundation.

This service owns product identity and catalog metadata. It deliberately does not
implement checkout, payments, fit prediction, personalized ranking, or rendering.
"""
from __future__ import annotations

import hashlib
import httpx
import hmac
import json
import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Any, Iterator, Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
    inspect,
    or_,
    select,
    text,
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from starlette import status
from starlette.responses import Response

from app.product_intelligence import validate_product_intelligence_attributes


SERVICE_NAME = "cirvanna-catalog-service"
EXPECTED_SCHEMA_REVISION = "20261104_0002"
MAX_PAGE_SIZE = 100
MAX_IMAGE_URLS = 20
MAX_ATTRIBUTES = 100
SKU_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,79}$")
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _database_url() -> str:
    return os.getenv("CATALOG_DATABASE_URL", "sqlite:///./catalog.db")


def _build_engine(database_url: str):
    options: dict[str, Any] = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    return create_engine(database_url, **options)


engine = _build_engine(_database_url())
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "catalog_products"
    __table_args__ = (
        UniqueConstraint("sku", name="uq_catalog_products_sku"),
        Index("ix_catalog_products_status_category", "status", "category"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sku: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    price_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    image_urls: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", index=True)
    catalog_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class ProductVersion(Base):
    __tablename__ = "catalog_product_versions"
    __table_args__ = (UniqueConstraint("product_id", "version", name="uq_catalog_product_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("catalog_products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    change_type: Mapped[str] = mapped_column(String(24), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)


class ProductVariant(Base):
    """Catalog-owned immutable purchasable variant identity."""
    __tablename__ = "catalog_product_variants"
    __table_args__ = (
        UniqueConstraint("product_id", "identity_key", name="uq_catalog_variant_product_identity"),
        Index("ix_catalog_variant_product_status", "product_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("catalog_products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attributes: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    identity_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    variant_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _normalize_sku(value: str) -> str:
    normalized = value.strip().upper()
    if not SKU_PATTERN.fullmatch(normalized):
        raise ValueError("SKU must be 1-80 characters using letters, digits, dot, underscore, or hyphen.")
    return normalized


def _normalize_currency(value: str) -> str:
    normalized = value.strip().upper()
    if not CURRENCY_PATTERN.fullmatch(normalized):
        raise ValueError("Currency must be a three-letter ISO-style code.")
    return normalized


def _validate_image_urls(value: list[str]) -> list[str]:
    if len(value) > MAX_IMAGE_URLS:
        raise ValueError(f"No more than {MAX_IMAGE_URLS} image URLs are allowed.")
    normalized: list[str] = []
    for raw in value:
        candidate = raw.strip()
        parts = urlsplit(candidate)
        if len(candidate) > 2048 or parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError("Image URLs must be absolute HTTP(S) URLs no longer than 2048 characters.")
        if parts.username is not None or parts.password is not None:
            raise ValueError("Image URLs must not embed credentials.")
        normalized.append(candidate)
    return normalized


def _validate_attributes(value: dict[str, Any]) -> dict[str, Any]:
    if len(value) > MAX_ATTRIBUTES:
        raise ValueError(f"No more than {MAX_ATTRIBUTES} attribute keys are allowed.")
    if any(not key.strip() or len(key) > 64 for key in value):
        raise ValueError("Attribute keys must contain 1-64 non-whitespace characters.")
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("Attributes must be finite JSON-compatible values.") from exc
    return validate_product_intelligence_attributes(value)


def _normalize_variant_attributes(value: dict[str, str]) -> dict[str, str]:
    """Normalize identity-defining option labels/values without fuzzy matching."""
    if not value or len(value) > 20:
        raise ValueError("A variant requires 1-20 identity-defining attributes.")
    normalized: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        key = re.sub(r"[\s-]+", "_", raw_key.strip().casefold())
        item = re.sub(r"\s+", " ", raw_value.strip().casefold())
        if not re.fullmatch(r"[a-z0-9_]{1,64}", key) or not item or len(item) > 120:
            raise ValueError("Variant attribute keys/values are invalid.")
        if key in normalized:
            raise ValueError("Variant attribute keys collide after normalization.")
        normalized[key] = item
    return dict(sorted(normalized.items()))


def _variant_identity_key(attributes: dict[str, str]) -> str:
    canonical = json.dumps(attributes, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _variant_json(variant: ProductVariant) -> dict[str, Any]:
    return {
        "variant_id": variant.id,
        "product_id": variant.product_id,
        "attributes": variant.attributes,
        "status": variant.status,
        "variant_version": variant.variant_version,
        "created_at": variant.created_at,
        "updated_at": variant.updated_at,
    }


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=10000)
    category: str = Field(min_length=1, max_length=80)
    brand: str | None = Field(default=None, max_length=100)
    price_minor: int = Field(ge=0, le=2_000_000_000, description="Price in the smallest currency unit, such as cents.")
    currency: str = Field(min_length=3, max_length=3)
    attributes: dict[str, Any] = Field(default_factory=dict)
    image_urls: list[str] = Field(default_factory=list)

    @field_validator("sku")
    @classmethod
    def validate_sku(cls, value: str) -> str:
        return _normalize_sku(value)

    @field_validator("name", "category", "brand", mode="before")
    @classmethod
    def trim_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return _normalize_currency(value)

    @field_validator("image_urls")
    @classmethod
    def validate_urls(cls, value: list[str]) -> list[str]:
        return _validate_image_urls(value)

    @field_validator("attributes")
    @classmethod
    def validate_attrs(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_attributes(value)


class CanonicalVariantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attributes: dict[str, str] = Field(min_length=1, max_length=20)

    @field_validator("attributes")
    @classmethod
    def normalize_attributes(cls, value: dict[str, str]) -> dict[str, str]:
        return _normalize_variant_attributes(value)


class ProductPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str | None = Field(default=None, min_length=1, max_length=80)
    name: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=10000)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    brand: str | None = Field(default=None, max_length=100)
    price_minor: int | None = Field(default=None, ge=0, le=2_000_000_000)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    attributes: dict[str, Any] | None = None
    image_urls: list[str] | None = None
    status: Literal["active", "archived"] | None = None

    @field_validator("sku")
    @classmethod
    def validate_sku(cls, value: str | None) -> str | None:
        return _normalize_sku(value) if value is not None else value

    @field_validator("name", "category", "brand", mode="before")
    @classmethod
    def trim_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str | None) -> str | None:
        return _normalize_currency(value) if value is not None else value

    @field_validator("image_urls")
    @classmethod
    def validate_urls(cls, value: list[str] | None) -> list[str] | None:
        return _validate_image_urls(value) if value is not None else value

    @field_validator("attributes")
    @classmethod
    def validate_attrs(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return _validate_attributes(value) if value is not None else value


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    product_id: str = Field(validation_alias="id")
    sku: str
    name: str
    description: str | None
    category: str
    brand: str | None
    price_minor: int
    currency: str
    attributes: dict[str, Any]
    image_urls: list[str]
    status: Literal["active", "archived"]
    catalog_version: int
    created_at: datetime
    updated_at: datetime


class ProductListOut(BaseModel):
    items: list[ProductOut]
    total: int
    offset: int
    limit: int


class ProductBatchOut(BaseModel):
    """Canonical catalog records fetched in a bounded internal batch."""
    items: list[ProductOut]


class ProductVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    version_id: int = Field(validation_alias="id")
    catalog_version: int = Field(validation_alias="version")
    change_type: str
    snapshot: dict[str, Any]
    created_at: datetime


class ReadinessOut(BaseModel):
    status: str
    service: str
    database_connected: bool
    schema_present: bool
    authentication_configured: bool
    migrations_required: bool
    migrations_applied: bool
    schema_revision: str | None
    ready: bool


bearer = HTTPBearer(auto_error=False)


def _catalog_production_mode() -> bool:
    return os.getenv("CATALOG_ENVIRONMENT", "development").strip().lower() == "production"


def _catalog_expected_token(scope: str) -> str:
    production = _catalog_production_mode()
    read_token = os.getenv("CATALOG_READ_TOKEN", "").strip()
    write_token = os.getenv("CATALOG_WRITE_TOKEN", "").strip()
    if production:
        # Separate credentials limit the blast radius of the Commerce read credential.
        if not read_token or not write_token or hmac.compare_digest(read_token, write_token):
            return ""
        return read_token if scope == "read" else write_token
    # One legacy token remains convenient for local tests/development only.
    scoped = read_token if scope == "read" else write_token
    return scoped or os.getenv("CATALOG_API_TOKEN", "")


def _require_catalog_scope(
    scope: str,
    credentials: HTTPAuthorizationCredentials | None,
) -> None:
    expected = _catalog_expected_token(scope)
    if not expected or credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Configured {scope}-scoped catalog bearer authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token for the required catalog scope.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_catalog_read_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    _require_catalog_scope("read", credentials)


def require_catalog_write_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    _require_catalog_scope("write", credentials)


def _catalog_auth_configured() -> bool:
    if _catalog_production_mode():
        read_token = os.getenv("CATALOG_READ_TOKEN", "").strip()
        write_token = os.getenv("CATALOG_WRITE_TOKEN", "").strip()
        return bool(read_token and write_token and not hmac.compare_digest(read_token, write_token))
    return bool(_catalog_expected_token("read") and _catalog_expected_token("write"))


# Compatibility name for callers that imported the former generic guard: it is read-only.
def require_catalog_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    require_catalog_read_token(credentials)


def _snapshot(product: Product) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "product_id": product.id,
        "sku": product.sku,
        "name": product.name,
        "description": product.description,
        "category": product.category,
        "brand": product.brand,
        "price_minor": product.price_minor,
        "currency": product.currency,
        "attributes": product.attributes,
        "image_urls": product.image_urls,
        "status": product.status,
        "catalog_version": product.catalog_version,
        "created_at": product.created_at.isoformat() if product.created_at else None,
        "updated_at": product.updated_at.isoformat() if product.updated_at else None,
    }


def _record_version(db: Session, product: Product, change_type: str) -> None:
    db.add(
        ProductVersion(
            product_id=product.id,
            version=product.catalog_version,
            change_type=change_type,
            snapshot=_snapshot(product),
        )
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Bootstrap convenience for local/demo use. Production should use a reviewed,
    # versioned database migration process and set CATALOG_AUTO_CREATE_SCHEMA=false.
    if os.getenv("CATALOG_AUTO_CREATE_SCHEMA", "true").lower() == "true":
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Cirvanna Catalog Service",
    version="0.1.0",
    description=(
        "Canonical product identity and metadata. This is not a checkout, "
        "payment, fit-prediction, personalized-ranking, or try-on service."
    ),
    lifespan=lifespan,
)

# Cross-origin browser access is opt-in. Configure exact trusted frontend origins in
# CATALOG_CORS_ORIGINS (comma-separated); never use a wildcard for authenticated APIs.
_cors_origins = [origin.strip().rstrip("/") for origin in os.getenv("CATALOG_CORS_ORIGINS", "").split(",") if origin.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["Authorization", "Accept"],
        max_age=600,
    )


async def _cil_gate_node(node: Any, client: httpx.AsyncClient, gateway: str, token: str) -> None:
    """Fail closed for CIL metadata on every Catalog GET representation."""
    if isinstance(node, list):
        await __import__("asyncio").gather(*[
            _cil_gate_node(item, client, gateway, token) for item in node if isinstance(item, (dict, list))
        ])
        return
    if not isinstance(node, dict):
        return
    attributes = node.get("attributes")
    intelligence = attributes.get("product_intelligence") if isinstance(attributes, dict) else None
    if isinstance(intelligence, dict):
        claims = intelligence.get("claims", [])
        ingredients = intelligence.get("ingredient_declarations", [])
        if not gateway or not token or not (claims or ingredients):
            attributes.pop("product_intelligence", None)
        else:
            def bind_evidence(item: dict[str, Any]) -> dict[str, Any]:
                result = dict(item)
                evidence = dict(result.get("evidence") or {})
                evidence["evidence_id"] = evidence.get("evidence_id") or evidence.get("reference")
                result["evidence"] = evidence
                return result
            request_payload = {
                "purpose": "commercial_recommendation",
                "product_id": str(node.get("product_id") or node.get("id") or ""),
                "catalog_version": int(node.get("catalog_version") or 1),
                "claims": [bind_evidence(item) for item in claims],
                "ingredient_declarations": [bind_evidence(item) for item in ingredients],
            }
            try:
                response = await client.post(
                    f"{gateway.rstrip('/')}/serving/assessment",
                    json=request_payload,
                    headers={"Authorization": f"Bearer {token}"},
                )
                response.raise_for_status()
                assessment = response.json()
                expected_count = len(claims) + len(ingredients)
                decisions = assessment.get("decisions", [])
                expected_items = [
                    (item, "claim", item.get("claim_id")) for item in claims
                ] + [
                    (item, "ingredient", item.get("inci_name")) for item in ingredients
                ]
                if (
                    assessment.get("product_id") != request_payload["product_id"]
                    or assessment.get("catalog_version") != request_payload["catalog_version"]
                    or len(decisions) != expected_count
                    or any(
                        decision.get("item_id") != expected_id
                        or decision.get("kind") != expected_kind
                        or not isinstance(decision.get("eligible"), bool)
                        for decision, (_, expected_kind, expected_id) in zip(decisions, expected_items)
                    )
                ):
                    attributes.pop("product_intelligence", None)
                else:
                    # Filter item-by-item; pending claims never pass, while independently
                    # evidenced ingredients may still be served with required attribution.
                    approved_claims = []
                    approved_ingredients = []
                    for decision, (item, kind, _) in zip(decisions, expected_items):
                        if not decision.get("eligible"):
                            continue
                        evidence = dict(item.get("evidence") or {})
                        if decision.get("attribution_required"):
                            evidence["attribution"] = decision.get("attribution_text")
                            evidence["source_owner"] = decision.get("source_owner")
                        item["evidence"] = evidence
                        (approved_claims if kind == "claim" else approved_ingredients).append(item)
                    if not approved_claims and not approved_ingredients:
                        attributes.pop("product_intelligence", None)
                    else:
                        attributes["product_intelligence"] = {
                            "schema_version": intelligence.get("schema_version", "1.0"),
                            "claims": approved_claims,
                            "ingredient_declarations": approved_ingredients,
                        }
            except (httpx.HTTPError, ValueError, TypeError, KeyError):
                attributes.pop("product_intelligence", None)
    await __import__("asyncio").gather(*[
        _cil_gate_node(value, client, gateway, token)
        for key, value in node.items()
        if key != "attributes" and isinstance(value, (dict, list))
    ])


@app.middleware("http")
async def enforce_cil_before_catalog_serving(request: Request, call_next):
    response = await call_next(request)
    if request.method != "GET" or not request.url.path.startswith(("/products", "/variants")):
        return response
    body = b"".join([chunk async for chunk in response.body_iterator])
    if response.status_code >= 400:
        return Response(content=body, status_code=response.status_code, headers={
            key: value for key, value in response.headers.items()
            if key.lower() not in {"content-length", "content-encoding", "transfer-encoding"}
        })
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return Response(content=body, status_code=response.status_code, media_type="application/json")
    gateway = os.getenv("CIL_GATEWAY_URL", "").strip()
    token = os.getenv("CIL_SERVICE_TOKEN", "").strip()
    async with httpx.AsyncClient(timeout=httpx.Timeout(2.0, connect=1.0), follow_redirects=False) as client:
        await _cil_gate_node(payload, client, gateway, token)
    return Response(
        content=json.dumps(payload, separators=(",", ":"), default=str),
        status_code=response.status_code,
        media_type="application/json",
    )


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    """Liveness only; it does not promise database readiness."""
    return {"status": "alive", "service": SERVICE_NAME}


@app.get("/ready", response_model=ReadinessOut, tags=["operations"])
def readiness(db: Annotated[Session, Depends(get_db)]) -> ReadinessOut:
    """Readiness requires a reachable DB, expected schema and deployment auth config."""
    configured = _catalog_auth_configured()
    migrations_required = os.getenv("CATALOG_AUTO_CREATE_SCHEMA", "true").lower() != "true"
    connected = False
    schema_present = False
    schema_revision = None
    try:
        db.execute(text("SELECT 1"))
        connected = True
        table_names = set(inspect(db.get_bind()).get_table_names())
        schema_present = set(Base.metadata.tables).issubset(table_names)
        if "alembic_version" in table_names:
            schema_revision = db.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            ).scalar_one_or_none()
    except SQLAlchemyError:
        # Never turn a failed connection/schema probe into a successful health check.
        connected = False
        schema_present = False

    migrations_applied = schema_revision == EXPECTED_SCHEMA_REVISION
    is_ready = (
        connected
        and schema_present
        and configured
        and (not migrations_required or migrations_applied)
    )
    result = ReadinessOut(
        status="ready" if is_ready else "not_ready",
        service=SERVICE_NAME,
        database_connected=connected,
        schema_present=schema_present,
        authentication_configured=configured,
        migrations_required=migrations_required,
        migrations_applied=migrations_applied,
        schema_revision=schema_revision,
        ready=is_ready,
    )
    if not is_ready:
        raise HTTPException(status_code=503, detail=result.model_dump())
    return result


@app.get("/capabilities", tags=["operations"])
def capabilities() -> dict[str, Any]:
    return {
        "service": SERVICE_NAME,
        "canonical_product_identity": True,
        "canonical_product_variant_identity": True,
        "trusted_variant_lookup": True,
        "validated_product_metadata": True,
        "catalog_persistence": True,
        "product_version_history": True,
        "versioned_migrations_available": True,
        "product_search_and_listing": True,
        "merchant_bulk_import": False,
        "checkout": False,
        "payments": False,
        "fit_prediction": False,
        "personalized_ranking": False,
        "click_it_reconstruction": False,
        "virtual_try_on": False,
        "production_migrations_configured": False,
    }


@app.post(
    "/products",
    response_model=ProductOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_catalog_write_token)],
    tags=["products"],
)
def create_product(payload: ProductCreate, db: Annotated[Session, Depends(get_db)]) -> Product:
    product = Product(
        id=str(uuid.uuid4()),
        sku=payload.sku,
        name=payload.name,
        description=payload.description,
        category=payload.category,
        brand=payload.brand,
        price_minor=payload.price_minor,
        currency=payload.currency,
        attributes=payload.attributes,
        image_urls=payload.image_urls,
        status="active",
        catalog_version=1,
    )
    db.add(product)
    try:
        db.flush()
        _record_version(db, product, "created")
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SKU already exists.") from exc
    db.refresh(product)
    return product


@app.get(
    "/products",
    response_model=ProductListOut,
    dependencies=[Depends(require_catalog_read_token)],
    tags=["products"],
)
def list_products(
    db: Annotated[Session, Depends(get_db)],
    q: str | None = Query(default=None, max_length=160),
    category: str | None = Query(default=None, max_length=80),
    status_filter: Literal["active", "archived", "all"] = Query(default="active", alias="status"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
) -> ProductListOut:
    filters = []
    if status_filter != "all":
        filters.append(Product.status == status_filter)
    if category:
        filters.append(func.lower(Product.category) == category.strip().lower())
    if q and q.strip():
        term = f"%{q.strip()}%"
        # Descriptions and categories matter for semantic marketplace discovery;
        # this SQL substring search remains a fallback, not an embedding ranking.
        filters.append(or_(
            Product.name.ilike(term), Product.sku.ilike(term), Product.brand.ilike(term),
            Product.description.ilike(term), Product.category.ilike(term),
        ))
    statement = select(Product).where(*filters)
    total = db.scalar(select(func.count()).select_from(Product).where(*filters)) or 0
    items = list(db.scalars(statement.order_by(Product.created_at.desc(), Product.id).offset(offset).limit(limit)).all())
    return ProductListOut(items=items, total=int(total), offset=offset, limit=limit)


@app.get(
    "/products/batch",
    response_model=ProductBatchOut,
    dependencies=[Depends(require_catalog_read_token)],
    tags=["products"],
)
def get_products_batch(
    db: Annotated[Session, Depends(get_db)],
    ids: list[uuid.UUID] = Query(..., description="One or more canonical product UUIDs; maximum 100."),
) -> ProductBatchOut:
    """Bounded, read-only product enrichment endpoint for trusted retrieval services.

    Archived or unknown records are omitted. It does not expose archived product
    metadata to the marketplace semantic search service.
    """
    if not ids or len(ids) > MAX_PAGE_SIZE:
        raise HTTPException(status_code=422, detail={"code": "INVALID_BATCH_SIZE", "maximum": MAX_PAGE_SIZE})
    unique_ids = list(dict.fromkeys(str(pid) for pid in ids))
    products = list(db.scalars(select(Product).where(
        Product.id.in_(unique_ids), Product.status == "active"
    )).all())
    by_id = {product.id: product for product in products}
    ordered = [by_id[pid] for pid in unique_ids if pid in by_id]
    return ProductBatchOut(items=ordered)


def _get_product(db: Session, product_id: uuid.UUID) -> Product:
    product = db.get(Product, str(product_id))
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
    return product


@app.get(
    "/products/{product_id}",
    response_model=ProductOut,
    dependencies=[Depends(require_catalog_read_token)],
    tags=["products"],
)
def get_product(product_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]) -> Product:
    return _get_product(db, product_id)


@app.patch(
    "/products/{product_id}",
    response_model=ProductOut,
    dependencies=[Depends(require_catalog_write_token)],
    tags=["products"],
)
def update_product(
    product_id: uuid.UUID,
    payload: ProductPatch,
    db: Annotated[Session, Depends(get_db)],
    expected_version: int | None = Query(default=None, ge=1),
) -> Product:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="At least one field must be supplied.")
    product = _get_product(db, product_id)
    if expected_version is not None and product.catalog_version != expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "STALE_CATALOG_VERSION", "current_version": product.catalog_version},
        )
    for key, value in changes.items():
        if isinstance(value, str) and key in {"name", "category", "brand"}:
            value = value.strip()
        setattr(product, key, value)
    product.catalog_version += 1
    product.updated_at = _now()
    change_type = "status_changed" if set(changes) == {"status"} else "updated"
    try:
        db.flush()
        _record_version(db, product, change_type)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SKU already exists.") from exc
    db.refresh(product)
    return product


@app.delete(
    "/products/{product_id}",
    response_model=ProductOut,
    dependencies=[Depends(require_catalog_write_token)],
    tags=["products"],
)
def archive_product(
    product_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    expected_version: int | None = Query(default=None, ge=1),
) -> Product:
    product = _get_product(db, product_id)
    if expected_version is not None and product.catalog_version != expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "STALE_CATALOG_VERSION", "current_version": product.catalog_version},
        )
    if product.status != "archived":
        product.status = "archived"
        product.catalog_version += 1
        product.updated_at = _now()
        _record_version(db, product, "archived")
        db.commit()
        db.refresh(product)
    return product


@app.post(
    "/products/{product_id}/variants",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_catalog_write_token)],
    tags=["variants"],
)
def create_product_variant(
    product_id: uuid.UUID,
    payload: CanonicalVariantCreate,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    product = _get_product(db, product_id)
    if product.status != "active":
        raise HTTPException(status_code=409, detail={"code": "PRODUCT_NOT_ACTIVE"})
    identity_key = _variant_identity_key(payload.attributes)
    variant = ProductVariant(
        id=str(uuid.uuid4()),
        product_id=product.id,
        attributes=payload.attributes,
        identity_key=identity_key,
        status="active",
        variant_version=1,
    )
    db.add(variant)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail={"code": "CANONICAL_VARIANT_ALREADY_EXISTS"}) from exc
    db.refresh(variant)
    return _variant_json(variant)


@app.get(
    "/products/{product_id}/variants",
    dependencies=[Depends(require_catalog_read_token)],
    tags=["variants"],
)
def list_product_variants(
    product_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    product = _get_product(db, product_id)
    if product.status != "active":
        raise HTTPException(status_code=404, detail={"code": "PRODUCT_NOT_FOUND"})
    variants = list(db.scalars(
        select(ProductVariant)
        .where(ProductVariant.product_id == product.id, ProductVariant.status == "active")
        .order_by(ProductVariant.created_at.asc(), ProductVariant.id.asc())
    ).all())
    return {"items": [_variant_json(item) for item in variants], "total": len(variants)}


@app.get(
    "/variants/{variant_id}",
    dependencies=[Depends(require_catalog_read_token)],
    tags=["variants"],
)
def get_canonical_variant(
    variant_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    variant = db.get(ProductVariant, str(variant_id))
    if variant is None or variant.status != "active":
        raise HTTPException(status_code=404, detail={"code": "CANONICAL_VARIANT_NOT_FOUND"})
    product = db.get(Product, variant.product_id)
    if product is None or product.status != "active":
        raise HTTPException(status_code=404, detail={"code": "CANONICAL_VARIANT_NOT_FOUND"})
    return _variant_json(variant)


@app.delete(
    "/variants/{variant_id}",
    dependencies=[Depends(require_catalog_write_token)],
    tags=["variants"],
)
def archive_canonical_variant(
    variant_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    variant = db.get(ProductVariant, str(variant_id))
    if variant is None:
        raise HTTPException(status_code=404, detail={"code": "CANONICAL_VARIANT_NOT_FOUND"})
    if variant.status != "archived":
        variant.status = "archived"
        variant.variant_version += 1
        variant.updated_at = _now()
        db.commit()
        db.refresh(variant)
    return _variant_json(variant)


@app.get(
    "/products/{product_id}/versions",
    response_model=list[ProductVersionOut],
    dependencies=[Depends(require_catalog_read_token)],
    tags=["products"],
)
def product_versions(product_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]) -> list[ProductVersion]:
    product = _get_product(db, product_id)
    statement = (
        select(ProductVersion)
        .where(ProductVersion.product_id == product.id)
        .order_by(ProductVersion.version.asc())
    )
    return list(db.scalars(statement).all())
