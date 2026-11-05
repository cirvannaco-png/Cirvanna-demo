"""Persistent Cirvanna commerce API.

Catalog is canonical in catalog-service. This service owns account-scoped saves,
persistent carts, merchant offers/variants, inventory reservations, orders, and
Stripe-hosted checkout. Only a verified provider webhook can mark an order paid.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
import uuid
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Iterator, Literal

import httpx
import jwt as pyjwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWTError
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from urllib.parse import urlsplit
from babel.numbers import get_currency_precision

from sqlalchemy import (
    JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint,
    create_engine, func, inspect, select, text, update,
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


SERVICE = "cirvanna-commerce-service"
EXPECTED_SCHEMA_REVISION = "20261105_0004"
MAX_QTY = 50
RESERVATION_MINUTES = 60
SKU_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,79}$")
CODE3_RE = re.compile(r"^[A-Z]{3}$")
COUNTRY_RE = re.compile(r"^[A-Z]{2}$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def now() -> datetime:
    return datetime.now(timezone.utc)


def offer_max_age_seconds() -> int:
    try:
        configured = int(os.getenv("COMMERCE_OFFER_MAX_AGE_SECONDS", "3600"))
    except ValueError:
        configured = 3600
    return max(60, min(configured, 604800))


def offer_is_fresh(observed_at: datetime | None) -> bool:
    if observed_at is None:
        return False
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    current = now()
    return current - timedelta(seconds=offer_max_age_seconds()) <= observed_at <= current + timedelta(minutes=5)


def make_engine(url: str):
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


engine = make_engine(os.getenv("COMMERCE_DATABASE_URL", "sqlite:///./commerce.db"))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Merchant(Base):
    __tablename__ = "commerce_merchants"
    __table_args__ = (UniqueConstraint("owner_user_id", name="uq_commerce_merchant_owner"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    legal_name: Mapped[str] = mapped_column(String(180), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)  # legacy legal-country alias
    brand_home_country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    legal_country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    contact_email: Mapped[str] = mapped_column(String(254), nullable=False)
    verification_reference: Mapped[str | None] = mapped_column(String(180))
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    commission_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    decision_note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now, onupdate=now)


class Listing(Base):
    __tablename__ = "commerce_listings"
    __table_args__ = (
        UniqueConstraint("merchant_id", "catalog_product_id", name="uq_commerce_listing_merchant_product"),
        Index("ix_commerce_listing_state_category", "state", "category"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("commerce_merchants.id", ondelete="CASCADE"), nullable=False, index=True)
    catalog_product_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    product_name: Mapped[str] = mapped_column(String(180), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    image_urls: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)


class Variant(Base):
    __tablename__ = "commerce_variants"
    __table_args__ = (
        UniqueConstraint("listing_id", "sku", name="uq_commerce_variant_sku"),
        Index("ix_commerce_variant_listing_state", "listing_id", "state"),
        Index("ix_commerce_variant_canonical_observed", "canonical_variant_id", "observed_at"),
        CheckConstraint("price_minor >= 0", name="ck_commerce_variant_price_nonnegative"),
        CheckConstraint("on_hand >= 0", name="ck_commerce_variant_on_hand_nonnegative"),
        CheckConstraint("reserved_qty >= 0 AND reserved_qty <= on_hand", name="ck_commerce_variant_reservation_bounds"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    listing_id: Mapped[str] = mapped_column(ForeignKey("commerce_listings.id", ondelete="CASCADE"), nullable=False, index=True)
    sku: Mapped[str] = mapped_column(String(80), nullable=False)
    options: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    price_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    on_hand: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    canonical_variant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now, onupdate=now)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)
    source_price_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)


class InventoryMovement(Base):
    __tablename__ = "commerce_inventory_movements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    variant_id: Mapped[str] = mapped_column(ForeignKey("commerce_variants.id"), nullable=False, index=True)
    actor_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)


class MerchantOperatingMarket(Base):
    __tablename__ = "commerce_merchant_operating_markets"
    __table_args__ = (
        UniqueConstraint("merchant_id", "market_country_code", name="uq_commerce_merchant_market"),
        CheckConstraint("state IN ('pending','active','blocked')", name="ck_commerce_market_state"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("commerce_merchants.id", ondelete="CASCADE"), nullable=False, index=True)
    market_country_code: Mapped[str] = mapped_column(String(2), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    display_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    locale: Mapped[str | None] = mapped_column(String(35), nullable=True)
    activated_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now, onupdate=now)


class OfferFXQuote(Base):
    __tablename__ = "commerce_offer_fx_quotes"
    __table_args__ = (
        UniqueConstraint("variant_id", "provider", "provider_quote_id", name="uq_commerce_fx_provider_quote"),
        Index("ix_commerce_fx_pair_expiry", "variant_id", "base_currency", "quote_currency", "expires_at"),
        CheckConstraint("rate > 0", name="ck_commerce_fx_rate_positive"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    variant_id: Mapped[str] = mapped_column(ForeignKey("commerce_variants.id", ondelete="CASCADE"), nullable=False, index=True)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_quote_id: Mapped[str] = mapped_column(String(180), nullable=False)
    rounding_rule: Mapped[str] = mapped_column(String(40), nullable=False, default="HALF_UP")
    spread_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)


class OfferFulfillmentQuote(Base):
    __tablename__ = "commerce_offer_fulfillment_quotes"
    __table_args__ = (
        UniqueConstraint("variant_id", "provider", "provider_quote_id", name="uq_commerce_fulfillment_provider_quote"),
        Index("ix_commerce_fulfillment_lookup", "variant_id", "destination_country_code", "destination_key", "fulfillment_mode", "expires_at"),
        CheckConstraint("status IN ('estimate','confirmed','unavailable')", name="ck_commerce_fulfillment_status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    variant_id: Mapped[str] = mapped_column(ForeignKey("commerce_variants.id", ondelete="CASCADE"), nullable=False, index=True)
    destination_country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    destination_key: Mapped[str] = mapped_column(String(180), nullable=False)
    fulfillment_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    amount_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    distance_km: Mapped[Decimal | None] = mapped_column(Numeric(9, 2), nullable=True)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_quote_id: Mapped[str] = mapped_column(String(180), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OfferTaxQuote(Base):
    __tablename__ = "commerce_offer_tax_quotes"
    __table_args__ = (
        UniqueConstraint("variant_id", "provider", "provider_quote_id", name="uq_commerce_tax_provider_quote"),
        Index("ix_commerce_tax_lookup", "variant_id", "destination_country_code", "jurisdiction", "expires_at"),
        CheckConstraint("basis IN ('inclusive','exclusive')", name="ck_commerce_tax_basis"),
        CheckConstraint("status IN ('estimate','confirmed','unavailable')", name="ck_commerce_tax_status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    variant_id: Mapped[str] = mapped_column(ForeignKey("commerce_variants.id", ondelete="CASCADE"), nullable=False, index=True)
    destination_country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(100), nullable=False)
    tax_category: Mapped[str] = mapped_column(String(80), nullable=False)
    basis: Mapped[str] = mapped_column(String(16), nullable=False)
    amount_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    authoritative: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_quote_id: Mapped[str] = mapped_column(String(180), nullable=False)
    rule_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MarketPaymentCapability(Base):
    __tablename__ = "commerce_market_payment_capabilities"
    __table_args__ = (
        UniqueConstraint("merchant_id", "market_country_code", "provider", name="uq_commerce_market_payment_provider"),
        CheckConstraint("state IN ('pending','active','blocked')", name="ck_commerce_market_payment_state"),
        Index("ix_commerce_payment_capability_market", "merchant_id", "market_country_code", "state"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("commerce_merchants.id", ondelete="CASCADE"), nullable=False, index=True)
    market_country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    transaction_currencies: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    settlement_currencies: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    payment_methods: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    provider_reference: Mapped[str | None] = mapped_column(String(180), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SavedProduct(Base):
    __tablename__ = "commerce_saved_products"
    __table_args__ = (UniqueConstraint("user_id", "catalog_product_id", name="uq_commerce_saved_product"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    catalog_product_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)


class Cart(Base):
    __tablename__ = "commerce_carts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now, onupdate=now)


class CartItem(Base):
    __tablename__ = "commerce_cart_items"
    __table_args__ = (UniqueConstraint("cart_id", "variant_id", name="uq_commerce_cart_item"), CheckConstraint("quantity > 0", name="ck_commerce_cart_quantity_positive"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    cart_id: Mapped[str] = mapped_column(ForeignKey("commerce_carts.id", ondelete="CASCADE"), nullable=False, index=True)
    variant_id: Mapped[str] = mapped_column(ForeignKey("commerce_variants.id"), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)


class CommerceOrder(Base):
    __tablename__ = "commerce_orders"
    __table_args__ = (
        UniqueConstraint("buyer_user_id", "idempotency_key", name="uq_commerce_order_idempotency"),
        Index("ix_commerce_order_buyer_created", "buyer_user_id", "created_at"),
        CheckConstraint("subtotal_minor >= 0", name="ck_commerce_order_subtotal_nonnegative"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_number: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    buyer_user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="pending_payment", index=True)
    payment_state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    subtotal_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    commission_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payment_session_id: Mapped[str | None] = mapped_column(String(180), unique=True)
    checkout_url: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now, onupdate=now)


class OrderItem(Base):
    __tablename__ = "commerce_order_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("commerce_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("commerce_merchants.id"), nullable=False, index=True)
    variant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    catalog_product_id: Mapped[str] = mapped_column(String(36), nullable=False)
    product_name: Mapped[str] = mapped_column(String(180), nullable=False)
    sku: Mapped[str] = mapped_column(String(80), nullable=False)
    options: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    commission_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    commission_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_commerce_order_item_quantity_positive"), CheckConstraint("unit_price_minor >= 0 AND line_total_minor >= 0", name="ck_commerce_order_item_price_nonnegative"))


class StockReservation(Base):
    __tablename__ = "commerce_stock_reservations"
    __table_args__ = (UniqueConstraint("order_id", "variant_id", name="uq_commerce_reservation"), CheckConstraint("quantity > 0", name="ck_commerce_reservation_quantity_positive"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("commerce_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    variant_id: Mapped[str] = mapped_column(ForeignKey("commerce_variants.id"), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="reserved", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class PaymentWebhookEvent(Base):
    __tablename__ = "commerce_payment_webhook_events"
    event_id: Mapped[str] = mapped_column(String(180), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)


class Actor(BaseModel):
    user_id: str
    role: Literal["customer", "merchant", "admin"]
    email: str | None = None


bearer = HTTPBearer(auto_error=False)


def _commerce_auth_mode() -> str:
    return os.getenv("COMMERCE_AUTH_MODE", "hs256").strip().lower()


def _production_environment() -> bool:
    return os.getenv("COMMERCE_ENVIRONMENT", "development").strip().lower() == "production"


def _oidc_jwks_url() -> str:
    raw = os.getenv("COMMERCE_JWT_JWKS_URL", "").strip()
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    local = host in {"localhost", "127.0.0.1", "::1"}
    if (not raw or not host or parts.username is not None or parts.password is not None
            or parts.query or parts.fragment
            or (parts.scheme != "https" and not (parts.scheme == "http" and local))):
        raise ValueError("A trusted HTTPS JWKS URL is required.")
    return raw


def _authentication_configured() -> bool:
    mode = _commerce_auth_mode()
    production = _production_environment()
    if mode == "hs256":
        return not production and len(os.getenv("COMMERCE_JWT_SECRET", "").encode()) >= 32
    if mode != "oidc_jwks":
        return False
    issuer = os.getenv("COMMERCE_JWT_ISSUER", "").strip()
    audience = os.getenv("COMMERCE_JWT_AUDIENCE", "").strip()
    try:
        _oidc_jwks_url()
    except ValueError:
        return False
    return bool(issuer and audience)


@lru_cache(maxsize=4)
def _jwks_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url, cache_keys=True, cache_jwk_set=True, lifespan=300, timeout=4)


def _actor_from_claims(claims: dict[str, Any], role_claim: str = "role") -> Actor:
    sub, role = claims.get("sub"), claims.get(role_claim)
    if not isinstance(sub, str) or not sub.strip() or role not in {"customer", "merchant", "admin"}:
        raise ValueError("Required subject or trusted application role claim is invalid.")
    email = claims.get("email")
    if email is not None and (not isinstance(email, str) or len(email) > 254 or not EMAIL_RE.fullmatch(email)):
        raise ValueError("Email claim is invalid.")
    return Actor(user_id=sub, role=role, email=email)


def _decode_oidc_actor(token: str) -> Actor:
    if not _authentication_configured():
        raise HTTPException(503, detail={"code": "AUTH_NOT_CONFIGURED"})
    jwks_url = _oidc_jwks_url()
    issuer = os.getenv("COMMERCE_JWT_ISSUER", "").strip()
    audience = os.getenv("COMMERCE_JWT_AUDIENCE", "").strip()
    role_claim = os.getenv("COMMERCE_JWT_ROLE_CLAIM", "role").strip() or "role"
    try:
        signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token)
        claims = pyjwt.decode(
            token, signing_key.key, algorithms=["RS256"], issuer=issuer, audience=audience,
            options={"require": ["exp", "iss", "aud", "sub"]}, leeway=30,
        )
        return _actor_from_claims(claims, role_claim=role_claim)
    except PyJWKClientConnectionError as exc:
        raise HTTPException(503, detail={"code": "IDENTITY_KEYS_UNAVAILABLE"}) from exc
    except (PyJWTError, TypeError, ValueError) as exc:
        raise HTTPException(401, detail="Invalid bearer token.", headers={"WWW-Authenticate": "Bearer"}) from exc


def decode_actor(token: str) -> Actor:
    mode = _commerce_auth_mode()
    if mode == "oidc_jwks":
        return _decode_oidc_actor(token)
    # Shared-secret HS256 is compatibility mode for local development and tests only.
    if mode != "hs256" or _production_environment():
        raise HTTPException(503, detail={"code": "AUTH_NOT_CONFIGURED"})
    secret = os.getenv("COMMERCE_JWT_SECRET", "")
    if len(secret.encode()) < 32:
        raise HTTPException(503, detail={"code": "AUTH_NOT_CONFIGURED"})
    try:
        p1, p2, p3 = token.split(".")
        header = json.loads(base64.urlsafe_b64decode(p1 + "=" * (-len(p1) % 4)))
        claims = json.loads(base64.urlsafe_b64decode(p2 + "=" * (-len(p2) % 4)))
        supplied = base64.urlsafe_b64decode(p3 + "=" * (-len(p3) % 4))
        if header.get("alg") != "HS256" or header.get("typ") not in (None, "JWT"):
            raise ValueError("unsupported algorithm")
        expected = hmac.new(secret.encode(), f"{p1}.{p2}".encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, supplied):
            raise ValueError("signature")
        ts = int(time.time())
        if not isinstance(claims.get("exp"), (int, float)) or claims["exp"] <= ts:
            raise ValueError("expired")
        if "nbf" in claims and (not isinstance(claims["nbf"], (int, float)) or claims["nbf"] > ts):
            raise ValueError("not active")
        if claims.get("iss") != os.getenv("COMMERCE_JWT_ISSUER", "cirvanna-auth"):
            raise ValueError("issuer")
        aud = claims.get("aud")
        expected_aud = os.getenv("COMMERCE_JWT_AUDIENCE", "cirvanna-commerce")
        if aud != expected_aud and not (isinstance(aud, list) and expected_aud in aud):
            raise ValueError("audience")
        return _actor_from_claims(claims)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(401, detail="Invalid bearer token.", headers={"WWW-Authenticate": "Bearer"}) from exc


def require_actor(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> Actor:
    if credentials is None:
        raise HTTPException(401, detail="Bearer authentication is required.", headers={"WWW-Authenticate": "Bearer"})
    return decode_actor(credentials.credentials)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class CatalogClient:
    def product(self, pid: str) -> dict[str, Any]:
        base, token = os.getenv("CATALOG_API_URL", "").rstrip("/"), os.getenv("CATALOG_API_TOKEN", "")
        if not base or not token:
            raise HTTPException(503, detail={"code": "CATALOG_INTEGRATION_NOT_CONFIGURED"})
        parsed = urlsplit(base)
        local_hosts = {"localhost", "127.0.0.1", "::1"}
        if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise HTTPException(503, detail={"code": "INVALID_CATALOG_API_URL"})
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname.lower() in local_hosts):
            raise HTTPException(503, detail={"code": "CATALOG_API_MUST_USE_HTTPS"})
        try:
            response = httpx.get(f"{base}/products/{pid}", headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}, timeout=4.0)
        except httpx.HTTPError as exc:
            raise HTTPException(503, detail={"code": "CATALOG_UNAVAILABLE"}) from exc
        if response.status_code == 404:
            raise HTTPException(404, detail={"code": "CATALOG_PRODUCT_NOT_FOUND"})
        if response.status_code == 401:
            raise HTTPException(503, detail={"code": "CATALOG_AUTH_FAILED"})
        if response.status_code != 200:
            raise HTTPException(503, detail={"code": "CATALOG_LOOKUP_FAILED", "upstream_status": response.status_code})
        try:
            data = response.json()
        except ValueError as exc:
            raise HTTPException(502, detail={"code": "INVALID_CATALOG_RESPONSE"}) from exc
        if data.get("product_id") != pid or data.get("status") != "active":
            raise HTTPException(409, detail={"code": "CATALOG_PRODUCT_NOT_ACTIVE"})
        return data



    def variant(self, variant_id: str, expected_product_id: str) -> dict[str, Any]:
        base, token = os.getenv("CATALOG_API_URL", "").rstrip("/"), os.getenv("CATALOG_API_TOKEN", "")
        if not base or not token:
            raise HTTPException(503, detail={"code": "CATALOG_INTEGRATION_NOT_CONFIGURED"})
        parsed = urlsplit(base)
        local_hosts = {"localhost", "127.0.0.1", "::1"}
        if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise HTTPException(503, detail={"code": "INVALID_CATALOG_API_URL"})
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname.lower() in local_hosts):
            raise HTTPException(503, detail={"code": "CATALOG_API_MUST_USE_HTTPS"})
        try:
            response = httpx.get(
                f"{base}/variants/{variant_id}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                timeout=4.0,
            )
        except httpx.HTTPError as exc:
            raise HTTPException(503, detail={"code": "CATALOG_UNAVAILABLE"}) from exc
        if response.status_code == 404:
            raise HTTPException(409, detail={"code": "CANONICAL_VARIANT_NOT_FOUND"})
        if response.status_code == 401:
            raise HTTPException(503, detail={"code": "CATALOG_AUTH_FAILED"})
        if response.status_code != 200:
            raise HTTPException(503, detail={"code": "CATALOG_VARIANT_LOOKUP_FAILED", "upstream_status": response.status_code})
        try:
            data = response.json()
        except ValueError as exc:
            raise HTTPException(502, detail={"code": "INVALID_CATALOG_VARIANT_RESPONSE"}) from exc
        if data.get("variant_id") != variant_id or data.get("product_id") != expected_product_id or data.get("status") != "active":
            raise HTTPException(409, detail={"code": "CANONICAL_VARIANT_MISMATCH_OR_INACTIVE"})
        return data


class StripeGateway:
    def __init__(self):
        self.secret = os.getenv("STRIPE_SECRET_KEY", "")
        self.webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
        self.success_url = os.getenv("COMMERCE_CHECKOUT_SUCCESS_URL", "")
        self.cancel_url = os.getenv("COMMERCE_CHECKOUT_CANCEL_URL", "")
        self.countries = [x.strip().upper() for x in os.getenv("COMMERCE_SHIPPING_COUNTRIES", "").split(",") if x.strip()]

    @property
    def ready(self) -> bool:
        return bool(self.secret.startswith(("sk_test_", "sk_live_")) and self.webhook_secret
            and self.success_url.startswith("https://") and self.cancel_url.startswith("https://")
            and self.countries and all(COUNTRY_RE.fullmatch(x) for x in self.countries))

    def create_session(self, order: CommerceOrder, items: list[OrderItem], email: str | None) -> dict[str, str]:
        if not self.ready:
            raise RuntimeError("Stripe not configured")
        params: dict[str, str] = {
            "mode": "payment", "success_url": self.success_url, "cancel_url": self.cancel_url,
            "client_reference_id": order.id, "expires_at": str(int(order.expires_at.timestamp())),
            "metadata[order_id]": order.id, "metadata[order_number]": order.order_number,
        }
        for i, country in enumerate(self.countries):
            params[f"shipping_address_collection[allowed_countries][{i}]"] = country
        if email:
            params["customer_email"] = email
        for i, item in enumerate(items):
            params[f"line_items[{i}][price_data][currency]"] = order.currency.lower()
            params[f"line_items[{i}][price_data][unit_amount]"] = str(item.unit_price_minor)
            params[f"line_items[{i}][price_data][product_data][name]"] = item.product_name[:120]
            params[f"line_items[{i}][quantity]"] = str(item.quantity)
        try:
            res = httpx.post("https://api.stripe.com/v1/checkout/sessions", data=params,
                auth=(self.secret, ""), headers={"Idempotency-Key": f"cirvanna-order-{order.id}"}, timeout=12.0)
            res.raise_for_status()
            data = res.json()
        except (httpx.HTTPError, ValueError) as exc:
            # Ambiguous timeout must not release stock: retry same idempotency key.
            raise RuntimeError("Stripe session request failed or was ambiguous") from exc
        if not data.get("id") or not data.get("url") or data.get("status") != "open":
            raise RuntimeError("Incomplete Stripe session response")
        return {"id": data["id"], "url": data["url"]}

    def expire_session(self, session_id: str) -> bool:
        if not self.ready:
            return False
        try:
            res = httpx.post(f"https://api.stripe.com/v1/checkout/sessions/{session_id}/expire",
                auth=(self.secret, ""), headers={"Idempotency-Key": f"cirvanna-expire-{session_id}"}, timeout=8.0)
            res.raise_for_status()
            return res.json().get("status") == "expired"
        except (httpx.HTTPError, ValueError):
            return False


class MerchantApplication(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=2, max_length=120)
    legal_name: str = Field(min_length=2, max_length=180)
    # country_code remains the legacy legal-country alias for older clients.
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    brand_home_country_code: str | None = Field(default=None, min_length=2, max_length=2)
    legal_country_code: str | None = Field(default=None, min_length=2, max_length=2)
    operating_markets: list[str] = Field(default_factory=list, max_length=30)
    contact_email: str = Field(min_length=5, max_length=254)

    @field_validator("display_name", "legal_name", "contact_email", mode="before")
    @classmethod
    def trim(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v

    @field_validator("country_code", "brand_home_country_code", "legal_country_code")
    @classmethod
    def country(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().upper()
        if not COUNTRY_RE.fullmatch(v):
            raise ValueError("country code must be two letters")
        return v

    @field_validator("operating_markets")
    @classmethod
    def countries(cls, values: list[str]) -> list[str]:
        output = [value.strip().upper() for value in values]
        if any(not COUNTRY_RE.fullmatch(value) for value in output):
            raise ValueError("operating markets must use two-letter country codes")
        if len(output) != len(set(output)):
            raise ValueError("operating markets must not contain duplicates")
        return output

    @field_validator("contact_email")
    @classmethod
    def email(cls, v: str) -> str:
        if not EMAIL_RE.fullmatch(v):
            raise ValueError("valid contact email required")
        return v.lower()

    @model_validator(mode="after")
    def legal_country_required(self):
        if self.legal_country_code is None and self.country_code is None:
            raise ValueError("legal_country_code is required (or legacy country_code)")
        return self


class MerchantDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject", "suspend"]
    commission_bps: int = Field(default=300, ge=0, le=3000)
    note: str | None = Field(default=None, max_length=500)
    # Only an authenticated admin may attach the external verification reference.
    verification_reference: str | None = Field(default=None, min_length=3, max_length=180)


class ListingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    catalog_product_id: str = Field(min_length=36, max_length=36)

    @field_validator("catalog_product_id")
    @classmethod
    def uuid_str(cls, v: str) -> str:
        return str(uuid.UUID(v))


class VariantIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: str = Field(min_length=1, max_length=80)
    options: dict[str, str] = Field(min_length=1, max_length=20)
    price_minor: int = Field(ge=0, le=2_000_000_000)
    currency: str = Field(min_length=3, max_length=3)
    initial_stock: int = Field(ge=0, le=1_000_000)
    canonical_variant_id: str | None = Field(default=None, min_length=36, max_length=36)
    source_price_minor: int | None = Field(default=None, ge=0, le=2_000_000_000)
    source_currency: str | None = Field(default=None, min_length=3, max_length=3)

    @model_validator(mode="after")
    def source_price_pair(self):
        if (self.source_price_minor is None) != (self.source_currency is None):
            raise ValueError("source_price_minor and source_currency must be supplied together")
        if self.source_currency is not None:
            self.source_currency = self.source_currency.strip().upper()
            if not CODE3_RE.fullmatch(self.source_currency):
                raise ValueError("source_currency must be three letters")
        return self

    @field_validator("canonical_variant_id")
    @classmethod
    def valid_canonical_variant_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return str(uuid.UUID(value))

    @field_validator("sku")
    @classmethod
    def valid_sku(cls, v: str) -> str:
        v = v.strip().upper()
        if not SKU_RE.fullmatch(v):
            raise ValueError("invalid SKU")
        return v

    @field_validator("currency")
    @classmethod
    def valid_currency(cls, v: str) -> str:
        v = v.strip().upper()
        if not CODE3_RE.fullmatch(v):
            raise ValueError("currency must be three letters")
        return v

    @field_validator("options")
    @classmethod
    def valid_options(cls, v: dict[str, str]) -> dict[str, str]:
        out = {}
        for k, value in v.items():
            key, value = k.strip().lower(), value.strip()
            if not key or len(key) > 40 or not value or len(value) > 80:
                raise ValueError("option names and values must be non-empty and bounded")
            if key in out:
                raise ValueError("duplicate normalized option name")
            out[key] = value
        return out


MARKET_MODES = {"shipping", "courier_delivery", "merchant_delivery", "collection", "local_transport"}


def _valid_country(value: str) -> str:
    value = value.strip().upper()
    if not COUNTRY_RE.fullmatch(value):
        raise ValueError("country code must be two letters")
    return value


def _valid_currency(value: str) -> str:
    value = value.strip().upper()
    if not CODE3_RE.fullmatch(value):
        raise ValueError("currency must be three letters")
    return value


class MarketDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market_country_code: str = Field(min_length=2, max_length=2)
    display_currency: str | None = Field(default=None, min_length=3, max_length=3)
    locale: str | None = Field(default=None, min_length=2, max_length=35)

    _country = field_validator("market_country_code")(_valid_country)
    _currency = field_validator("display_currency")(_valid_currency)


class MarketActivation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Literal["active", "blocked", "pending"]
    display_currency: str | None = Field(default=None, min_length=3, max_length=3)
    locale: str | None = Field(default=None, min_length=2, max_length=35)

    _currency = field_validator("display_currency")(_valid_currency)


class FXQuoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = Field(min_length=2, max_length=100)
    provider_quote_id: str = Field(min_length=3, max_length=180)
    base_currency: str = Field(min_length=3, max_length=3)
    quote_currency: str = Field(min_length=3, max_length=3)
    rate: Decimal = Field(gt=0, le=Decimal("1000000"))
    rounding_rule: Literal["HALF_UP"] = "HALF_UP"
    spread_bps: int = Field(default=0, ge=0, le=5000)
    observed_at: datetime
    expires_at: datetime

    _base = field_validator("base_currency")(_valid_currency)
    _quote = field_validator("quote_currency")(_valid_currency)

    @model_validator(mode="after")
    def quote_window(self):
        if self.base_currency == self.quote_currency:
            raise ValueError("FX quote currencies must differ")
        if self.observed_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("FX timestamps must include timezone")
        if self.expires_at <= self.observed_at:
            raise ValueError("FX quote expiry must follow observation")
        return self


class FulfillmentQuoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = Field(min_length=2, max_length=100)
    provider_quote_id: str = Field(min_length=3, max_length=180)
    destination_country_code: str = Field(min_length=2, max_length=2)
    destination_key: str = Field(min_length=3, max_length=180)
    fulfillment_mode: Literal["shipping", "courier_delivery", "merchant_delivery", "collection", "local_transport"]
    amount_minor: int | None = Field(default=None, ge=0, le=2_000_000_000)
    currency: str = Field(min_length=3, max_length=3)
    status: Literal["estimate", "confirmed", "unavailable"]
    distance_km: Decimal | None = Field(default=None, ge=0, le=Decimal("100000"))
    observed_at: datetime
    expires_at: datetime

    _country = field_validator("destination_country_code")(_valid_country)
    _currency = field_validator("currency")(_valid_currency)

    @model_validator(mode="after")
    def validate_fulfillment_quote(self):
        if self.status == "unavailable" and self.amount_minor is not None:
            raise ValueError("unavailable fulfilment quotes cannot include an amount")
        if self.status != "unavailable" and self.amount_minor is None:
            raise ValueError("estimated or confirmed fulfilment quotes require an amount")
        if self.observed_at.tzinfo is None or self.expires_at.tzinfo is None or self.expires_at <= self.observed_at:
            raise ValueError("fulfilment quote timestamps must be valid and ordered")
        return self


class TaxQuoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = Field(min_length=2, max_length=100)
    provider_quote_id: str = Field(min_length=3, max_length=180)
    destination_country_code: str = Field(min_length=2, max_length=2)
    jurisdiction: str = Field(min_length=2, max_length=100)
    tax_category: str = Field(min_length=2, max_length=80)
    basis: Literal["inclusive", "exclusive"]
    amount_minor: int | None = Field(default=None, ge=0, le=2_000_000_000)
    currency: str = Field(min_length=3, max_length=3)
    status: Literal["estimate", "confirmed", "unavailable"]
    authoritative: bool = False
    rule_version: str | None = Field(default=None, max_length=80)
    observed_at: datetime
    expires_at: datetime

    _country = field_validator("destination_country_code")(_valid_country)
    _currency = field_validator("currency")(_valid_currency)

    @model_validator(mode="after")
    def validate_tax_quote(self):
        if self.status == "unavailable" and self.amount_minor is not None:
            raise ValueError("unavailable tax quotes cannot include an amount")
        if self.status != "unavailable" and self.amount_minor is None:
            raise ValueError("tax amount required unless unavailable")
        if self.authoritative and (self.status != "confirmed" or not self.provider):
            raise ValueError("authoritative tax requires a confirmed provider quote")
        if self.observed_at.tzinfo is None or self.expires_at.tzinfo is None or self.expires_at <= self.observed_at:
            raise ValueError("tax quote timestamps must be valid and ordered")
        return self


class PaymentCapabilityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market_country_code: str = Field(min_length=2, max_length=2)
    provider: str = Field(min_length=2, max_length=100)
    state: Literal["pending", "active", "blocked"]
    transaction_currencies: list[str] = Field(min_length=1, max_length=20)
    settlement_currencies: list[str] = Field(min_length=1, max_length=20)
    payment_methods: list[str] = Field(min_length=1, max_length=30)
    provider_reference: str | None = Field(default=None, max_length=180)
    observed_at: datetime
    expires_at: datetime

    _country = field_validator("market_country_code")(_valid_country)

    @field_validator("transaction_currencies", "settlement_currencies")
    @classmethod
    def currency_list(cls, values: list[str]) -> list[str]:
        output = [_valid_currency(value) for value in values]
        if len(output) != len(set(output)):
            raise ValueError("payment currencies must be unique")
        return output

    @model_validator(mode="after")
    def valid_window(self):
        if self.observed_at.tzinfo is None or self.expires_at.tzinfo is None or self.expires_at <= self.observed_at:
            raise ValueError("payment capability timestamps must be valid and ordered")
        return self


class OfferComparisonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    variant_ids: list[str] = Field(min_length=2, max_length=2)
    destination_country_code: str = Field(min_length=2, max_length=2)
    destination_key: str = Field(min_length=3, max_length=180)
    fulfillment_mode: Literal["shipping", "courier_delivery", "merchant_delivery", "collection", "local_transport"]
    display_currency: str = Field(min_length=3, max_length=3)
    payment_method: str | None = Field(default=None, min_length=2, max_length=50)

    @field_validator("variant_ids")
    @classmethod
    def uuids(cls, values: list[str]) -> list[str]:
        output = [str(uuid.UUID(value)) for value in values]
        if len(set(output)) != 2:
            raise ValueError("two distinct variant IDs are required")
        return output

    _country = field_validator("destination_country_code")(_valid_country)
    _currency = field_validator("display_currency")(_valid_currency)



class CartItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    variant_id: str = Field(min_length=36, max_length=36)
    quantity: int = Field(ge=1, le=MAX_QTY)

    @field_validator("variant_id")
    @classmethod
    def valid_variant_uuid(cls, v: str) -> str:
        return str(uuid.UUID(v))


class QuantityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quantity: int = Field(ge=1, le=MAX_QTY)


class InventoryAdjustment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quantity_delta: int = Field(ge=-1_000_000, le=1_000_000)
    reason: str = Field(min_length=3, max_length=160)

    @field_validator("reason")
    @classmethod
    def trim_reason(cls, v: str) -> str:
        return v.strip()


class Readiness(BaseModel):
    status: str
    service: str
    database_connected: bool
    schema_present: bool
    authentication_configured: bool
    authentication_mode: str
    catalog_configured: bool
    payment_configured: bool
    migrations_required: bool
    migrations_applied: bool
    schema_revision: str | None
    ready: bool


def merchant_json(m: Merchant) -> dict[str, Any]:
    return {"merchant_id": m.id, "owner_user_id": m.owner_user_id, "display_name": m.display_name,
        "legal_name": m.legal_name, "country_code": m.country_code,
        "brand_home_country_code": m.brand_home_country_code,
        "legal_country_code": m.legal_country_code or m.country_code,
        "contact_email": m.contact_email,
        "verification_reference": m.verification_reference, "status": m.state, "commission_bps": m.commission_bps,
        "decision_note": m.decision_note, "created_at": m.created_at.isoformat() if m.created_at else None}



def quote_is_current(observed_at: datetime | None, expires_at: datetime | None) -> bool:
    if observed_at is None or expires_at is None:
        return False
    observed = observed_at if observed_at.tzinfo else observed_at.replace(tzinfo=timezone.utc)
    expiry = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
    current = now()
    return (
        current - timedelta(seconds=offer_max_age_seconds()) <= observed <= current + timedelta(minutes=5)
        and expiry > current
    )


def _require_market_context_token(token: str | None) -> None:
    expected = os.getenv("COMMERCE_MARKET_CONTEXT_TOKEN", "").strip()
    if len(expected.encode("utf-8")) < 32 or not token or not hmac.compare_digest(expected, token):
        raise HTTPException(401, detail={"code": "MARKET_CONTEXT_AUTH_REQUIRED"})


def _currency_minor_units(currency: str) -> int:
    try:
        return int(get_currency_precision(currency.upper()))
    except Exception as exc:
        raise ValueError("unsupported ISO currency") from exc


def _fresh_fx_quote(db: Session, variant_id: str, base_currency: str, quote_currency: str) -> OfferFXQuote | None:
    if base_currency == quote_currency:
        return None
    quote = db.scalar(select(OfferFXQuote).where(
        OfferFXQuote.variant_id == variant_id,
        OfferFXQuote.base_currency == base_currency,
        OfferFXQuote.quote_currency == quote_currency,
    ).order_by(OfferFXQuote.observed_at.desc(), OfferFXQuote.id.desc()).limit(1))
    if quote is None or not quote_is_current(quote.observed_at, quote.expires_at):
        return None
    return quote


def _convert_minor_amount(
    db: Session, *, variant_id: str, amount_minor: int, source_currency: str, target_currency: str
) -> tuple[int | None, dict[str, Any] | None]:
    source_currency = source_currency.upper()
    target_currency = target_currency.upper()
    try:
        source_exponent = _currency_minor_units(source_currency)
        target_exponent = _currency_minor_units(target_currency)
    except ValueError:
        return None, None
    amount_major = Decimal(amount_minor) / (Decimal(10) ** source_exponent)
    fx = None
    rate = Decimal("1")
    if source_currency != target_currency:
        fx = _fresh_fx_quote(db, variant_id, source_currency, target_currency)
        if fx is None:
            return None, None
        rate = Decimal(fx.rate)
    converted_minor = (amount_major * rate * (Decimal(10) ** target_exponent)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    fx_meta = None if fx is None else {
        "quote_id": fx.id,
        "provider": fx.provider,
        "provider_quote_id": fx.provider_quote_id,
        "base_currency": fx.base_currency,
        "quote_currency": fx.quote_currency,
        "rate": str(fx.rate),
        "observed_at": fx.observed_at.isoformat(),
        "expires_at": fx.expires_at.isoformat(),
        "rounding_rule": fx.rounding_rule,
        "spread_bps": fx.spread_bps,
    }
    return int(converted_minor), fx_meta


def _market_payment_capability(
    db: Session, merchant_id: str, market_country_code: str, transaction_currency: str,
    payment_method: str | None = None,
) -> MarketPaymentCapability | None:
    current = now()
    rows = list(db.scalars(select(MarketPaymentCapability).where(
        MarketPaymentCapability.merchant_id == merchant_id,
        MarketPaymentCapability.market_country_code == market_country_code,
        MarketPaymentCapability.state == "active",
    ).order_by(MarketPaymentCapability.observed_at.desc())).all())
    for row in rows:
        if not quote_is_current(row.observed_at, row.expires_at):
            continue
        if transaction_currency not in row.transaction_currencies:
            continue
        if payment_method and payment_method not in row.payment_methods:
            continue
        return row
    return None


def _market_is_active(db: Session, merchant_id: str, market_country_code: str) -> MerchantOperatingMarket | None:
    return db.scalar(select(MerchantOperatingMarket).where(
        MerchantOperatingMarket.merchant_id == merchant_id,
        MerchantOperatingMarket.market_country_code == market_country_code,
        MerchantOperatingMarket.state == "active",
    ))



def approved_merchant(db: Session, actor: Actor) -> Merchant:
    # Ownership alone is not an authorization boundary: the signed token must
    # also carry the merchant role issued by the trusted identity provider.
    if actor.role != "merchant":
        raise HTTPException(403, detail={"code": "MERCHANT_ROLE_REQUIRED"})
    merchant = db.scalar(select(Merchant).where(Merchant.owner_user_id == actor.user_id))
    if merchant is None or merchant.state != "approved":
        raise HTTPException(403, detail={"code": "MERCHANT_NOT_APPROVED"})
    return merchant


def ensure_cart(db: Session, user_id: str) -> Cart:
    cart = db.scalar(select(Cart).where(Cart.user_id == user_id))
    if cart is not None:
        return cart
    cart = Cart(id=str(uuid.uuid4()), user_id=user_id, version=1)
    db.add(cart)
    try:
        db.commit()
        db.refresh(cart)
    except IntegrityError:
        db.rollback()
        cart = db.scalar(select(Cart).where(Cart.user_id == user_id))
        if cart is None:
            raise
    return cart


def variant_triplet(db: Session, variant_id: str):
    return db.execute(select(Variant, Listing, Merchant)
        .join(Listing, Variant.listing_id == Listing.id)
        .join(Merchant, Listing.merchant_id == Merchant.id)
        .where(Variant.id == variant_id)).first()


def cart_json(db: Session, cart: Cart) -> dict[str, Any]:
    rows = db.execute(select(CartItem, Variant, Listing, Merchant)
        .join(Variant, CartItem.variant_id == Variant.id).join(Listing, Variant.listing_id == Listing.id)
        .join(Merchant, Listing.merchant_id == Merchant.id).where(CartItem.cart_id == cart.id)).all()
    items, subtotals, currencies = [], {}, set()
    for ci, v, listing, merchant in rows:
        available = max(0, v.on_hand - v.reserved_qty)
        valid = v.state == "active" and listing.state == "active" and merchant.state == "approved"
        line = v.price_minor * ci.quantity
        items.append({"variant_id": v.id, "listing_id": listing.id, "catalog_product_id": listing.catalog_product_id,
            "product_name": listing.product_name, "merchant_name": merchant.display_name, "sku": v.sku,
            "options": v.options, "quantity": ci.quantity, "price_minor": v.price_minor, "currency": v.currency,
            "line_total_minor": line, "available_stock": available,
            "availability": "in_stock" if valid and available >= ci.quantity else "unavailable"})
        currencies.add(v.currency)
        subtotals[v.currency] = subtotals.get(v.currency, 0) + line
    return {"cart_id": cart.id, "version": cart.version, "items": items,
        "item_count": sum(x["quantity"] for x in items), "subtotal_by_currency": subtotals,
        "single_currency": len(currencies) <= 1, "updated_at": cart.updated_at}


def order_json(db: Session, order: CommerceOrder, include_url: bool = False) -> dict[str, Any]:
    lines = list(db.scalars(select(OrderItem).where(OrderItem.order_id == order.id)).all())
    result = {"order_id": order.id, "order_number": order.order_number, "status": order.state,
        "payment_status": order.payment_state, "currency": order.currency, "subtotal_minor": order.subtotal_minor,
        "commission_minor": order.commission_minor, "expires_at": order.expires_at, "paid_at": order.paid_at,
        "created_at": order.created_at, "items": [{"merchant_id": i.merchant_id, "variant_id": i.variant_id,
        "catalog_product_id": i.catalog_product_id, "product_name": i.product_name, "sku": i.sku, "options": i.options,
        "quantity": i.quantity, "unit_price_minor": i.unit_price_minor, "line_total_minor": i.line_total_minor,
        "commission_bps": i.commission_bps, "commission_minor": i.commission_minor} for i in lines]}
    if include_url and order.checkout_url and order.state == "pending_payment":
        result["checkout_url"] = order.checkout_url
    return result


def persist_stripe_session(db: Session, order_id: str, email: str | None, gateway: StripeGateway) -> dict[str, Any]:
    order = db.scalar(select(CommerceOrder).where(CommerceOrder.id == order_id))
    if order is None:
        raise HTTPException(404, detail={"code": "ORDER_NOT_FOUND"})
    if order.checkout_url and order.state == "pending_payment":
        return {"order": order_json(db, order, True), "checkout_url": order.checkout_url, "duplicate": True}
    if order.state != "pending_payment":
        raise HTTPException(409, detail={"code": "ORDER_NOT_PAYABLE", "state": order.state})
    lines = list(db.scalars(select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.id)).all())
    try:
        session = gateway.create_session(order, lines, email)
    except RuntimeError as exc:
        # Network failure may occur after Stripe accepted the request. Keep the
        # reservation and recover via stable provider idempotency on retry.
        raise HTTPException(502, detail={"code": "PAYMENT_SESSION_PENDING_RECONCILIATION",
            "order_id": order.id, "detail": "Retry using the SAME Idempotency-Key; stock remains reserved."}) from exc
    order.payment_session_id, order.checkout_url, order.updated_at = session["id"], session["url"], now()
    db.commit()
    db.refresh(order)
    return {"order": order_json(db, order, True), "checkout_url": order.checkout_url, "duplicate": False}


def release_reservations(db: Session, order: CommerceOrder, final_state: str) -> None:
    rows = list(db.scalars(select(StockReservation).where(
        StockReservation.order_id == order.id, StockReservation.state == "reserved").with_for_update()).all())
    for reservation in rows:
        changed = db.execute(update(Variant).where(Variant.id == reservation.variant_id,
            Variant.reserved_qty >= reservation.quantity).values(
            reserved_qty=Variant.reserved_qty - reservation.quantity, version=Variant.version + 1, updated_at=now(), observed_at=now()))
        if changed.rowcount != 1:
            raise RuntimeError("Inventory reservation invariant failed")
        reservation.state = "released"
    order.state = final_state
    if final_state in {"checkout_failed", "payment_failed"}:
        order.payment_state = "failed"
    order.updated_at = now()


def settle_paid(db: Session, order: CommerceOrder, amount_total: int, currency: str) -> None:
    if order.state == "paid":
        return
    if order.state != "pending_payment":
        raise HTTPException(409, detail={"code": "PAYMENT_ORDER_NOT_PENDING", "state": order.state})
    if amount_total != order.subtotal_minor or currency.lower() != order.currency.lower():
        raise HTTPException(400, detail={"code": "PAYMENT_AMOUNT_MISMATCH"})
    reservations = list(db.scalars(select(StockReservation).where(
        StockReservation.order_id == order.id, StockReservation.state == "reserved").with_for_update()).all())
    if not reservations:
        raise HTTPException(409, detail={"code": "ACTIVE_RESERVATION_MISSING"})
    for r in reservations:
        changed = db.execute(update(Variant).where(Variant.id == r.variant_id,
            Variant.reserved_qty >= r.quantity, Variant.on_hand >= r.quantity).values(
            on_hand=Variant.on_hand - r.quantity, reserved_qty=Variant.reserved_qty - r.quantity,
            version=Variant.version + 1, updated_at=now(), observed_at=now()))
        if changed.rowcount != 1:
            raise HTTPException(409, detail={"code": "STOCK_SETTLEMENT_CONFLICT"})
        r.state = "consumed"
        db.add(InventoryMovement(id=str(uuid.uuid4()), variant_id=r.variant_id,
            actor_user_id="system:payment-webhook", delta=-r.quantity, reason=f"sale:{order.order_number}"))
    order.state, order.payment_state, order.paid_at, order.updated_at = "paid", "paid", now(), now()
    cart = db.scalar(select(Cart).where(Cart.user_id == order.buyer_user_id))
    if cart:
        ids = [r.variant_id for r in reservations]
        db.query(CartItem).filter(CartItem.cart_id == cart.id, CartItem.variant_id.in_(ids)).delete(synchronize_session=False)
        cart.version, cart.updated_at = cart.version + 1, now()


def verify_stripe_signature(payload: bytes, signature: str, secret: str, tolerance: int = 300) -> None:
    if not secret:
        raise HTTPException(503, detail={"code": "PAYMENT_WEBHOOK_NOT_CONFIGURED"})
    fields: dict[str, list[str]] = {}
    for part in signature.split(","):
        key, sep, value = part.strip().partition("=")
        if sep:
            fields.setdefault(key, []).append(value)
    if not fields.get("t") or not fields.get("v1"):
        raise HTTPException(400, detail={"code": "INVALID_PAYMENT_SIGNATURE"})
    try:
        ts = int(fields["t"][0])
    except ValueError as exc:
        raise HTTPException(400, detail={"code": "INVALID_PAYMENT_SIGNATURE"}) from exc
    if abs(int(time.time()) - ts) > tolerance:
        raise HTTPException(400, detail={"code": "STALE_PAYMENT_SIGNATURE"})
    expected = hmac.new(secret.encode(), str(ts).encode() + b"." + payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, value) for value in fields["v1"]):
        raise HTTPException(400, detail={"code": "INVALID_PAYMENT_SIGNATURE"})


app = FastAPI(title="Cirvanna Commerce Service", version="0.1.0")
cors = [x.strip().rstrip("/") for x in os.getenv("COMMERCE_CORS_ORIGINS", "").split(",") if x.strip()]
if cors:
    app.add_middleware(CORSMiddleware, allow_origins=cors, allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "Stripe-Signature", "X-Commerce-Cron-Token"],
        max_age=600)


@app.on_event("startup")
def startup() -> None:
    if os.getenv("COMMERCE_AUTO_CREATE_SCHEMA", "true").lower() == "true":
        Base.metadata.create_all(bind=engine)


@app.get("/me", tags=["identity"])
def get_current_actor(actor: Annotated[Actor, Depends(require_actor)]) -> dict[str, Any]:
    """Return the actor derived from a verified signed token, never caller-supplied IDs."""
    return {"user_id": actor.user_id, "role": actor.role, "email": actor.email}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "alive", "service": SERVICE}


@app.get("/ready", response_model=Readiness)
def readiness(db: Annotated[Session, Depends(get_db)]) -> Readiness:
    """Require DB reachability, complete schema, current migration, and integrations."""
    migrations_required = os.getenv("COMMERCE_AUTO_CREATE_SCHEMA", "true").lower() != "true"
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
        # A failed DB/schema probe must never be interpreted as ready.
        connected = False
        schema_present = False

    auth_ok = _authentication_configured()
    catalog_ok = bool(os.getenv("CATALOG_API_URL") and os.getenv("CATALOG_API_TOKEN"))
    payment_ok = StripeGateway().ready
    migrations_applied = schema_revision == EXPECTED_SCHEMA_REVISION
    ready = (
        connected
        and schema_present
        and auth_ok
        and catalog_ok
        and payment_ok
        and (not migrations_required or migrations_applied)
    )
    result = Readiness(status="ready" if ready else "not_ready", service=SERVICE,
        database_connected=connected, schema_present=schema_present,
        authentication_configured=auth_ok, authentication_mode=_commerce_auth_mode(),
        catalog_configured=catalog_ok, payment_configured=payment_ok, migrations_required=migrations_required,
        migrations_applied=migrations_applied, schema_revision=schema_revision, ready=ready)
    if not ready:
        raise HTTPException(503, detail=result.model_dump())
    return result

@app.get("/capabilities")
def capabilities() -> dict[str, Any]:
    return {"service": SERVICE, "persistent_carts": True, "saved_products": True,
        "merchant_onboarding": True, "variant_inventory": True, "transactional_reservations": True,
        "idempotent_orders": True, "stripe_hosted_checkout": StripeGateway().ready,
        "verified_payment_webhooks": bool(os.getenv("STRIPE_WEBHOOK_SECRET")),
        "automated_seller_payouts": False, "shipping_tax_calculation": False,
        "catacaci_eligibility": False, "click_it_reconstruction": False,
        "virtual_twin_generation": False, "virtual_try_on": False}


@app.post("/merchants/applications", status_code=201)
def apply_merchant(payload: MerchantApplication, actor: Annotated[Actor, Depends(require_actor)], db: Annotated[Session, Depends(get_db)]):
    # Any authenticated user may apply; the trusted identity issuer must grant
    # the merchant role separately before approved seller operations are allowed.
    exists = db.scalar(select(Merchant).where(Merchant.owner_user_id == actor.user_id))
    if exists:
        raise HTTPException(409, detail={"code": "MERCHANT_APPLICATION_EXISTS", "merchant": merchant_json(exists)})
    legacy_country = payload.country_code or payload.legal_country_code
    legal_country = payload.legal_country_code or legacy_country
    merchant = Merchant(id=str(uuid.uuid4()), owner_user_id=actor.user_id,
        display_name=payload.display_name, legal_name=payload.legal_name, country_code=legacy_country,
        brand_home_country_code=payload.brand_home_country_code, legal_country_code=legal_country,
        contact_email=payload.contact_email, verification_reference=None, state="pending")
    db.add(merchant)
    for market_country in payload.operating_markets:
        db.add(MerchantOperatingMarket(
            id=str(uuid.uuid4()), merchant_id=merchant.id, market_country_code=market_country,
            state="pending", display_currency=None, locale=None,
        ))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail={"code": "MERCHANT_APPLICATION_EXISTS"}) from exc
    db.refresh(merchant)
    return merchant_json(merchant)


@app.get("/merchants/me")
def merchant_me(actor: Annotated[Actor, Depends(require_actor)], db: Annotated[Session, Depends(get_db)]):
    merchant = db.scalar(select(Merchant).where(Merchant.owner_user_id == actor.user_id))
    if not merchant:
        raise HTTPException(404, detail={"code": "MERCHANT_APPLICATION_NOT_FOUND"})
    return merchant_json(merchant)



@app.get("/admin/merchants")
def list_merchants(
    actor: Annotated[Actor, Depends(require_actor)],
    db: Annotated[Session, Depends(get_db)],
    state: Literal["pending", "approved", "rejected", "suspended"] | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    """Return a paginated merchant review queue to authenticated administrators."""
    if actor.role != "admin":
        raise HTTPException(403, detail={"code": "ADMIN_REQUIRED"})
    stmt = select(Merchant)
    count_stmt = select(func.count()).select_from(Merchant)
    if state is not None:
        stmt = stmt.where(Merchant.state == state)
        count_stmt = count_stmt.where(Merchant.state == state)
    total = int(db.scalar(count_stmt) or 0)
    rows = list(db.scalars(
        stmt.order_by(Merchant.created_at.desc(), Merchant.id).offset(offset).limit(limit)
    ).all())
    # Do not expose owner_user_id or internal verification references in the queue.
    return {
        "items": [{
            "merchant_id": merchant.id,
            "display_name": merchant.display_name,
            "legal_name": merchant.legal_name,
            "country_code": merchant.country_code,
            "contact_email": merchant.contact_email,
            "status": merchant.state,
            "commission_bps": merchant.commission_bps,
            "decision_note": merchant.decision_note,
            "created_at": merchant.created_at.isoformat() if merchant.created_at else None,
        } for merchant in rows],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@app.post("/admin/merchants/{merchant_id}/decision")
def decide_merchant(merchant_id: uuid.UUID, payload: MerchantDecision,
    actor: Annotated[Actor, Depends(require_actor)], db: Annotated[Session, Depends(get_db)]):
    if actor.role != "admin":
        raise HTTPException(403, detail={"code": "ADMIN_REQUIRED"})
    merchant = db.get(Merchant, str(merchant_id))
    if not merchant:
        raise HTTPException(404, detail={"code": "MERCHANT_NOT_FOUND"})
    if payload.decision == "approve":
        if not payload.verification_reference or not payload.verification_reference.strip():
            raise HTTPException(409, detail={"code": "MERCHANT_VERIFICATION_REQUIRED",
                "detail": "An admin-supplied reference from the external business/KYC verification procedure is required."})
        merchant.verification_reference = payload.verification_reference.strip()
    merchant.state = {"approve": "approved", "reject": "rejected", "suspend": "suspended"}[payload.decision]
    merchant.commission_bps = payload.commission_bps
    merchant.decision_note = payload.note.strip() if payload.note else None
    merchant.updated_at = now()
    db.commit()
    db.refresh(merchant)
    return merchant_json(merchant)


def trusted_catalog_image_urls(product: dict[str, Any]) -> list[str]:
    raw_urls = product.get("image_urls", [])
    if not isinstance(raw_urls, list):
        return []
    safe: list[str] = []
    for value in raw_urls:
        if not isinstance(value, str) or not value.strip() or len(value) > 2048:
            continue
        try:
            parsed = urlsplit(value.strip())
        except ValueError:
            continue
        if parsed.scheme != "https" or not parsed.hostname or parsed.username is not None or parsed.password is not None:
            continue
        if parsed.fragment or any(ord(ch) < 32 for ch in value):
            continue
        normalized = value.strip()
        if normalized not in safe:
            safe.append(normalized)
        if len(safe) == 8:
            break
    return safe



@app.get("/merchant/markets")
def list_merchant_markets(
    actor: Annotated[Actor, Depends(require_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    merchant = approved_merchant(db, actor)
    rows = list(db.scalars(select(MerchantOperatingMarket).where(
        MerchantOperatingMarket.merchant_id == merchant.id
    ).order_by(MerchantOperatingMarket.market_country_code)).all())
    return {"items": [{
        "market_country_code": row.market_country_code,
        "state": row.state,
        "display_currency": row.display_currency,
        "locale": row.locale,
        "activated_at": row.activated_at.isoformat() if row.activated_at else None,
    } for row in rows]}


@app.post("/merchant/markets", status_code=201)
def declare_merchant_market(
    payload: MarketDeclaration,
    actor: Annotated[Actor, Depends(require_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    merchant = approved_merchant(db, actor)
    row = db.scalar(select(MerchantOperatingMarket).where(
        MerchantOperatingMarket.merchant_id == merchant.id,
        MerchantOperatingMarket.market_country_code == payload.market_country_code,
    ))
    if row is None:
        row = MerchantOperatingMarket(
            id=str(uuid.uuid4()), merchant_id=merchant.id,
            market_country_code=payload.market_country_code, state="pending",
            display_currency=payload.display_currency, locale=payload.locale,
        )
        db.add(row)
    else:
        row.display_currency = payload.display_currency
        row.locale = payload.locale
        # A merchant may not activate a market or reverse a block.
        if row.state == "active":
            row.state = "pending"
            row.activated_by = None
            row.activated_at = None
    db.commit()
    db.refresh(row)
    return {
        "market_country_code": row.market_country_code,
        "state": row.state,
        "display_currency": row.display_currency,
        "locale": row.locale,
        "activation_authority": "admin",
    }


@app.put("/admin/merchants/{merchant_id}/markets/{market_country_code}")
def set_merchant_market_state(
    merchant_id: uuid.UUID,
    market_country_code: str,
    payload: MarketActivation,
    actor: Annotated[Actor, Depends(require_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    if actor.role != "admin":
        raise HTTPException(403, detail={"code": "ADMIN_REQUIRED"})
    market_code = _valid_country(market_country_code)
    merchant = db.get(Merchant, str(merchant_id))
    if merchant is None:
        raise HTTPException(404, detail={"code": "MERCHANT_NOT_FOUND"})
    market = db.scalar(select(MerchantOperatingMarket).where(
        MerchantOperatingMarket.merchant_id == merchant.id,
        MerchantOperatingMarket.market_country_code == market_code,
    ))
    if market is None:
        raise HTTPException(404, detail={"code": "MERCHANT_MARKET_NOT_DECLARED"})
    if payload.state == "active":
        if merchant.state != "approved":
            raise HTTPException(409, detail={"code": "MERCHANT_NOT_APPROVED"})
        display_currency = payload.display_currency or market.display_currency
        if not display_currency:
            raise HTTPException(409, detail={"code": "MARKET_DISPLAY_CURRENCY_REQUIRED"})
        capable = list(db.scalars(select(MarketPaymentCapability).where(
            MarketPaymentCapability.merchant_id == merchant.id,
            MarketPaymentCapability.market_country_code == market_code,
            MarketPaymentCapability.state == "active",
        )).all())
        if not any(
            quote_is_current(item.observed_at, item.expires_at)
            and display_currency in item.transaction_currencies
            for item in capable
        ):
            raise HTTPException(409, detail={"code": "MARKET_PAYMENT_CAPABILITY_NOT_READY"})
        market.display_currency = display_currency
        market.locale = payload.locale or market.locale
        market.activated_by = actor.user_id
        market.activated_at = now()
    else:
        market.activated_by = None
        market.activated_at = None
    market.state = payload.state
    market.updated_at = now()
    db.commit()
    return {
        "merchant_id": merchant.id,
        "market_country_code": market.market_country_code,
        "state": market.state,
        "display_currency": market.display_currency,
        "locale": market.locale,
        "activated_at": market.activated_at.isoformat() if market.activated_at else None,
    }


def _validate_quote_variant(db: Session, variant_id: str) -> Variant:
    variant = db.get(Variant, variant_id)
    if variant is None or variant.state != "active":
        raise HTTPException(404, detail={"code": "ACTIVE_VARIANT_NOT_FOUND"})
    return variant


@app.post("/internal/market-context/variants/{variant_id}/fx-quotes", status_code=201)
def ingest_fx_quote(
    variant_id: uuid.UUID,
    payload: FXQuoteIn,
    db: Annotated[Session, Depends(get_db)],
    token: Annotated[str | None, Header(alias="X-Commerce-Market-Context-Token")] = None,
):
    _require_market_context_token(token)
    variant = _validate_quote_variant(db, str(variant_id))
    if not quote_is_current(payload.observed_at, payload.expires_at):
        raise HTTPException(422, detail={"code": "FX_QUOTE_NOT_CURRENT"})
    existing = db.scalar(select(OfferFXQuote).where(
        OfferFXQuote.variant_id == variant.id,
        OfferFXQuote.provider == payload.provider,
        OfferFXQuote.provider_quote_id == payload.provider_quote_id,
    ))
    if existing:
        raise HTTPException(409, detail={"code": "FX_QUOTE_ALREADY_RECORDED"})
    row = OfferFXQuote(
        id=str(uuid.uuid4()), variant_id=variant.id,
        base_currency=payload.base_currency, quote_currency=payload.quote_currency,
        rate=payload.rate, provider=payload.provider, provider_quote_id=payload.provider_quote_id,
        rounding_rule=payload.rounding_rule, spread_bps=payload.spread_bps,
        observed_at=payload.observed_at, expires_at=payload.expires_at,
    )
    db.add(row)
    db.commit()
    return {
        "quote_id": row.id, "variant_id": variant.id,
        "base_currency": row.base_currency, "quote_currency": row.quote_currency,
        "rate": str(row.rate), "provider": row.provider,
        "provider_quote_id": row.provider_quote_id,
        "observed_at": row.observed_at.isoformat(), "expires_at": row.expires_at.isoformat(),
    }


@app.post("/internal/market-context/variants/{variant_id}/fulfillment-quotes", status_code=201)
def ingest_fulfillment_quote(
    variant_id: uuid.UUID,
    payload: FulfillmentQuoteIn,
    db: Annotated[Session, Depends(get_db)],
    token: Annotated[str | None, Header(alias="X-Commerce-Market-Context-Token")] = None,
):
    _require_market_context_token(token)
    variant = _validate_quote_variant(db, str(variant_id))
    if not quote_is_current(payload.observed_at, payload.expires_at):
        raise HTTPException(422, detail={"code": "FULFILLMENT_QUOTE_NOT_CURRENT"})
    existing = db.scalar(select(OfferFulfillmentQuote).where(
        OfferFulfillmentQuote.variant_id == variant.id,
        OfferFulfillmentQuote.provider == payload.provider,
        OfferFulfillmentQuote.provider_quote_id == payload.provider_quote_id,
    ))
    if existing:
        raise HTTPException(409, detail={"code": "FULFILLMENT_QUOTE_ALREADY_RECORDED"})
    row = OfferFulfillmentQuote(
        id=str(uuid.uuid4()), variant_id=variant.id,
        destination_country_code=payload.destination_country_code,
        destination_key=payload.destination_key.strip(), fulfillment_mode=payload.fulfillment_mode,
        amount_minor=payload.amount_minor, currency=payload.currency, status=payload.status,
        distance_km=payload.distance_km, provider=payload.provider,
        provider_quote_id=payload.provider_quote_id, observed_at=payload.observed_at,
        expires_at=payload.expires_at,
    )
    db.add(row)
    db.commit()
    return {"quote_id": row.id, "variant_id": variant.id, "destination_country_code": row.destination_country_code,
        "destination_key": row.destination_key, "fulfillment_mode": row.fulfillment_mode,
        "amount_minor": row.amount_minor, "currency": row.currency, "status": row.status,
        "provider": row.provider, "observed_at": row.observed_at.isoformat(), "expires_at": row.expires_at.isoformat()}


@app.post("/internal/market-context/variants/{variant_id}/tax-quotes", status_code=201)
def ingest_tax_quote(
    variant_id: uuid.UUID,
    payload: TaxQuoteIn,
    db: Annotated[Session, Depends(get_db)],
    token: Annotated[str | None, Header(alias="X-Commerce-Market-Context-Token")] = None,
):
    _require_market_context_token(token)
    variant = _validate_quote_variant(db, str(variant_id))
    if not quote_is_current(payload.observed_at, payload.expires_at):
        raise HTTPException(422, detail={"code": "TAX_QUOTE_NOT_CURRENT"})
    existing = db.scalar(select(OfferTaxQuote).where(
        OfferTaxQuote.variant_id == variant.id,
        OfferTaxQuote.provider == payload.provider,
        OfferTaxQuote.provider_quote_id == payload.provider_quote_id,
    ))
    if existing:
        raise HTTPException(409, detail={"code": "TAX_QUOTE_ALREADY_RECORDED"})
    row = OfferTaxQuote(
        id=str(uuid.uuid4()), variant_id=variant.id,
        destination_country_code=payload.destination_country_code,
        jurisdiction=payload.jurisdiction.strip(), tax_category=payload.tax_category.strip(),
        basis=payload.basis, amount_minor=payload.amount_minor, currency=payload.currency,
        status=payload.status, authoritative=payload.authoritative, provider=payload.provider,
        provider_quote_id=payload.provider_quote_id, rule_version=payload.rule_version,
        observed_at=payload.observed_at, expires_at=payload.expires_at,
    )
    db.add(row)
    db.commit()
    return {"quote_id": row.id, "variant_id": variant.id, "destination_country_code": row.destination_country_code,
        "jurisdiction": row.jurisdiction, "tax_category": row.tax_category, "basis": row.basis,
        "amount_minor": row.amount_minor, "currency": row.currency, "status": row.status,
        "authoritative": row.authoritative, "provider": row.provider,
        "observed_at": row.observed_at.isoformat(), "expires_at": row.expires_at.isoformat()}


@app.put("/internal/market-context/merchants/{merchant_id}/payment-capabilities")
def upsert_market_payment_capability(
    merchant_id: uuid.UUID,
    payload: PaymentCapabilityIn,
    db: Annotated[Session, Depends(get_db)],
    token: Annotated[str | None, Header(alias="X-Commerce-Market-Context-Token")] = None,
):
    _require_market_context_token(token)
    merchant = db.get(Merchant, str(merchant_id))
    if merchant is None:
        raise HTTPException(404, detail={"code": "MERCHANT_NOT_FOUND"})
    market = db.scalar(select(MerchantOperatingMarket).where(
        MerchantOperatingMarket.merchant_id == merchant.id,
        MerchantOperatingMarket.market_country_code == payload.market_country_code,
    ))
    if market is None:
        raise HTTPException(404, detail={"code": "MERCHANT_MARKET_NOT_DECLARED"})
    if not quote_is_current(payload.observed_at, payload.expires_at):
        raise HTTPException(422, detail={"code": "PAYMENT_CAPABILITY_NOT_CURRENT"})
    row = db.scalar(select(MarketPaymentCapability).where(
        MarketPaymentCapability.merchant_id == merchant.id,
        MarketPaymentCapability.market_country_code == payload.market_country_code,
        MarketPaymentCapability.provider == payload.provider,
    ))
    if row is None:
        row = MarketPaymentCapability(
            id=str(uuid.uuid4()), merchant_id=merchant.id,
            market_country_code=payload.market_country_code, provider=payload.provider,
            state=payload.state,
        )
        db.add(row)
    row.state = payload.state
    row.transaction_currencies = payload.transaction_currencies
    row.settlement_currencies = payload.settlement_currencies
    row.payment_methods = payload.payment_methods
    row.provider_reference = payload.provider_reference
    row.observed_at = payload.observed_at
    row.expires_at = payload.expires_at
    db.commit()
    return {"capability_id": row.id, "merchant_id": merchant.id, "market_country_code": row.market_country_code,
        "provider": row.provider, "state": row.state, "transaction_currencies": row.transaction_currencies,
        "settlement_currencies": row.settlement_currencies, "payment_methods": row.payment_methods,
        "observed_at": row.observed_at.isoformat(), "expires_at": row.expires_at.isoformat()}



@app.post("/merchant/listings", status_code=201)
def create_listing(payload: ListingIn, actor: Annotated[Actor, Depends(require_actor)], db: Annotated[Session, Depends(get_db)]):
    merchant = approved_merchant(db, actor)
    product = CatalogClient().product(payload.catalog_product_id)
    if db.scalar(select(Listing).where(Listing.merchant_id == merchant.id, Listing.catalog_product_id == product["product_id"])):
        raise HTTPException(409, detail={"code": "LISTING_ALREADY_EXISTS"})
    listing = Listing(id=str(uuid.uuid4()), merchant_id=merchant.id, catalog_product_id=product["product_id"],
        product_name=str(product["name"])[:180], category=str(product.get("category") or "uncategorized")[:80],
        image_urls=trusted_catalog_image_urls(product), state="active")
    db.add(listing)
    db.commit()
    return {"listing_id": listing.id, "merchant_id": listing.merchant_id, "catalog_product_id": listing.catalog_product_id,
        "product_name": listing.product_name, "category": listing.category, "image_urls": listing.image_urls,
        "status": listing.state}


@app.post("/merchant/listings/{listing_id}/variants", status_code=201)
def create_variant(listing_id: uuid.UUID, payload: VariantIn,
    actor: Annotated[Actor, Depends(require_actor)], db: Annotated[Session, Depends(get_db)]):
    merchant = approved_merchant(db, actor)
    listing = db.get(Listing, str(listing_id))
    if not listing or listing.merchant_id != merchant.id:
        raise HTTPException(404, detail={"code": "LISTING_NOT_FOUND"})
    if listing.state != "active":
        raise HTTPException(409, detail={"code": "LISTING_NOT_ACTIVE"})
    require_canonical = (
        os.getenv("COMMERCE_ENVIRONMENT", "").strip().lower() == "production"
        or os.getenv("COMMERCE_REQUIRE_CANONICAL_VARIANT_ID", "false").strip().lower() == "true"
    )
    if require_canonical and not payload.canonical_variant_id:
        raise HTTPException(422, detail={"code": "CANONICAL_VARIANT_ID_REQUIRED"})
    if payload.canonical_variant_id:
        CatalogClient().variant(payload.canonical_variant_id, listing.catalog_product_id)
    observed_at = now()
    variant = Variant(id=str(uuid.uuid4()), listing_id=listing.id, sku=payload.sku, options=payload.options,
        price_minor=payload.price_minor, currency=payload.currency, on_hand=payload.initial_stock,
        reserved_qty=0, state="active", version=1, canonical_variant_id=payload.canonical_variant_id,
        updated_at=observed_at, observed_at=observed_at,
        source_price_minor=payload.source_price_minor, source_currency=payload.source_currency)
    db.add(variant)
    if payload.initial_stock:
        db.add(InventoryMovement(id=str(uuid.uuid4()), variant_id=variant.id,
            actor_user_id=actor.user_id, delta=payload.initial_stock, reason="initial_stock"))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail={"code": "VARIANT_SKU_CONFLICT"}) from exc
    return {"variant_id": variant.id, "listing_id": listing.id, "sku": variant.sku, "options": variant.options,
        "price_minor": variant.price_minor, "currency": variant.currency,
        "source_price_minor": variant.source_price_minor, "source_currency": variant.source_currency,
        "on_hand": variant.on_hand, "reserved_qty": variant.reserved_qty,
        "available_stock": variant.on_hand - variant.reserved_qty,
        "canonical_variant_id": variant.canonical_variant_id, "observed_at": variant.observed_at.isoformat(),
        "version": variant.version}


@app.post("/merchant/variants/{variant_id}/inventory-adjustments")
def adjust_inventory(variant_id: uuid.UUID, payload: InventoryAdjustment,
    actor: Annotated[Actor, Depends(require_actor)], db: Annotated[Session, Depends(get_db)]):
    if payload.quantity_delta == 0 or not payload.reason.strip():
        raise HTTPException(422, detail={"code": "INVALID_ADJUSTMENT"})
    merchant = approved_merchant(db, actor)
    variant = db.get(Variant, str(variant_id))
    listing = db.get(Listing, variant.listing_id) if variant else None
    if not variant or not listing or listing.merchant_id != merchant.id:
        raise HTTPException(404, detail={"code": "VARIANT_NOT_FOUND"})
    result = db.execute(update(Variant).where(Variant.id == variant.id,
        Variant.on_hand + payload.quantity_delta >= Variant.reserved_qty,
        Variant.on_hand + payload.quantity_delta >= 0).values(
        on_hand=Variant.on_hand + payload.quantity_delta, version=Variant.version + 1, updated_at=now(), observed_at=now()))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, detail={"code": "INVENTORY_BELOW_RESERVED_OR_NEGATIVE"})
    db.add(InventoryMovement(id=str(uuid.uuid4()), variant_id=variant.id, actor_user_id=actor.user_id,
        delta=payload.quantity_delta, reason=payload.reason.strip()))
    db.commit()
    db.refresh(variant)
    return {"variant_id": variant.id, "on_hand": variant.on_hand, "reserved_qty": variant.reserved_qty,
        "available_stock": variant.on_hand - variant.reserved_qty, "canonical_variant_id": variant.canonical_variant_id,
        "observed_at": variant.observed_at.isoformat() if variant.observed_at else None, "version": variant.version}


@app.get("/marketplace/offers")
def list_offers(db: Annotated[Session, Depends(get_db)], q: str | None = Query(None, max_length=160),
    category: str | None = Query(None, max_length=80), currency: str | None = Query(None, min_length=3, max_length=3),
    offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    stmt = select(Variant, Listing, Merchant).join(Listing, Variant.listing_id == Listing.id).join(Merchant, Listing.merchant_id == Merchant.id).where(
        Variant.state == "active", Listing.state == "active", Merchant.state == "approved", Variant.on_hand > Variant.reserved_qty)
    if q and q.strip():
        stmt = stmt.where(func.lower(Listing.product_name).like(f"%{q.strip().lower()}%"))
    if category:
        stmt = stmt.where(func.lower(Listing.category) == category.strip().lower())
    if currency:
        curr = currency.strip().upper()
        if not CODE3_RE.fullmatch(curr):
            raise HTTPException(422, detail={"code": "INVALID_CURRENCY"})
        stmt = stmt.where(Variant.currency == curr)
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = db.execute(stmt.order_by(Listing.created_at.desc(), Variant.id).offset(offset).limit(limit)).all()
    return {"items": [{"variant_id": v.id, "listing_id": l.id, "merchant_id": m.id, "merchant_name": m.display_name,
        "catalog_product_id": l.catalog_product_id, "product_name": l.product_name, "category": l.category,
        "image_urls": l.image_urls, "sku": v.sku, "options": v.options, "price_minor": v.price_minor, "currency": v.currency,
        "available_stock": v.on_hand - v.reserved_qty, "canonical_variant_id": v.canonical_variant_id,
        "observed_at": v.observed_at.isoformat() if v.observed_at else None,
        "is_fresh": offer_is_fresh(v.observed_at),
        "comparison_eligible": bool(v.canonical_variant_id and offer_is_fresh(v.observed_at))}
        for v, l, m in rows], "total": total, "offset": offset, "limit": limit,
        "offer_max_age_seconds": offer_max_age_seconds()}


@app.put("/saved-products/{catalog_product_id}", status_code=201)
def save_product(catalog_product_id: uuid.UUID, actor: Annotated[Actor, Depends(require_actor)], db: Annotated[Session, Depends(get_db)]):
    pid = str(catalog_product_id)
    product = CatalogClient().product(pid)
    saved = db.scalar(select(SavedProduct).where(SavedProduct.user_id == actor.user_id, SavedProduct.catalog_product_id == pid))
    if saved is None:
        db.add(SavedProduct(id=str(uuid.uuid4()), user_id=actor.user_id, catalog_product_id=pid))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
    return {"catalog_product_id": pid, "product_name": product["name"], "saved": True}


@app.get("/saved-products")
def get_saved_products(actor: Annotated[Actor, Depends(require_actor)], db: Annotated[Session, Depends(get_db)]):
    rows = list(db.scalars(select(SavedProduct).where(SavedProduct.user_id == actor.user_id).order_by(SavedProduct.created_at.desc())).all())
    return {"items": [{"catalog_product_id": r.catalog_product_id, "saved_at": r.created_at} for r in rows], "total": len(rows)}


@app.delete("/saved-products/{catalog_product_id}", status_code=204)
def delete_saved_product(catalog_product_id: uuid.UUID, actor: Annotated[Actor, Depends(require_actor)], db: Annotated[Session, Depends(get_db)]):
    db.query(SavedProduct).filter(SavedProduct.user_id == actor.user_id, SavedProduct.catalog_product_id == str(catalog_product_id)).delete(synchronize_session=False)
    db.commit()


@app.get("/cart")
def get_cart(actor: Annotated[Actor, Depends(require_actor)], db: Annotated[Session, Depends(get_db)]):
    return cart_json(db, ensure_cart(db, actor.user_id))


@app.post("/cart/items", status_code=201)
def add_cart_item(payload: CartItemIn, actor: Annotated[Actor, Depends(require_actor)], db: Annotated[Session, Depends(get_db)]):
    joined = variant_triplet(db, payload.variant_id)
    if not joined:
        raise HTTPException(404, detail={"code": "VARIANT_NOT_FOUND"})
    variant, listing, merchant = joined
    if variant.state != "active" or listing.state != "active" or merchant.state != "approved":
        raise HTTPException(409, detail={"code": "OFFER_UNAVAILABLE"})
    cart = ensure_cart(db, actor.user_id)
    item = db.scalar(select(CartItem).where(CartItem.cart_id == cart.id, CartItem.variant_id == variant.id))
    quantity = payload.quantity + (item.quantity if item else 0)
    if quantity > MAX_QTY:
        raise HTTPException(422, detail={"code": "CART_QUANTITY_LIMIT", "maximum": MAX_QTY})
    if variant.on_hand - variant.reserved_qty < quantity:
        raise HTTPException(409, detail={"code": "INSUFFICIENT_AVAILABLE_STOCK", "available_stock": variant.on_hand - variant.reserved_qty})
    if item:
        item.quantity = quantity
    else:
        db.add(CartItem(id=str(uuid.uuid4()), cart_id=cart.id, variant_id=variant.id, quantity=quantity))
    cart.version, cart.updated_at = cart.version + 1, now()
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail={"code": "CART_CONFLICT_RETRY"}) from exc
    return cart_json(db, ensure_cart(db, actor.user_id))


@app.patch("/cart/items/{variant_id}")
def update_cart_item(variant_id: uuid.UUID, payload: QuantityIn, actor: Annotated[Actor, Depends(require_actor)], db: Annotated[Session, Depends(get_db)]):
    cart = ensure_cart(db, actor.user_id)
    item = db.scalar(select(CartItem).where(CartItem.cart_id == cart.id, CartItem.variant_id == str(variant_id)))
    if not item:
        raise HTTPException(404, detail={"code": "CART_ITEM_NOT_FOUND"})
    variant = db.get(Variant, item.variant_id)
    if not variant or variant.state != "active" or variant.on_hand - variant.reserved_qty < payload.quantity:
        raise HTTPException(409, detail={"code": "INSUFFICIENT_AVAILABLE_STOCK"})
    item.quantity, cart.version, cart.updated_at = payload.quantity, cart.version + 1, now()
    db.commit()
    return cart_json(db, cart)


@app.delete("/cart/items/{variant_id}")
def remove_cart_item(variant_id: uuid.UUID, actor: Annotated[Actor, Depends(require_actor)], db: Annotated[Session, Depends(get_db)]):
    cart = ensure_cart(db, actor.user_id)
    db.query(CartItem).filter(CartItem.cart_id == cart.id, CartItem.variant_id == str(variant_id)).delete(synchronize_session=False)
    cart.version, cart.updated_at = cart.version + 1, now()
    db.commit()
    return cart_json(db, cart)


@app.post("/checkout", status_code=201)
def checkout(actor: Annotated[Actor, Depends(require_actor)], db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=255)]):
    gateway = StripeGateway()
    if not gateway.ready:
        raise HTTPException(503, detail={"code": "PAYMENT_PROVIDER_NOT_CONFIGURED"})
    existing = db.scalar(select(CommerceOrder).where(CommerceOrder.buyer_user_id == actor.user_id, CommerceOrder.idempotency_key == idempotency_key))
    if existing:
        return persist_stripe_session(db, existing.id, actor.email, gateway)
    cart = ensure_cart(db, actor.user_id)
    rows = db.execute(select(CartItem, Variant, Listing, Merchant)
        .join(Variant, CartItem.variant_id == Variant.id).join(Listing, Variant.listing_id == Listing.id)
        .join(Merchant, Listing.merchant_id == Merchant.id).where(CartItem.cart_id == cart.id).with_for_update()).all()
    if not rows:
        raise HTTPException(409, detail={"code": "EMPTY_CART"})
    if len(rows) > 100 or any(ci.quantity < 1 or ci.quantity > MAX_QTY for ci, *_ in rows):
        raise HTTPException(422, detail={"code": "INVALID_CART_ITEMS"})
    if any(v.state != "active" or l.state != "active" or m.state != "approved" for _, v, l, m in rows):
        raise HTTPException(409, detail={"code": "CART_CONTAINS_UNAVAILABLE_OFFERS"})
    currencies = {v.currency for _, v, _, _ in rows}
    if len(currencies) != 1:
        raise HTTPException(422, detail={"code": "MIXED_CURRENCY_CART"})
    currency = next(iter(currencies))
    subtotal = sum(v.price_minor * ci.quantity for ci, v, _, _ in rows)
    if subtotal <= 0:
        raise HTTPException(422, detail={"code": "INVALID_ORDER_TOTAL"})
    expiry = now() + timedelta(minutes=RESERVATION_MINUTES)
    order = CommerceOrder(id=str(uuid.uuid4()), order_number=f"CV-{now():%Y%m%d}-{uuid.uuid4().hex[:10].upper()}",
        buyer_user_id=actor.user_id, state="pending_payment", payment_state="pending", currency=currency,
        subtotal_minor=subtotal, commission_minor=0, idempotency_key=idempotency_key, expires_at=expiry)
    try:
        for ci, v, listing, merchant in rows:
            changed = db.execute(update(Variant).where(Variant.id == v.id, Variant.state == "active",
                Variant.on_hand - Variant.reserved_qty >= ci.quantity).values(
                reserved_qty=Variant.reserved_qty + ci.quantity, version=Variant.version + 1, updated_at=now(), observed_at=now()))
            if changed.rowcount != 1:
                raise HTTPException(409, detail={"code": "INSUFFICIENT_AVAILABLE_STOCK", "variant_id": v.id})
            line = v.price_minor * ci.quantity
            commission = line * merchant.commission_bps // 10000
            order.commission_minor += commission
            db.add(OrderItem(id=str(uuid.uuid4()), order_id=order.id, merchant_id=merchant.id,
                variant_id=v.id, catalog_product_id=listing.catalog_product_id, product_name=listing.product_name,
                sku=v.sku, options=v.options, quantity=ci.quantity, unit_price_minor=v.price_minor,
                line_total_minor=line, commission_bps=merchant.commission_bps, commission_minor=commission))
            db.add(StockReservation(id=str(uuid.uuid4()), order_id=order.id, variant_id=v.id, quantity=ci.quantity,
                state="reserved", expires_at=expiry))
            db.add(InventoryMovement(id=str(uuid.uuid4()), variant_id=v.id, actor_user_id="system:checkout",
                delta=0, reason=f"reserve:{order.order_number}:qty={ci.quantity}"))
        db.add(order)
        db.flush()
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        existing = db.scalar(select(CommerceOrder).where(CommerceOrder.buyer_user_id == actor.user_id, CommerceOrder.idempotency_key == idempotency_key))
        if existing:
            return persist_stripe_session(db, existing.id, actor.email, gateway)
        raise HTTPException(409, detail={"code": "ORDER_CONFLICT_RETRY_SAME_IDEMPOTENCY_KEY"}) from exc
    return persist_stripe_session(db, order.id, actor.email, gateway)


@app.get("/orders")
def get_orders(actor: Annotated[Actor, Depends(require_actor)], db: Annotated[Session, Depends(get_db)],
    offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    stmt = select(CommerceOrder).where(CommerceOrder.buyer_user_id == actor.user_id)
    total = int(db.scalar(select(func.count()).select_from(CommerceOrder).where(CommerceOrder.buyer_user_id == actor.user_id)) or 0)
    rows = list(db.scalars(stmt.order_by(CommerceOrder.created_at.desc()).offset(offset).limit(limit)).all())
    return {"items": [order_json(db, x, True) for x in rows], "total": total, "offset": offset, "limit": limit}


@app.get("/orders/{order_id}")
def get_order(order_id: uuid.UUID, actor: Annotated[Actor, Depends(require_actor)], db: Annotated[Session, Depends(get_db)]):
    order = db.get(CommerceOrder, str(order_id))
    if not order or order.buyer_user_id != actor.user_id:
        raise HTTPException(404, detail={"code": "ORDER_NOT_FOUND"})
    return order_json(db, order, True)


@app.get("/merchant/orders")
def merchant_orders(actor: Annotated[Actor, Depends(require_actor)], db: Annotated[Session, Depends(get_db)],
    offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    merchant = approved_merchant(db, actor)
    order_ids = select(OrderItem.order_id).where(OrderItem.merchant_id == merchant.id).distinct()
    orders = list(db.scalars(select(CommerceOrder).where(CommerceOrder.id.in_(order_ids))
        .order_by(CommerceOrder.created_at.desc()).offset(offset).limit(limit)).all())
    result = []
    for order in orders:
        snapshot = order_json(db, order)
        snapshot["items"] = [item for item in snapshot["items"] if item["merchant_id"] == merchant.id]
        result.append(snapshot)
    return {"items": result, "offset": offset, "limit": limit}


@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: Annotated[Session, Depends(get_db)],
    signature: Annotated[str | None, Header(alias="Stripe-Signature")] = None):
    raw = await request.body()
    if not signature:
        raise HTTPException(400, detail={"code": "PAYMENT_SIGNATURE_REQUIRED"})
    verify_stripe_signature(raw, signature, os.getenv("STRIPE_WEBHOOK_SECRET", ""))
    try:
        event = json.loads(raw)
        event_id, event_type, obj = event["id"], event["type"], event["data"]["object"]
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(400, detail={"code": "INVALID_PAYMENT_EVENT"}) from exc
    if not isinstance(event_id, str) or not event_id or not isinstance(event_type, str):
        raise HTTPException(400, detail={"code": "INVALID_PAYMENT_EVENT"})
    if db.get(PaymentWebhookEvent, event_id) is not None:
        return {"received": True, "duplicate": True}
    handled = {"checkout.session.completed", "checkout.session.async_payment_succeeded",
        "checkout.session.expired", "checkout.session.async_payment_failed"}
    if event_type in handled:
        order_id = (obj.get("metadata") or {}).get("order_id")
        if not order_id:
            raise HTTPException(400, detail={"code": "ORDER_REFERENCE_MISSING"})
        order = db.scalar(select(CommerceOrder).where(CommerceOrder.id == str(order_id)).with_for_update())
        if not order or not order.payment_session_id or obj.get("id") != order.payment_session_id:
            raise HTTPException(409, detail={"code": "PAYMENT_SESSION_MISMATCH"})
        if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
            if obj.get("payment_status") == "paid":
                settle_paid(db, order, int(obj.get("amount_total", -1)), str(obj.get("currency", "")))
        elif event_type == "checkout.session.expired" and order.state == "pending_payment":
            release_reservations(db, order, "expired")
        elif event_type == "checkout.session.async_payment_failed" and order.state == "pending_payment":
            release_reservations(db, order, "payment_failed")
    db.add(PaymentWebhookEvent(event_id=event_id, event_type=event_type))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"received": True, "duplicate": True}
    return {"received": True, "duplicate": False}


@app.post("/internal/expire-reservations")
def expire_reservations(db: Annotated[Session, Depends(get_db)],
    cron_token: Annotated[str | None, Header(alias="X-Commerce-Cron-Token")] = None):
    expected = os.getenv("COMMERCE_CRON_TOKEN", "")
    if not expected or not cron_token or not hmac.compare_digest(expected, cron_token):
        raise HTTPException(401, detail={"code": "CRON_AUTH_FAILED"})
    gateway = StripeGateway()
    if not gateway.ready:
        raise HTTPException(503, detail={"code": "PAYMENT_PROVIDER_NOT_CONFIGURED"})
    orders = list(db.scalars(select(CommerceOrder).where(CommerceOrder.state == "pending_payment",
        CommerceOrder.expires_at <= now(), CommerceOrder.payment_session_id.is_not(None)).limit(100)).all())
    expired = 0
    for found in orders:
        # Do not release stock on timeouts or unknown provider state. Stripe must
        # confirm the session actually expired before reservations can be released.
        if gateway.expire_session(found.payment_session_id or ""):
            order = db.scalar(select(CommerceOrder).where(CommerceOrder.id == found.id).with_for_update())
            if order and order.state == "pending_payment":
                release_reservations(db, order, "expired")
                db.commit()
                expired += 1
    return {"expired_reservations": expired, "examined_orders": len(orders)}


@app.get("/admin/inventory/audit")
def inventory_audit(actor: Annotated[Actor, Depends(require_actor)], db: Annotated[Session, Depends(get_db)]):
    if actor.role != "admin":
        raise HTTPException(403, detail={"code": "ADMIN_REQUIRED"})
    bad = list(db.scalars(select(Variant).where(
        (Variant.on_hand < 0) | (Variant.reserved_qty < 0) | (Variant.reserved_qty > Variant.on_hand))).all())
    return {"ok": not bad, "violations": [{"variant_id": v.id, "on_hand": v.on_hand,
        "reserved_qty": v.reserved_qty, "version": v.version} for v in bad]}
