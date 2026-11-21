"""Shopify merchant-provider adapter for Cirvanna Commerce.

Shopify is an external merchant system of record for its own catalogue and stock.
Catalog remains canonical for product/variant identity; Commerce remains canonical
for offers, inventory reservations, buyer orders and CAL purchase authorization.
Imported Shopify products are private staging records until explicitly mapped to
verified Catalog identities. This module deliberately exposes no shopper catalogue.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Annotated, Any, Iterator
from urllib.parse import urlencode, urlsplit

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, and_, or_,
    UniqueConstraint, select,
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Mapped, Session, mapped_column
from babel.numbers import get_currency_precision

from app import main as commerce


router = APIRouter(tags=["Shopify integration"])
API_VERSION = os.getenv("SHOPIFY_ADMIN_API_VERSION", "2026-10").strip()
SHOP_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.myshopify\.com$")
GID_RE = re.compile(r"^gid://shopify/(Product|ProductVariant|Order|InventoryItem|InventoryLevel)/[0-9]+$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
REQUIRED_SCOPES = {
    "read_products", "read_inventory", "read_locations", "read_orders", "write_orders"
}
WEBHOOK_TOPICS = (
    "PRODUCTS_CREATE", "PRODUCTS_UPDATE", "PRODUCTS_DELETE",
    "INVENTORY_LEVELS_UPDATE",
    "ORDERS_CREATE", "ORDERS_UPDATED", "ORDERS_CANCELLED", "ORDERS_FULFILLED",
    "APP_UNINSTALLED", "SHOP_REDACT",
    "CUSTOMERS_DATA_REQUEST", "CUSTOMERS_REDACT",
)
OAUTH_COOKIE = "cirvanna_shopify_oauth_state"
OAUTH_STATE_TTL_MINUTES = 10
TOKEN_AAD = b"cirvanna-shopify-token-v1"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _shop_domain(value: str) -> str:
    normalized = (value or "").strip().lower().rstrip(".")
    if not SHOP_RE.fullmatch(normalized):
        raise HTTPException(422, detail={"code": "SHOPIFY_SHOP_DOMAIN_INVALID"})
    return normalized


def _oauth_config() -> tuple[str, str, str]:
    api_key = os.getenv("SHOPIFY_API_KEY", "").strip()
    api_secret = os.getenv("SHOPIFY_API_SECRET", "").strip()
    base_url = os.getenv("SHOPIFY_APP_BASE_URL", "").strip().rstrip("/")
    parsed = urlsplit(base_url)
    host = (parsed.hostname or "").lower()
    local = host in {"localhost", "127.0.0.1", "::1"}
    if (
        not api_key or len(api_secret.encode()) < 32 or not host
        or parsed.username or parsed.password or parsed.query or parsed.fragment
        or (parsed.scheme != "https" and not (parsed.scheme == "http" and local))
    ):
        raise HTTPException(503, detail={"code": "SHOPIFY_OAUTH_NOT_CONFIGURED"})
    return api_key, api_secret, base_url


def _webhook_base_url() -> str:
    value = os.getenv("SHOPIFY_WEBHOOK_BASE_URL", "").strip().rstrip("/")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https" or not parsed.hostname
        or parsed.username or parsed.password or parsed.query or parsed.fragment
    ):
        raise HTTPException(503, detail={"code": "SHOPIFY_WEBHOOK_BASE_URL_NOT_CONFIGURED"})
    return value


def _encryption_key() -> bytes:
    raw = os.getenv("COMMERCE_SHOPIFY_TOKEN_ENCRYPTION_KEY", "").strip()
    if not raw:
        raise HTTPException(503, detail={"code": "SHOPIFY_TOKEN_ENCRYPTION_NOT_CONFIGURED"})
    try:
        decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    except Exception as exc:
        raise HTTPException(503, detail={"code": "SHOPIFY_TOKEN_ENCRYPTION_KEY_INVALID"}) from exc
    if len(decoded) != 32:
        raise HTTPException(503, detail={"code": "SHOPIFY_TOKEN_ENCRYPTION_KEY_INVALID"})
    return decoded


def _token_aad(connection: ShopifyConnection, purpose: str) -> bytes:
    return TOKEN_AAD + b"|" + connection.id.encode() + b"|" + connection.merchant_id.encode() + b"|" + connection.shop_domain.encode() + b"|" + purpose.encode()


def _seal(value: str, connection: ShopifyConnection, purpose: str) -> str:
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(_encryption_key()).encrypt(
        nonce, value.encode("utf-8"), _token_aad(connection, purpose)
    )
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def _unseal(value: str, connection: ShopifyConnection, purpose: str) -> str:
    try:
        packed = base64.urlsafe_b64decode(value.encode("ascii"))
        if len(packed) < 29:
            raise ValueError("ciphertext too short")
        return AESGCM(_encryption_key()).decrypt(
            packed[:12], packed[12:], _token_aad(connection, purpose)
        ).decode("utf-8")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, detail={"code": "SHOPIFY_TOKEN_DECRYPTION_FAILED"}) from exc


def _minor_units(amount: str | Decimal | int, currency: str) -> int:
    code = str(currency).strip().upper()
    if not CURRENCY_RE.fullmatch(code):
        raise ValueError("Invalid ISO currency code")
    try:
        value = Decimal(str(amount))
        if not value.is_finite() or value < 0:
            raise ValueError("Money must be finite and non-negative")
        precision = get_currency_precision(code)
        scale = Decimal(10) ** precision
        return int((value * scale).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Invalid money amount") from exc


def _major_units(minor: int, currency: str) -> str:
    if isinstance(minor, bool) or minor < 0:
        raise ValueError("Money minor units must be a non-negative integer")
    precision = get_currency_precision(currency)
    return format(Decimal(minor) / (Decimal(10) ** precision), f".{precision}f")


def _oauth_hmac_valid(query_params, secret: str) -> bool:
    supplied = query_params.get("hmac")
    if not supplied:
        return False
    pairs = [(key, value) for key, value in query_params.multi_items() if key not in {"hmac", "signature"}]
    message = "&".join(key + "=" + value for key, value in sorted(pairs, key=lambda pair: (pair[0], pair[1])))
    expected = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, supplied)


def _webhook_hmac_valid(raw: bytes, supplied: str | None, secret: str) -> bool:
    if not supplied or not secret:
        return False
    expected = base64.b64encode(hmac.new(secret.encode(), raw, hashlib.sha256).digest()).decode("ascii")
    return hmac.compare_digest(expected, supplied.strip())


class ShopifyConnection(commerce.Base):
    __tablename__ = "commerce_shopify_connections"
    __table_args__ = (
        UniqueConstraint("merchant_id", name="uq_commerce_shopify_merchant"),
        UniqueConstraint("shop_domain", name="uq_commerce_shopify_domain"),
        Index("ix_commerce_shopify_status_expiry", "status", "access_expires_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("commerce_merchants.id", ondelete="CASCADE"), nullable=False)
    shop_domain: Mapped[str] = mapped_column(String(100), nullable=False)
    shop_gid: Mapped[str | None] = mapped_column(String(180))
    shop_name: Mapped[str | None] = mapped_column(String(180))
    shop_currency: Mapped[str | None] = mapped_column(String(3))
    access_token_ciphertext: Mapped[str | None] = mapped_column(Text)
    refresh_token_ciphertext: Mapped[str | None] = mapped_column(Text)
    access_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refresh_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    granted_scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    webhook_registration: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    products_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    products_cursor: Mapped[str | None] = mapped_column(String(512))
    orders_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class ShopifyOAuthState(commerce.Base):
    __tablename__ = "commerce_shopify_oauth_states"
    __table_args__ = (Index("ix_commerce_shopify_oauth_expiry", "expires_at", "consumed_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("commerce_merchants.id", ondelete="CASCADE"), nullable=False)
    shop_domain: Mapped[str] = mapped_column(String(100), nullable=False)
    state_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ShopifyProductSnapshot(commerce.Base):
    __tablename__ = "commerce_shopify_product_snapshots"
    __table_args__ = (
        UniqueConstraint("connection_id", "shopify_product_gid", name="uq_shopify_product_snapshot"),
        Index("ix_shopify_product_snapshot_state", "connection_id", "mapping_state"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    connection_id: Mapped[str] = mapped_column(ForeignKey("commerce_shopify_connections.id", ondelete="CASCADE"), nullable=False)
    shopify_product_gid: Mapped[str] = mapped_column(String(180), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    handle: Mapped[str | None] = mapped_column(String(255))
    vendor: Mapped[str | None] = mapped_column(String(180))
    product_type: Mapped[str | None] = mapped_column(String(120))
    remote_status: Mapped[str] = mapped_column(String(24), nullable=False)
    remote_updated_at: Mapped[str | None] = mapped_column(String(64))
    catalog_product_id: Mapped[str | None] = mapped_column(String(36))
    listing_id: Mapped[str | None] = mapped_column(String(36))
    mapping_state: Mapped[str] = mapped_column(String(24), nullable=False, default="staged")
    variants_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ShopifyVariantSnapshot(commerce.Base):
    __tablename__ = "commerce_shopify_variant_snapshots"
    __table_args__ = (
        UniqueConstraint("connection_id", "shopify_variant_gid", name="uq_shopify_variant_snapshot"),
        Index("ix_shopify_variant_product", "product_snapshot_id"),
        Index("ix_shopify_variant_local", "local_variant_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    connection_id: Mapped[str] = mapped_column(ForeignKey("commerce_shopify_connections.id", ondelete="CASCADE"), nullable=False)
    product_snapshot_id: Mapped[str] = mapped_column(ForeignKey("commerce_shopify_product_snapshots.id", ondelete="CASCADE"), nullable=False)
    shopify_variant_gid: Mapped[str] = mapped_column(String(180), nullable=False)
    shopify_inventory_item_gid: Mapped[str | None] = mapped_column(String(180))
    sku: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    options: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    price_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    tracked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    available_quantity: Mapped[int | None] = mapped_column(Integer)
    on_hand_quantity: Mapped[int | None] = mapped_column(Integer)
    inventory_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    regional_prices: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    local_variant_id: Mapped[str | None] = mapped_column(String(36))
    canonical_variant_id: Mapped[str | None] = mapped_column(String(36))
    mapping_state: Mapped[str] = mapped_column(String(24), nullable=False, default="staged")
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ShopifyWebhookEvent(commerce.Base):
    __tablename__ = "commerce_shopify_webhook_events"
    __table_args__ = (
        UniqueConstraint("shop_domain", "delivery_id", name="uq_shopify_webhook_delivery"),
        Index("ix_shopify_webhook_pending", "state", "received_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    shop_domain: Mapped[str] = mapped_column(String(100), nullable=False)
    delivery_id: Mapped[str] = mapped_column(String(180), nullable=False)
    event_id: Mapped[str | None] = mapped_column(String(180))
    topic: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_gid: Mapped[str | None] = mapped_column(String(180))
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(300))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ShopifyOrderLink(commerce.Base):
    __tablename__ = "commerce_shopify_order_links"
    __table_args__ = (
        UniqueConstraint("commerce_order_id", "merchant_id", name="uq_shopify_order_link_commerce"),
        UniqueConstraint("connection_id", "shopify_order_gid", name="uq_shopify_order_link_remote"),
        Index("ix_shopify_order_link_state", "connection_id", "link_state"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    connection_id: Mapped[str] = mapped_column(ForeignKey("commerce_shopify_connections.id", ondelete="CASCADE"), nullable=False)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("commerce_merchants.id", ondelete="CASCADE"), nullable=False)
    commerce_order_id: Mapped[str] = mapped_column(ForeignKey("commerce_orders.id", ondelete="CASCADE"), nullable=False)
    idempotency_tag: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    shopify_order_gid: Mapped[str | None] = mapped_column(String(180))
    shopify_order_name: Mapped[str | None] = mapped_column(String(80))
    financial_status: Mapped[str | None] = mapped_column(String(40))
    fulfillment_status: Mapped[str | None] = mapped_column(String(40))
    link_state: Mapped[str] = mapped_column(String(24), nullable=False, default="creating")
    last_error: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class ShopifyVariantMap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shopify_variant_gid: str = Field(min_length=1, max_length=180)
    canonical_variant_id: str = Field(min_length=36, max_length=36)

    @field_validator("canonical_variant_id")
    @classmethod
    def uuid_value(cls, value: str) -> str:
        return str(uuid.UUID(value))


class ShopifyProductMap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    canonical_product_id: str = Field(min_length=36, max_length=36)
    variants: list[ShopifyVariantMap] = Field(min_length=1, max_length=250)

    @field_validator("canonical_product_id")
    @classmethod
    def product_uuid(cls, value: str) -> str:
        return str(uuid.UUID(value))


def _approved_merchant(actor, db: Session):
    return commerce.approved_merchant(db, actor)


def _connection_for_merchant(db: Session, merchant_id: str, *, active: bool = True) -> ShopifyConnection:
    connection = db.scalar(select(ShopifyConnection).where(ShopifyConnection.merchant_id == merchant_id))
    if connection is None or (active and connection.status != "active"):
        raise HTTPException(404, detail={"code": "SHOPIFY_CONNECTION_NOT_FOUND"})
    return connection


def _required_scopes(scopes: list[str]) -> set[str]:
    return {scope.strip() for scope in scopes if isinstance(scope, str) and scope.strip()}


def _save_token_response(connection: ShopifyConnection, data: dict[str, Any]) -> None:
    access = data.get("access_token")
    refresh = data.get("refresh_token")
    expires_in = data.get("expires_in")
    refresh_expires = data.get("refresh_token_expires_in")
    if (
        not isinstance(access, str) or not access
        or not isinstance(refresh, str) or not refresh
        or not isinstance(expires_in, int) or expires_in <= 0
        or not isinstance(refresh_expires, int) or refresh_expires <= 0
    ):
        raise HTTPException(502, detail={"code": "SHOPIFY_EXPIRING_TOKEN_RESPONSE_INVALID"})
    scopes = data.get("scope", connection.granted_scopes or [])
    if isinstance(scopes, str):
        scope_list = [value.strip() for value in scopes.split(",") if value.strip()]
    elif isinstance(scopes, list):
        scope_list = [str(value).strip() for value in scopes if str(value).strip()]
    else:
        scope_list = []
    connection.access_token_ciphertext = _seal(access, connection, "access")
    connection.refresh_token_ciphertext = _seal(refresh, connection, "refresh")
    connection.access_expires_at = utcnow() + timedelta(seconds=expires_in)
    connection.refresh_expires_at = utcnow() + timedelta(seconds=refresh_expires)
    connection.granted_scopes = sorted(set(scope_list))
    connection.status = "active" if REQUIRED_SCOPES.issubset(_required_scopes(scope_list)) else "scope_mismatch"
    connection.updated_at = utcnow()


def _refresh_access_token(connection: ShopifyConnection, db: Session) -> str:
    api_key, api_secret, _ = _oauth_config()
    locked = db.scalar(
        select(ShopifyConnection).where(ShopifyConnection.id == connection.id).with_for_update()
    )
    if locked is None or locked.status != "active":
        raise HTTPException(409, detail={"code": "SHOPIFY_REAUTH_REQUIRED"})
    if locked.access_expires_at and commerce._aware_utc(locked.access_expires_at) > utcnow() + timedelta(minutes=5):
        return _unseal(locked.access_token_ciphertext or "", locked, "access")
    if (
        not locked.refresh_token_ciphertext or not locked.refresh_expires_at
        or commerce._aware_utc(locked.refresh_expires_at) <= utcnow()
    ):
        locked.status = "reauthorization_required"
        db.commit()
        raise HTTPException(409, detail={"code": "SHOPIFY_REAUTH_REQUIRED"})
    try:
        response = httpx.post(
            "https://" + locked.shop_domain + "/admin/oauth/access_token",
            data={
                "client_id": api_key,
                "client_secret": api_secret,
                "grant_type": "refresh_token",
                "refresh_token": _unseal(locked.refresh_token_ciphertext, locked, "refresh"),
            },
            headers={"Accept": "application/json"},
            timeout=8.0,
            follow_redirects=False,
            trust_env=False,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "SHOPIFY_TOKEN_REFRESH_UNAVAILABLE"}) from exc
    if response.status_code != 200:
        locked.status = "reauthorization_required"
        db.commit()
        raise HTTPException(409, detail={"code": "SHOPIFY_REAUTH_REQUIRED"})
    try:
        _save_token_response(locked, response.json())
        if locked.status != "active":
            db.commit()
            raise HTTPException(403, detail={"code": "SHOPIFY_REQUIRED_SCOPES_MISSING"})
        db.commit()
        return _unseal(locked.access_token_ciphertext or "", locked, "access")
    except (ValueError, TypeError) as exc:
        db.rollback()
        raise HTTPException(502, detail={"code": "SHOPIFY_TOKEN_REFRESH_RESPONSE_INVALID"}) from exc


def _graphql(connection: ShopifyConnection, db: Session, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    if API_VERSION != "2026-10":
        raise HTTPException(503, detail={"code": "SHOPIFY_API_VERSION_NOT_APPROVED"})
    token = _refresh_access_token(connection, db)
    url = "https://" + connection.shop_domain + "/admin/api/" + API_VERSION + "/graphql.json"
    try:
        response = httpx.post(
            url,
            json={"query": query, "variables": variables or {}},
            headers={"X-Shopify-Access-Token": token, "Accept": "application/json"},
            timeout=12.0,
            follow_redirects=False,
            trust_env=False,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "SHOPIFY_API_UNAVAILABLE"}) from exc
    if response.status_code == 401:
        connection.status = "reauthorization_required"
        db.commit()
        raise HTTPException(409, detail={"code": "SHOPIFY_REAUTH_REQUIRED"})
    if response.status_code != 200:
        raise HTTPException(502, detail={"code": "SHOPIFY_API_REQUEST_FAILED", "upstream_status": response.status_code})
    try:
        body = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "SHOPIFY_GRAPHQL_RESPONSE_INVALID"}) from exc
    if not isinstance(body, dict) or body.get("errors"):
        errors = body.get("errors", []) if isinstance(body, dict) else []
        raise HTTPException(502, detail={"code": "SHOPIFY_GRAPHQL_ERROR", "errors": errors[:5]})
    data = body.get("data")
    if not isinstance(data, dict):
        raise HTTPException(502, detail={"code": "SHOPIFY_GRAPHQL_DATA_MISSING"})
    return data


def _register_webhooks(connection: ShopifyConnection, db: Session, callback_url: str) -> dict[str, str]:
    results: dict[str, str] = {}
    existing_topics: set[str] = set()
    try:
        existing_data = _graphql(connection, db, """
        query CirvannaExistingWebhooks {
          webhookSubscriptions(first: 100) { nodes { topic uri } }
        }
        """)
        existing_topics = {
            str(item.get("topic")) for item in (existing_data.get("webhookSubscriptions") or {}).get("nodes") or []
            if item.get("uri") == callback_url
        }
    except HTTPException:
        existing_topics = set()
    query = """
    mutation RegisterShopifyWebhook($topic: WebhookSubscriptionTopic!, $input: WebhookSubscriptionInput!) {
      webhookSubscriptionCreate(topic: $topic, webhookSubscription: $input) {
        webhookSubscription { id topic }
        userErrors { field message }
      }
    }
    """
    for topic in WEBHOOK_TOPICS:
        if topic in existing_topics:
            results[topic] = "registered"
            continue
        try:
            result = _graphql(connection, db, query, {
                "topic": topic,
                "input": {"callbackUrl": callback_url, "format": "JSON"},
            })
            payload = result.get("webhookSubscriptionCreate") or {}
            errors = payload.get("userErrors") or []
            results[topic] = "registered" if payload.get("webhookSubscription") and not errors else "error"
        except HTTPException:
            results[topic] = "error"
    connection.webhook_registration = results
    db.commit()
    return results


def _inventory_totals(inventory_item: dict[str, Any]) -> tuple[bool, int | None, int | None, bool]:
    tracked = inventory_item.get("tracked") is True
    if not tracked:
        return False, None, None, False
    connection = inventory_item.get("inventoryLevels") or {}
    nodes = connection.get("nodes") or []
    complete = not bool((connection.get("pageInfo") or {}).get("hasNextPage"))
    available = 0
    on_hand = 0
    for level in nodes:
        if level.get("isActive") is False:
            continue
        location = level.get("location") or {}
        if location.get("isActive") is False:
            continue
        values = {item.get("name"): item.get("quantity") for item in level.get("quantities") or []}
        if not isinstance(values.get("available"), int) or not isinstance(values.get("on_hand"), int):
            complete = False
            continue
        available += values["available"]
        on_hand += values["on_hand"]
    if not complete or not nodes:
        return True, None, None, False
    return True, available, on_hand, True


PRODUCTS_QUERY = """
query CirvannaShopifyVariantCatalog($first: Int!, $after: String) {
  shop { id name myshopifyDomain currencyCode }
  productVariants(first: $first, after: $after, sortKey: ID) {
    edges {
      cursor
      node {
        id title sku price selectedOptions
        product {
          id title handle vendor productType status updatedAt
        }
        inventoryItem {
          id tracked
          inventoryLevels(first: 50) {
            pageInfo { hasNextPage }
            nodes {
              isActive
              location { id name isActive }
              quantities(names: ["available", "on_hand"]) { name quantity }
            }
          }
        }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""



def _safe_sku(value: str | None, remote_gid: str) -> str:
    candidate = re.sub(r"[^A-Z0-9._-]", "-", (value or "").strip().upper()).strip(".-_")
    if not candidate:
        candidate = "SHOP-" + remote_gid.rsplit("/", 1)[-1]
    candidate = candidate[:80]
    if not commerce.SKU_RE.fullmatch(candidate):
        raise HTTPException(422, detail={"code": "SHOPIFY_VARIANT_SKU_INVALID"})
    return candidate


def _sync_mapped_variant(
    db: Session,
    connection: ShopifyConnection,
    snapshot: ShopifyVariantSnapshot,
    product_snapshot: ShopifyProductSnapshot,
) -> str | None:
    if not snapshot.local_variant_id:
        return None
    variant = db.get(commerce.Variant, snapshot.local_variant_id)
    if variant is None:
        snapshot.local_variant_id = None
        snapshot.mapping_state = "mapping_conflict"
        return "LOCAL_COMMERCE_VARIANT_MISSING"
    listing = db.get(commerce.Listing, variant.listing_id)
    if listing is None or listing.merchant_id != connection.merchant_id:
        snapshot.mapping_state = "mapping_conflict"
        return "LOCAL_VARIANT_OWNER_MISMATCH"
    if product_snapshot.remote_status != "ACTIVE":
        listing.state = "inactive"
        variant.state = "inactive"
    if snapshot.currency != variant.currency:
        # The shop's base currency changed. A silent rewrite would make existing
        # offer receipts and seller payable terms ambiguous; quarantine instead.
        snapshot.mapping_state = "currency_conflict"
        variant.observed_at = utcnow() - timedelta(days=30)
        return "SHOP_CURRENCY_CHANGED"
    sku_conflict = db.scalar(select(commerce.Variant.id).join(
        commerce.Listing, commerce.Variant.listing_id == commerce.Listing.id
    ).where(
        commerce.Listing.merchant_id == connection.merchant_id,
        commerce.Variant.listing_id == variant.listing_id,
        commerce.Variant.sku == snapshot.sku,
        commerce.Variant.id != variant.id,
    ))
    if sku_conflict:
        snapshot.mapping_state = "sku_conflict"
        variant.observed_at = utcnow() - timedelta(days=30)
        return "SHOPIFY_SKU_CONFLICT"
    sku_changed = variant.sku != snapshot.sku
    if sku_changed:
        variant.sku = snapshot.sku
    old_on_hand = variant.on_hand
    if snapshot.tracked and snapshot.inventory_complete and snapshot.available_quantity is not None:
        desired_on_hand = snapshot.available_quantity + variant.reserved_qty
        if desired_on_hand < variant.reserved_qty or desired_on_hand < 0:
            variant.observed_at = utcnow() - timedelta(days=30)
            snapshot.mapping_state = "inventory_conflict"
            return "SHOPIFY_INVENTORY_INVALID"
        variant.on_hand = desired_on_hand
        if desired_on_hand != old_on_hand:
            db.add(commerce.InventoryMovement(
                id=str(uuid.uuid4()), variant_id=variant.id,
                actor_user_id="shopify:" + connection.shop_domain,
                delta=desired_on_hand - old_on_hand,
                reason="shopify_inventory_reconciliation",
            ))
    else:
        # Unknown/untracked/incomplete inventory is not sellable evidence.
        variant.observed_at = utcnow() - timedelta(days=30)
        snapshot.mapping_state = "inventory_unknown"
        return "SHOPIFY_INVENTORY_NOT_VERIFIABLE"
    changed = variant.price_minor != snapshot.price_minor or variant.currency != snapshot.currency or sku_changed
    if changed:
        variant.price_minor = snapshot.price_minor
        variant.source_price_minor = snapshot.price_minor
        variant.source_currency = snapshot.currency
    if changed or old_on_hand != variant.on_hand:
        variant.version += 1
        variant.updated_at = utcnow()
    variant.observed_at = utcnow()
    snapshot.mapping_state = "mapped"
    return None


def _deactivate_product_listing(db: Session, connection: ShopifyConnection, product: ShopifyProductSnapshot) -> None:
    if product.remote_status == "ACTIVE":
        return
    if product.listing_id:
        listing = db.get(commerce.Listing, product.listing_id)
        if listing is not None and listing.merchant_id == connection.merchant_id:
            listing.state = "inactive"
    for snapshot in db.scalars(select(ShopifyVariantSnapshot).where(
        ShopifyVariantSnapshot.product_snapshot_id == product.id
    )).all():
        if snapshot.local_variant_id:
            variant = db.get(commerce.Variant, snapshot.local_variant_id)
            if variant is not None:
                variant.state = "inactive"
                variant.observed_at = utcnow() - timedelta(days=30)


def _sync_products(connection: ShopifyConnection, db: Session, *, max_pages: int = 20) -> dict[str, int | bool]:
    if connection.status != "active":
        raise HTTPException(409, detail={"code": "SHOPIFY_CONNECTION_NOT_ACTIVE"})
    after: str | None = connection.products_cursor
    variants_seen = inventory_conflicts = pages = 0
    products_seen_ids: set[str] = set()
    product_cache = {
        item.shopify_product_gid: item
        for item in db.scalars(select(ShopifyProductSnapshot).where(
            ShopifyProductSnapshot.connection_id == connection.id
        )).all()
    }
    variant_cache = {
        item.shopify_variant_gid: item
        for item in db.scalars(select(ShopifyVariantSnapshot).where(
            ShopifyVariantSnapshot.connection_id == connection.id
        )).all()
    }
    while pages < max_pages:
        data = _graphql(connection, db, PRODUCTS_QUERY, {"first": 20, "after": after})
        shop = data.get("shop") or {}
        shop_currency = str(shop.get("currencyCode") or "").upper()
        if not CURRENCY_RE.fullmatch(shop_currency):
            raise HTTPException(502, detail={"code": "SHOPIFY_SHOP_CURRENCY_INVALID"})
        if connection.shop_currency and connection.shop_currency != shop_currency:
            connection.status = "currency_review_required"
            db.commit()
            raise HTTPException(409, detail={"code": "SHOPIFY_SHOP_CURRENCY_CHANGED"})
        connection.shop_currency = shop_currency
        connection.shop_gid = shop.get("id")
        connection.shop_name = (shop.get("name") or "")[:180] or None
        variant_connection = data.get("productVariants") or {}
        for edge in variant_connection.get("edges") or []:
            remote_variant = edge.get("node") or {}
            remote_gid = remote_variant.get("id")
            product_node = remote_variant.get("product") or {}
            remote_product_gid = product_node.get("id")
            if (
                not isinstance(remote_gid, str)
                or not remote_gid.startswith("gid://shopify/ProductVariant/")
                or not isinstance(remote_product_gid, str)
                or not remote_product_gid.startswith("gid://shopify/Product/")
            ):
                continue
            product = product_cache.get(remote_product_gid)
            if product is None:
                product = ShopifyProductSnapshot(
                    id=str(uuid.uuid4()), connection_id=connection.id,
                    shopify_product_gid=remote_product_gid,
                    title=str(product_node.get("title") or "Untitled")[:255],
                    remote_status=str(product_node.get("status") or "UNKNOWN").upper(),
                    mapping_state="staged",
                    variants_complete=False,
                )
                db.add(product)
                db.flush()
                product_cache[remote_product_gid] = product
            else:
                # Any changed variant means this product's variant set must be
                # considered incomplete until the current full catalogue cycle ends.
                product.variants_complete = False
            product.title = str(product_node.get("title") or "Untitled")[:255]
            product.handle = str(product_node.get("handle") or "")[:255] or None
            product.vendor = str(product_node.get("vendor") or "")[:180] or None
            product.product_type = str(product_node.get("productType") or "")[:120] or None
            product.remote_status = str(product_node.get("status") or "UNKNOWN").upper()
            product.remote_updated_at = product_node.get("updatedAt")
            product.synced_at = utcnow()
            if product.catalog_product_id:
                product.mapping_state = "partial"
            _deactivate_product_listing(db, connection, product)
            products_seen_ids.add(product.id)
            inventory_item = remote_variant.get("inventoryItem") or {}
            tracked, available, on_hand, inventory_complete = _inventory_totals(inventory_item)
            sku = _safe_sku(remote_variant.get("sku"), remote_gid)
            sku_collision = db.scalar(select(ShopifyVariantSnapshot.id).where(
                ShopifyVariantSnapshot.product_snapshot_id == product.id,
                ShopifyVariantSnapshot.sku == sku,
                ShopifyVariantSnapshot.shopify_variant_gid != remote_gid,
            ))
            if sku_collision:
                suffix = remote_gid.rsplit("/", 1)[-1][-10:]
                sku = _safe_sku(sku[:68] + "-" + suffix, remote_gid)
            try:
                price_minor = _minor_units(remote_variant.get("price", "0"), shop_currency)
            except ValueError as exc:
                raise HTTPException(502, detail={"code": "SHOPIFY_VARIANT_PRICE_INVALID"}) from exc
            options = {
                str(option.get("name", ""))[:64]: str(option.get("value", ""))[:120]
                for option in remote_variant.get("selectedOptions") or []
                if option.get("name")
            }
            snapshot = variant_cache.get(remote_gid)
            if snapshot is None:
                snapshot = ShopifyVariantSnapshot(
                    id=str(uuid.uuid4()), connection_id=connection.id,
                    product_snapshot_id=product.id, shopify_variant_gid=remote_gid,
                    sku=sku, title=str(remote_variant.get("title") or "")[:255],
                    options=options, price_minor=price_minor, currency=shop_currency,
                    tracked=tracked, available_quantity=available, on_hand_quantity=on_hand,
                    inventory_complete=inventory_complete, mapping_state="staged",
                )
                db.add(snapshot)
                db.flush()
                variant_cache[remote_gid] = snapshot
            else:
                snapshot.product_snapshot_id = product.id
                snapshot.sku = sku
                snapshot.title = str(remote_variant.get("title") or "")[:255]
                snapshot.options = options
                snapshot.price_minor = price_minor
                snapshot.currency = shop_currency
                snapshot.tracked = tracked
                snapshot.available_quantity = available
                snapshot.on_hand_quantity = on_hand
                snapshot.inventory_complete = inventory_complete
            snapshot.shopify_inventory_item_gid = inventory_item.get("id")
            snapshot.synced_at = utcnow()
            if snapshot.local_variant_id:
                conflict = _sync_mapped_variant(db, connection, snapshot, product)
                if conflict:
                    inventory_conflicts += 1
            variants_seen += 1
            db.flush()
        page_info = variant_connection.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            after = None
            break
        after = page_info.get("endCursor")
        if not after:
            raise HTTPException(502, detail={"code": "SHOPIFY_VARIANT_CURSOR_MISSING"})
        pages += 1
    # Persist the cursor so repeated sync invocations progress through large stores.
    connection.products_cursor = after
    connection.products_synced_at = utcnow()
    connection.updated_at = utcnow()
    db.flush()
    if after is None:
        all_products = list(db.scalars(select(ShopifyProductSnapshot).where(
            ShopifyProductSnapshot.connection_id == connection.id
        )).all())
        for product in all_products:
            product_variants = list(db.scalars(select(ShopifyVariantSnapshot).where(
                ShopifyVariantSnapshot.product_snapshot_id == product.id
            )).all())
            product.variants_complete = bool(product_variants)
            if product.catalog_product_id:
                product.mapping_state = (
                    "mapped" if product_variants and all(item.local_variant_id for item in product_variants)
                    else "partial"
                )
    db.commit()
    return {
        "products_seen": len(products_seen_ids),
        "variants_seen": variants_seen,
        "inventory_conflicts": inventory_conflicts,
        "pages_processed": min(pages + 1, max_pages),
        "has_more": connection.products_cursor is not None,
    }



@router.get("/integrations/shopify/install")
def install_shopify(
    request: Request,
    actor: Annotated[commerce.Actor, Depends(commerce.require_actor)],
    db: Annotated[Session, Depends(commerce.get_db)],
    shop: str = Query(..., min_length=6, max_length=100),
):
    merchant = _approved_merchant(actor, db)
    api_key, _, base_url = _oauth_config()
    shop_domain = _shop_domain(shop)
    state = secrets.token_urlsafe(32)
    db.add(ShopifyOAuthState(
        id=str(uuid.uuid4()), merchant_id=merchant.id, shop_domain=shop_domain,
        state_sha256=hashlib.sha256(state.encode()).hexdigest(),
        expires_at=utcnow() + timedelta(minutes=OAUTH_STATE_TTL_MINUTES),
    ))
    db.commit()
    redirect_uri = base_url + "/integrations/shopify/callback"
    params = {
        "client_id": api_key,
        "scope": ",".join(sorted(REQUIRED_SCOPES)),
        "redirect_uri": redirect_uri,
        "state": state,
    }
    response = RedirectResponse(
        "https://" + shop_domain + "/admin/oauth/authorize?" + urlencode(params),
        status_code=302,
    )
    response.set_cookie(
        OAUTH_COOKIE, state, max_age=OAUTH_STATE_TTL_MINUTES * 60,
        httponly=True, secure=commerce._production_environment(),
        samesite="lax", path="/integrations/shopify/callback",
    )
    return response


@router.get("/integrations/shopify/callback")
def shopify_oauth_callback(
    request: Request,
    db: Annotated[Session, Depends(commerce.get_db)],
    code: str = Query(..., min_length=1, max_length=512),
    shop: str = Query(..., min_length=6, max_length=100),
    state: str = Query(..., min_length=20, max_length=200),
    hmac_value: str | None = Query(default=None, alias="hmac"),
):
    api_key, api_secret, base_url = _oauth_config()
    shop_domain = _shop_domain(shop)
    if not _oauth_hmac_valid(request.query_params, api_secret):
        raise HTTPException(401, detail={"code": "SHOPIFY_OAUTH_HMAC_INVALID"})
    cookie_state = request.cookies.get(OAUTH_COOKIE, "")
    if not cookie_state or not secrets.compare_digest(cookie_state, state):
        raise HTTPException(401, detail={"code": "SHOPIFY_OAUTH_STATE_COOKIE_MISMATCH"})
    state_hash = hashlib.sha256(state.encode()).hexdigest()
    state_row = db.scalar(select(ShopifyOAuthState).where(
        ShopifyOAuthState.state_sha256 == state_hash,
        ShopifyOAuthState.shop_domain == shop_domain,
        ShopifyOAuthState.consumed_at.is_(None),
    ).with_for_update())
    if state_row is None or commerce._aware_utc(state_row.expires_at) <= utcnow():
        raise HTTPException(401, detail={"code": "SHOPIFY_OAUTH_STATE_INVALID_OR_EXPIRED"})
    state_row.consumed_at = utcnow()
    merchant_id = state_row.merchant_id
    merchant = db.get(commerce.Merchant, merchant_id)
    if merchant is None or merchant.state != "approved":
        raise HTTPException(403, detail={"code": "MERCHANT_NOT_APPROVED"})
    db.commit()
    try:
        response = httpx.post(
            "https://" + shop_domain + "/admin/oauth/access_token",
            data={
                "client_id": api_key, "client_secret": api_secret, "code": code,
                "expiring": "1",
            },
            headers={"Accept": "application/json"},
            timeout=8.0,
            follow_redirects=False,
            trust_env=False,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "SHOPIFY_OAUTH_EXCHANGE_UNAVAILABLE"}) from exc
    if response.status_code != 200:
        raise HTTPException(502, detail={"code": "SHOPIFY_OAUTH_EXCHANGE_FAILED"})
    try:
        token_payload = response.json()
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "SHOPIFY_OAUTH_TOKEN_RESPONSE_INVALID"}) from exc
    connection = db.scalar(select(ShopifyConnection).where(
        (ShopifyConnection.merchant_id == merchant_id) | (ShopifyConnection.shop_domain == shop_domain)
    ).with_for_update())
    if connection is not None and (connection.merchant_id != merchant_id or connection.shop_domain != shop_domain):
        raise HTTPException(409, detail={"code": "SHOPIFY_STORE_OR_MERCHANT_ALREADY_LINKED"})
    if connection is None:
        connection = ShopifyConnection(
            id=str(uuid.uuid4()), merchant_id=merchant_id, shop_domain=shop_domain,
            status="pending_scope_check",
        )
        db.add(connection)
    _save_token_response(connection, token_payload)
    db.commit()
    if connection.status == "scope_mismatch":
        raise HTTPException(403, detail={"code": "SHOPIFY_REQUIRED_SCOPES_MISSING"})
    callback_url = _webhook_base_url() + "/webhooks/shopify"
    registrations = _register_webhooks(connection, db, callback_url)
    response = RedirectResponse(
        base_url + "/brand-portal.html?shopify=connected",
        status_code=303,
    )
    response.delete_cookie(OAUTH_COOKIE, path="/integrations/shopify/callback")
    # No access token, refresh token, or OAuth code is ever placed in a URL.
    return response


@router.get("/integrations/shopify/connection")
def get_shopify_connection(
    actor: Annotated[commerce.Actor, Depends(commerce.require_actor)],
    db: Annotated[Session, Depends(commerce.get_db)],
):
    merchant = _approved_merchant(actor, db)
    connection = db.scalar(select(ShopifyConnection).where(ShopifyConnection.merchant_id == merchant.id))
    if connection is None:
        return {"connected": False, "provider": "shopify"}
    return {
        "connected": connection.status == "active",
        "provider": "shopify",
        "shop_domain": connection.shop_domain,
        "shop_name": connection.shop_name,
        "shop_currency": connection.shop_currency,
        "status": connection.status,
        "granted_scopes": connection.granted_scopes,
        "webhook_registration": connection.webhook_registration,
        "webhooks_complete": all(
            connection.webhook_registration.get(topic) == "registered"
            for topic in WEBHOOK_TOPICS
        ),
        "products_synced_at": connection.products_synced_at.isoformat() if connection.products_synced_at else None,
        "orders_reconciled_at": connection.orders_reconciled_at.isoformat() if connection.orders_reconciled_at else None,
        "access_token_expires_at": connection.access_expires_at.isoformat() if connection.access_expires_at else None,
        "refresh_token_expires_at": connection.refresh_expires_at.isoformat() if connection.refresh_expires_at else None,
        "product_sync_in_progress": connection.products_cursor is not None,
    }


@router.post("/integrations/shopify/disconnect")
def disconnect_shopify(
    actor: Annotated[commerce.Actor, Depends(commerce.require_actor)],
    db: Annotated[Session, Depends(commerce.get_db)],
):
    merchant = _approved_merchant(actor, db)
    connection = db.scalar(select(ShopifyConnection).where(ShopifyConnection.merchant_id == merchant.id))
    if connection is None:
        return {"disconnected": True}
    connection.access_token_ciphertext = None
    connection.refresh_token_ciphertext = None
    connection.status = "revoked"
    connection.revoked_at = utcnow()
    connection.updated_at = utcnow()
    db.commit()
    return {"disconnected": True, "shop_domain": connection.shop_domain}


@router.post("/integrations/shopify/sync/products")
def sync_shopify_products(
    actor: Annotated[commerce.Actor, Depends(commerce.require_actor)],
    db: Annotated[Session, Depends(commerce.get_db)],
):
    merchant = _approved_merchant(actor, db)
    connection = _connection_for_merchant(db, merchant.id)
    return _sync_products(connection, db)


@router.get("/integrations/shopify/staged-products")
def list_staged_shopify_products(
    actor: Annotated[commerce.Actor, Depends(commerce.require_actor)],
    db: Annotated[Session, Depends(commerce.get_db)],
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    merchant = _approved_merchant(actor, db)
    connection = _connection_for_merchant(db, merchant.id)
    rows = list(db.scalars(
        select(ShopifyProductSnapshot).where(
            ShopifyProductSnapshot.connection_id == connection.id
        ).order_by(ShopifyProductSnapshot.synced_at.desc()).offset(offset).limit(limit)
    ).all())
    products = []
    for row in rows:
        variants = list(db.scalars(select(ShopifyVariantSnapshot).where(
            ShopifyVariantSnapshot.product_snapshot_id == row.id
        ).order_by(ShopifyVariantSnapshot.sku)).all())
        products.append({
            "snapshot_id": row.id,
            "shopify_product_gid": row.shopify_product_gid,
            "title": row.title,
            "vendor": row.vendor,
            "product_type": row.product_type,
            "remote_status": row.remote_status,
            "mapping_state": row.mapping_state,
            "variants_complete": row.variants_complete,
            "variants": [{
                "shopify_variant_gid": item.shopify_variant_gid,
                "sku": item.sku, "title": item.title, "options": item.options,
                "price_minor": item.price_minor, "currency": item.currency,
                "tracked": item.tracked, "available_quantity": item.available_quantity,
                "inventory_complete": item.inventory_complete,
                "mapping_state": item.mapping_state,
                "canonical_variant_id": item.canonical_variant_id,
            } for item in variants],
        })
    return {"items": products, "offset": offset, "limit": limit, "visibility": "merchant_only_staging"}


@router.post("/integrations/shopify/products/{snapshot_id}/map")
def map_shopify_product(
    snapshot_id: uuid.UUID,
    payload: ShopifyProductMap,
    actor: Annotated[commerce.Actor, Depends(commerce.require_actor)],
    db: Annotated[Session, Depends(commerce.get_db)],
):
    merchant = _approved_merchant(actor, db)
    connection = _connection_for_merchant(db, merchant.id)
    product_snapshot = db.get(ShopifyProductSnapshot, str(snapshot_id))
    if product_snapshot is None or product_snapshot.connection_id != connection.id:
        raise HTTPException(404, detail={"code": "SHOPIFY_PRODUCT_SNAPSHOT_NOT_FOUND"})
    if product_snapshot.remote_status != "ACTIVE" or not product_snapshot.variants_complete:
        raise HTTPException(409, detail={"code": "SHOPIFY_PRODUCT_NOT_READY_FOR_MAPPING"})
    catalog = commerce.CatalogClient()
    canonical_product = catalog.product(payload.canonical_product_id)
    if product_snapshot.catalog_product_id and product_snapshot.catalog_product_id != canonical_product["product_id"]:
        raise HTTPException(409, detail={"code": "SHOPIFY_PRODUCT_CANONICAL_MAPPING_IMMUTABLE"})
    if len(set(item.canonical_variant_id for item in payload.variants)) != len(payload.variants):
        raise HTTPException(422, detail={"code": "DUPLICATE_CANONICAL_VARIANT_MAPPING"})
    listing = db.scalar(select(commerce.Listing).where(
        commerce.Listing.merchant_id == merchant.id,
        commerce.Listing.catalog_product_id == canonical_product["product_id"],
    ))
    if listing is None:
        listing = commerce.Listing(
            id=str(uuid.uuid4()), merchant_id=merchant.id,
            catalog_product_id=canonical_product["product_id"],
            product_name=str(canonical_product["name"])[:180],
            category=str(canonical_product.get("category") or "uncategorized")[:80],
            image_urls=commerce.trusted_catalog_image_urls(canonical_product),
            state="active",
        )
        db.add(listing)
        db.flush()
    requested = {item.shopify_variant_gid: item.canonical_variant_id for item in payload.variants}
    if len(requested) != len(payload.variants):
        raise HTTPException(422, detail={"code": "DUPLICATE_SHOPIFY_VARIANT_MAPPING"})
    snapshots = list(db.scalars(select(ShopifyVariantSnapshot).where(
        ShopifyVariantSnapshot.product_snapshot_id == product_snapshot.id
    )).all())
    by_gid = {item.shopify_variant_gid: item for item in snapshots}
    if not set(requested).issubset(by_gid):
        raise HTTPException(422, detail={"code": "SHOPIFY_VARIANT_MAPPING_NOT_IN_PRODUCT"})
    existing_canonical = {
        item.canonical_variant_id for item in snapshots
        if item.canonical_variant_id and item.shopify_variant_gid not in requested
    }
    if existing_canonical.intersection(requested.values()):
        raise HTTPException(409, detail={"code": "CANONICAL_VARIANT_ALREADY_MAPPED"})
    for remote_gid in requested:
        target = by_gid[remote_gid]
        sku_collision = db.scalar(select(commerce.Variant.id).where(
            commerce.Variant.listing_id == listing.id,
            commerce.Variant.sku == target.sku,
            commerce.Variant.id != (target.local_variant_id or ""),
        ))
        if sku_collision:
            raise HTTPException(409, detail={"code": "SHOPIFY_SKU_CONFLICT_WITH_EXISTING_LISTING"})
    results = []
    for remote_gid, canonical_variant_id in requested.items():
        snapshot = by_gid[remote_gid]
        catalog.variant(canonical_variant_id, canonical_product["product_id"])
        duplicate_local = db.scalar(select(commerce.Variant).join(
            commerce.Listing, commerce.Variant.listing_id == commerce.Listing.id
        ).where(
            commerce.Listing.merchant_id == merchant.id,
            commerce.Variant.canonical_variant_id == canonical_variant_id,
            commerce.Variant.id != (snapshot.local_variant_id or ""),
        ))
        if duplicate_local:
            raise HTTPException(409, detail={"code": "CANONICAL_VARIANT_ALREADY_OFFERED"})
        if snapshot.local_variant_id:
            local = db.get(commerce.Variant, snapshot.local_variant_id)
            if local is None or local.listing_id != listing.id:
                raise HTTPException(409, detail={"code": "SHOPIFY_LOCAL_VARIANT_MAPPING_CONFLICT"})
        else:
            local = commerce.Variant(
                id=str(uuid.uuid4()), listing_id=listing.id,
                sku=snapshot.sku, options=snapshot.options,
                price_minor=snapshot.price_minor, currency=snapshot.currency,
                source_price_minor=snapshot.price_minor, source_currency=snapshot.currency,
                on_hand=0, reserved_qty=0, state="active", version=1,
                canonical_variant_id=canonical_variant_id,
                observed_at=utcnow() - timedelta(days=30),
            )
            db.add(local)
            db.flush()
            snapshot.local_variant_id = local.id
        snapshot.canonical_variant_id = canonical_variant_id
        snapshot.mapping_state = "mapped"
        conflict = _sync_mapped_variant(db, connection, snapshot, product_snapshot)
        if conflict:
            results.append({"shopify_variant_gid": remote_gid, "status": "mapped_inventory_held", "reason": conflict})
        else:
            results.append({"shopify_variant_gid": remote_gid, "status": "mapped", "commerce_variant_id": local.id})
    product_snapshot.catalog_product_id = canonical_product["product_id"]
    product_snapshot.listing_id = listing.id
    product_snapshot.mapping_state = "mapped" if all(
        item.local_variant_id for item in snapshots
    ) else "partial"
    db.commit()
    return {
        "listing_id": listing.id,
        "catalog_product_id": product_snapshot.catalog_product_id,
        "mapping_state": product_snapshot.mapping_state,
        "variants": results,
        "display_authorization": "not_granted_by_mapping",
        "note": "Marketplace display still requires active market eligibility and a fresh CAL SHOW decision.",
    }


@router.post("/integrations/shopify/markets/{country_code}/sync-pricing")
def sync_shopify_contextual_pricing(
    country_code: str,
    actor: Annotated[commerce.Actor, Depends(commerce.require_actor)],
    db: Annotated[Session, Depends(commerce.get_db)],
):
    merchant = _approved_merchant(actor, db)
    connection = _connection_for_merchant(db, merchant.id)
    country = country_code.strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", country):
        raise HTTPException(422, detail={"code": "MARKET_COUNTRY_CODE_INVALID"})
    market = db.scalar(select(commerce.MerchantOperatingMarket).where(
        commerce.MerchantOperatingMarket.merchant_id == merchant.id,
        commerce.MerchantOperatingMarket.market_country_code == country,
    ))
    if market is None:
        raise HTTPException(409, detail={"code": "MERCHANT_MARKET_NOT_DECLARED"})
    query = """
    query CirvannaContextualVariantPrice($id: ID!, $country: CountryCode!) {
      node(id: $id) {
        ... on ProductVariant {
          id
          contextualPricing(context: {country: $country}) {
            price { amount currencyCode }
            compareAtPrice { amount currencyCode }
          }
        }
      }
    }
    """
    snapshots = list(db.scalars(select(ShopifyVariantSnapshot).join(
        ShopifyProductSnapshot, ShopifyProductSnapshot.id == ShopifyVariantSnapshot.product_snapshot_id
    ).where(
        ShopifyVariantSnapshot.connection_id == connection.id,
        ShopifyProductSnapshot.mapping_state.in_(["mapped", "partial"]),
    )).limit(250).all())
    updated = 0
    for snapshot in snapshots:
        data = _graphql(connection, db, query, {"id": snapshot.shopify_variant_gid, "country": country})
        node = data.get("node") or {}
        contextual = node.get("contextualPricing") or {}
        price = contextual.get("price")
        if not price or not price.get("currencyCode") or price.get("amount") is None:
            continue
        currency = str(price["currencyCode"]).upper()
        amount_minor = _minor_units(price["amount"], currency)
        snapshot.regional_prices = {
            **(snapshot.regional_prices or {}),
            country: {
                "amount_minor": amount_minor,
                "currency": currency,
                "observed_at": utcnow().isoformat(),
                "source": "shopify_markets_contextual_pricing",
                "landed_cost": False,
                "fx_quote": False,
                "tax_and_fulfillment_included": False,
            },
        }
        updated += 1
    db.commit()
    return {
        "country_code": country, "variants_updated": updated,
        "price_semantics": "merchant contextual item price only; not a landed price or Commerce FX/tax/fulfillment quote",
    }


def _resource_gid(topic: str, payload: dict[str, Any]) -> str | None:
    raw_gid = payload.get("admin_graphql_api_id")
    if isinstance(raw_gid, str) and GID_RE.fullmatch(raw_gid):
        return raw_gid
    raw_id = payload.get("id")
    if raw_id is None:
        return None
    kind = {
        "products/create": "Product", "products/update": "Product", "products/delete": "Product",
        "orders/create": "Order", "orders/updated": "Order",
        "orders/cancelled": "Order", "orders/fulfilled": "Order",
    }.get(topic)
    if kind and str(raw_id).isdigit():
        return "gid://shopify/" + kind + "/" + str(raw_id)
    return None


@router.post("/webhooks/shopify")
async def receive_shopify_webhook(
    request: Request,
    db: Annotated[Session, Depends(commerce.get_db)],
    signature: str | None = Header(default=None, alias="X-Shopify-Hmac-Sha256"),
    topic_header: str | None = Header(default=None, alias="X-Shopify-Topic"),
    shop_header: str | None = Header(default=None, alias="X-Shopify-Shop-Domain"),
    delivery_header: str | None = Header(default=None, alias="X-Shopify-Webhook-Id"),
    event_header: str | None = Header(default=None, alias="X-Shopify-Event-Id"),
):
    _, secret, _ = _oauth_config()
    raw = await request.body()
    if not _webhook_hmac_valid(raw, signature, secret):
        raise HTTPException(401, detail={"code": "SHOPIFY_WEBHOOK_HMAC_INVALID"})
    shop_domain = _shop_domain(shop_header or "")
    topic = (topic_header or "").strip().lower()
    delivery_id = (delivery_header or "").strip()
    if not topic or not delivery_id or len(delivery_id) > 180:
        raise HTTPException(400, detail={"code": "SHOPIFY_WEBHOOK_HEADERS_INVALID"})
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, detail={"code": "SHOPIFY_WEBHOOK_PAYLOAD_INVALID"}) from exc
    if not isinstance(payload, dict):
        raise HTTPException(400, detail={"code": "SHOPIFY_WEBHOOK_PAYLOAD_INVALID"})
    connection = db.scalar(select(ShopifyConnection).where(ShopifyConnection.shop_domain == shop_domain))
    # Shopify may retry app/uninstalled after the connection has already been removed.
    if topic == "app/uninstalled":
        if connection:
            connection.status = "revoked"
            connection.access_token_ciphertext = None
            connection.refresh_token_ciphertext = None
            connection.revoked_at = utcnow()
            connection.updated_at = utcnow()
            db.commit()
        return {"received": True, "revoked": bool(connection)}
    if connection is None:
        return {"received": True, "ignored": True}
    if topic not in {
        "products/create", "products/update", "products/delete", "inventory_levels/update",
        "orders/create", "orders/updated", "orders/cancelled", "orders/fulfilled",
        "shop/redact", "customers/data_request", "customers/redact",
    }:
        return {"received": True, "ignored": True}
    existing = db.scalar(select(ShopifyWebhookEvent).where(
        ShopifyWebhookEvent.shop_domain == shop_domain,
        ShopifyWebhookEvent.delivery_id == delivery_id,
    ))
    if existing is not None:
        return {"received": True, "duplicate": True}
    event = ShopifyWebhookEvent(
        id=str(uuid.uuid4()), shop_domain=shop_domain, delivery_id=delivery_id,
        event_id=event_header, topic=topic,
        resource_gid=_resource_gid(topic, payload),
        payload_sha256=hashlib.sha256(raw).hexdigest(),
        state="pending",
    )
    db.add(event)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"received": True, "duplicate": True}
    # Raw payloads are deliberately not persisted: the durable event queue stores
    # identifiers and a digest only, avoiding customer/contact/address data.
    return {"received": True, "queued": True, "event_id": event.id}


ORDER_STATUS_QUERY = """
query CirvannaOrderStatus($id: ID!) {
  node(id: $id) {
    ... on Order {
      id name displayFinancialStatus displayFulfillmentStatus updatedAt cancelledAt
    }
  }
}
"""


def _retire_deleted_product(connection: ShopifyConnection, db: Session, remote_gid: str | None) -> bool:
    if not remote_gid or not remote_gid.startswith("gid://shopify/Product/"):
        return False
    product = db.scalar(select(ShopifyProductSnapshot).where(
        ShopifyProductSnapshot.connection_id == connection.id,
        ShopifyProductSnapshot.shopify_product_gid == remote_gid,
    ))
    if product is None:
        return False
    product.remote_status = "DELETED"
    product.mapping_state = "retired"
    listing = db.get(commerce.Listing, product.listing_id) if product.listing_id else None
    if listing is not None and listing.merchant_id == connection.merchant_id:
        listing.state = "inactive"
    snapshots = list(db.scalars(select(ShopifyVariantSnapshot).where(
        ShopifyVariantSnapshot.product_snapshot_id == product.id
    )).all())
    for snapshot in snapshots:
        snapshot.mapping_state = "retired"
        if snapshot.local_variant_id:
            variant = db.get(commerce.Variant, snapshot.local_variant_id)
            if variant is not None:
                variant.state = "inactive"
                variant.observed_at = utcnow() - timedelta(days=30)
    return True


def _sync_order_status(connection: ShopifyConnection, db: Session, remote_gid: str | None) -> bool:
    if not remote_gid or not remote_gid.startswith("gid://shopify/Order/"):
        return False
    link = db.scalar(select(ShopifyOrderLink).where(
        ShopifyOrderLink.connection_id == connection.id,
        ShopifyOrderLink.shopify_order_gid == remote_gid,
    ))
    if link is None:
        return False
    data = _graphql(connection, db, ORDER_STATUS_QUERY, {"id": remote_gid})
    order = data.get("node")
    if not isinstance(order, dict) or order.get("id") != remote_gid:
        return False
    link.shopify_order_name = str(order.get("name") or "")[:80] or None
    link.financial_status = order.get("displayFinancialStatus")
    link.fulfillment_status = order.get("displayFulfillmentStatus")
    link.link_state = "synced"
    link.last_error = None
    link.updated_at = utcnow()
    return True


def _claim_events(db: Session, limit: int) -> list[ShopifyWebhookEvent]:
    stale_processing_before = utcnow() - timedelta(minutes=5)
    rows = list(db.scalars(select(ShopifyWebhookEvent).where(
        or_(
            ShopifyWebhookEvent.state == "pending",
            (ShopifyWebhookEvent.state == "processing")
            & (ShopifyWebhookEvent.last_attempt_at.is_not(None))
            & (ShopifyWebhookEvent.last_attempt_at <= stale_processing_before),
        )
    ).order_by(ShopifyWebhookEvent.received_at).limit(limit).with_for_update()).all())
    for event in rows:
        event.state = "processing"
        event.attempts += 1
        event.last_attempt_at = utcnow()
    db.commit()
    return rows


@router.post("/internal/shopify/process-events")
def process_shopify_events(
    db: Annotated[Session, Depends(commerce.get_db)],
    token: str | None = Header(default=None, alias="X-Commerce-Shopify-Sync-Token"),
    limit: int = Query(25, ge=1, le=100),
):
    expected = os.getenv("COMMERCE_SHOPIFY_SYNC_TOKEN", "").strip()
    if len(expected.encode()) < 32 or not token or not hmac.compare_digest(token, expected):
        raise HTTPException(401, detail={"code": "SHOPIFY_SYNC_AUTH_FAILED"})
    events = _claim_events(db, limit)
    processed = failed = ignored = 0
    for event in events:
        try:
            if event.topic == "shop/redact":
                connection = db.scalar(select(ShopifyConnection).where(
                    ShopifyConnection.shop_domain == event.shop_domain
                ))
                if connection:
                    db.execute(ShopifyWebhookEvent.__table__.delete().where(
                        ShopifyWebhookEvent.shop_domain == event.shop_domain,
                        ShopifyWebhookEvent.id != event.id,
                    ))
                    db.execute(ShopifyOrderLink.__table__.delete().where(
                        ShopifyOrderLink.connection_id == connection.id
                    ))
                    db.execute(ShopifyVariantSnapshot.__table__.delete().where(
                        ShopifyVariantSnapshot.connection_id == connection.id
                    ))
                    db.execute(ShopifyProductSnapshot.__table__.delete().where(
                        ShopifyProductSnapshot.connection_id == connection.id
                    ))
                    connection.access_token_ciphertext = None
                    connection.refresh_token_ciphertext = None
                    db.delete(connection)
            elif event.topic in {"customers/data_request", "customers/redact"}:
                # Cirvanna does not request customer scopes or persist Shopify
                # customer records/addresses; keep this compliance handler PII-free.
                ignored += 1
            elif event.topic.startswith("orders/"):
                connection = db.scalar(select(ShopifyConnection).where(
                    ShopifyConnection.shop_domain == event.shop_domain
                ))
                if connection:
                    _sync_order_status(connection, db, event.resource_gid)
            elif event.topic == "products/delete":
                connection = db.scalar(select(ShopifyConnection).where(
                    ShopifyConnection.shop_domain == event.shop_domain
                ))
                if connection:
                    _retire_deleted_product(connection, db, event.resource_gid)
            elif event.topic in {"products/create", "products/update", "inventory_levels/update"}:
                connection = db.scalar(select(ShopifyConnection).where(
                    ShopifyConnection.shop_domain == event.shop_domain
                ))
                if connection:
                    _sync_products(connection, db)
            event.state = "processed"
            event.processed_at = utcnow()
            event.last_error = None
            db.commit()
            processed += 1
        except Exception as exc:
            db.rollback()
            failed += 1
            current = db.get(ShopifyWebhookEvent, event.id)
            if current:
                current.state = "dead_letter" if current.attempts >= 8 else "pending"
                current.last_error = type(exc).__name__[:120]
                db.commit()
    return {
        "claimed": len(events), "processed": processed,
        "failed": failed, "compliance_events_acknowledged": ignored,
    }


def _create_paid_order(connection: ShopifyConnection, db: Session, commerce_order: commerce.CommerceOrder, merchant_id: str) -> ShopifyOrderLink:
    items = list(db.scalars(select(commerce.OrderItem).where(
        commerce.OrderItem.order_id == commerce_order.id,
        commerce.OrderItem.merchant_id == merchant_id,
    )).all())
    if not items:
        raise HTTPException(409, detail={"code": "SHOPIFY_ORDER_HAS_NO_MERCHANT_LINES"})
    snapshots_by_local = {
        snapshot.local_variant_id: snapshot
        for snapshot in db.scalars(select(ShopifyVariantSnapshot).where(
            ShopifyVariantSnapshot.connection_id == connection.id,
            ShopifyVariantSnapshot.local_variant_id.is_not(None),
        )).all()
    }
    line_items = []
    total_shop_minor = 0
    presentment_total_minor = 0
    presentment_currency = commerce_order.currency.upper()
    for item in items:
        snapshot = snapshots_by_local.get(item.variant_id)
        if snapshot is None or snapshot.mapping_state != "mapped":
            raise HTTPException(409, detail={"code": "SHOPIFY_ORDER_VARIANT_MAPPING_MISSING"})
        if snapshot.currency != connection.shop_currency:
            raise HTTPException(409, detail={"code": "SHOPIFY_ORDER_SHOP_CURRENCY_MISMATCH"})
        source_minor = item.source_unit_price_minor
        source_currency = (item.source_currency or "").upper()
        if source_minor is None:
            source_minor = item.unit_price_minor
            source_currency = presentment_currency
        if source_currency != connection.shop_currency:
            raise HTTPException(409, detail={"code": "SHOPIFY_ORDER_SOURCE_CURRENCY_MISMATCH"})
        shop_line_minor = source_minor * item.quantity
        presentment_line_minor = item.unit_price_minor * item.quantity
        total_shop_minor += shop_line_minor
        presentment_total_minor += presentment_line_minor
        line_items.append({
            "variantId": snapshot.shopify_variant_gid,
            "quantity": item.quantity,
            "priceSet": {
                "shopMoney": {
                    "amount": _major_units(source_minor, connection.shop_currency),
                    "currencyCode": connection.shop_currency,
                },
                "presentmentMoney": {
                    "amount": _major_units(item.unit_price_minor, presentment_currency),
                    "currencyCode": presentment_currency,
                },
            },
        })
    if (commerce_order.fulfillment_total_minor or 0) != 0 or (commerce_order.tax_total_minor or 0) != 0:
        raise HTTPException(409, detail={"code": "SHOPIFY_ORDER_CHARGES_NOT_ALLOCATED_PER_MERCHANT"})
    if commerce_order.total_minor is not None and commerce_order.total_minor != commerce_order.subtotal_minor:
        raise HTTPException(409, detail={"code": "SHOPIFY_ORDER_TOTAL_REQUIRES_MERCHANT_ALLOCATION"})
    # Shopify imports one sub-order per merchant. Source shop money must match
    # the seller's immutable offer snapshots; presentment money remains buyer
    # checkout currency. No customer identity or delivery address is exported.
    tag = "cirvanna-link-" + uuid.uuid5(uuid.NAMESPACE_URL, commerce_order.id + ":" + merchant_id).hex[:24]
    link = db.scalar(select(ShopifyOrderLink).where(
        ShopifyOrderLink.commerce_order_id == commerce_order.id,
        ShopifyOrderLink.merchant_id == merchant_id,
    ))
    if link is None:
        link = ShopifyOrderLink(
            id=str(uuid.uuid4()), connection_id=connection.id, merchant_id=merchant_id,
            commerce_order_id=commerce_order.id, idempotency_tag=tag, link_state="creating",
        )
        db.add(link)
        db.commit()
    if link.shopify_order_gid:
        return link
    # Reconcile an ambiguous timeout before re-issuing a non-idempotent mutation.
    lookup = _graphql(connection, db, """
      query CirvannaFindImportedOrder($query: String!) {
        orders(first: 5, query: $query, sortKey: CREATED_AT, reverse: true) {
          nodes { id name displayFinancialStatus displayFulfillmentStatus updatedAt }
        }
      }
    """, {"query": "tag:" + tag})
    existing = (lookup.get("orders") or {}).get("nodes") or []
    if existing:
        remote = existing[0]
    else:
        mutation = """
        mutation CirvannaImportPaidOrder($order: OrderCreateOrderInput!, $options: OrderCreateOptionsInput) {
          orderCreate(order: $order, options: $options) {
            order { id name displayFinancialStatus displayFulfillmentStatus updatedAt }
            userErrors { field message }
          }
        }
        """
        variables = {"order": {
            "currency": connection.shop_currency,
            "presentmentCurrency": presentment_currency,
            "financialStatus": "PAID",
            "sourceName": "Cirvanna",
            "sourceIdentifier": commerce_order.id,
            "tags": ["Cirvanna", "Cirvanna-Externally-Paid", tag],
            "note": "Paid through Cirvanna. This Shopify order is an external order record; do not collect payment again.",
            "customAttributes": [
                {"key": "cirvanna_order_id", "value": commerce_order.id},
                {"key": "cirvanna_order_link_id", "value": link.id},
            ],
            "lineItems": line_items,
        }}
        data = _graphql(connection, db, mutation, {
            "order": variables["order"],
            "options": {
                "inventoryBehaviour": "DECREMENT_OBEYING_POLICY",
                "sendReceipt": False,
                "sendFulfillmentReceipt": False,
            },
        })
        result = data.get("orderCreate") or {}
        errors = result.get("userErrors") or []
        remote = result.get("order")
        if errors or not isinstance(remote, dict) or not remote.get("id"):
            link.link_state = "failed"
            link.last_error = json.dumps(errors[:3], ensure_ascii=True)[:300] or "SHOPIFY_ORDER_CREATE_FAILED"
            db.commit()
            raise HTTPException(502, detail={"code": "SHOPIFY_ORDER_CREATE_FAILED"})
    link.shopify_order_gid = remote["id"]
    link.shopify_order_name = str(remote.get("name") or "")[:80] or None
    link.financial_status = remote.get("displayFinancialStatus")
    link.fulfillment_status = remote.get("displayFulfillmentStatus")
    link.link_state = "synced"
    link.last_error = None
    link.updated_at = utcnow()
    db.commit()
    return link


@router.post("/internal/shopify/export-paid-orders")
def export_paid_orders_to_shopify(
    db: Annotated[Session, Depends(commerce.get_db)],
    token: str | None = Header(default=None, alias="X-Commerce-Shopify-Sync-Token"),
    limit: int = Query(25, ge=1, le=100),
):
    expected = os.getenv("COMMERCE_SHOPIFY_SYNC_TOKEN", "").strip()
    if len(expected.encode()) < 32 or not token or not hmac.compare_digest(token, expected):
        raise HTTPException(401, detail={"code": "SHOPIFY_SYNC_AUTH_FAILED"})
    pairs = db.execute(
        select(commerce.CommerceOrder, commerce.OrderItem.merchant_id)
        .join(commerce.OrderItem, commerce.OrderItem.order_id == commerce.CommerceOrder.id)
        .join(ShopifyConnection, ShopifyConnection.merchant_id == commerce.OrderItem.merchant_id)
        .outerjoin(ShopifyOrderLink, and_(
            ShopifyOrderLink.commerce_order_id == commerce.CommerceOrder.id,
            ShopifyOrderLink.merchant_id == commerce.OrderItem.merchant_id,
        ))
        .where(
            commerce.CommerceOrder.state == "paid",
            ShopifyConnection.status == "active",
            or_(ShopifyOrderLink.id.is_(None), ShopifyOrderLink.link_state != "synced"),
        )
        .order_by(commerce.CommerceOrder.paid_at)
        .limit(limit)
    ).all()
    pending_pairs = {(order.id, merchant_id): (order, merchant_id) for order, merchant_id in pairs}
    exported = skipped = failed = 0
    errors = []
    for order, merchant_id in pending_pairs.values():
        link = db.scalar(select(ShopifyOrderLink).where(
            ShopifyOrderLink.commerce_order_id == order.id,
            ShopifyOrderLink.merchant_id == merchant_id,
        ))
        if link and link.link_state == "synced":
            skipped += 1
            continue
        connection = db.scalar(select(ShopifyConnection).where(
            ShopifyConnection.merchant_id == merchant_id,
            ShopifyConnection.status == "active",
        ))
        if connection is None:
            skipped += 1
            continue
        try:
            _create_paid_order(connection, db, order, merchant_id)
            exported += 1
        except HTTPException as exc:
            failed += 1
            errors.append({"order_id": order.id, "merchant_id": merchant_id, "code": (exc.detail or {}).get("code", "SHOPIFY_EXPORT_FAILED")})
        except SQLAlchemyError:
            db.rollback()
            failed += 1
            errors.append({"order_id": order.id, "merchant_id": merchant_id, "code": "SHOPIFY_DATABASE_ERROR"})
    return {"exported": exported, "skipped": skipped, "failed": failed, "errors": errors[:20]}


@router.post("/internal/shopify/reconcile")
def reconcile_shopify(
    db: Annotated[Session, Depends(commerce.get_db)],
    token: str | None = Header(default=None, alias="X-Commerce-Shopify-Sync-Token"),
    limit: int = Query(100, ge=1, le=500),
):
    expected = os.getenv("COMMERCE_SHOPIFY_SYNC_TOKEN", "").strip()
    if len(expected.encode()) < 32 or not token or not hmac.compare_digest(token, expected):
        raise HTTPException(401, detail={"code": "SHOPIFY_SYNC_AUTH_FAILED"})
    connections = list(db.scalars(select(ShopifyConnection).where(
        ShopifyConnection.status == "active"
    ).limit(50)).all())
    products = orders = errors = 0
    for connection in connections:
        try:
            _sync_products(connection, db, max_pages=5)
            products += 1
            links = list(db.scalars(select(ShopifyOrderLink).where(
                ShopifyOrderLink.connection_id == connection.id,
                ShopifyOrderLink.shopify_order_gid.is_not(None),
            ).order_by(ShopifyOrderLink.updated_at).limit(limit)).all())
            for link in links:
                if _sync_order_status(connection, db, link.shopify_order_gid):
                    orders += 1
            connection.orders_reconciled_at = utcnow()
            db.commit()
        except HTTPException:
            errors += 1
            db.rollback()
    return {"stores_checked": len(connections), "product_syncs": products, "order_statuses_reconciled": orders, "stores_with_errors": errors}


@router.get("/integrations/shopify/readiness")
def shopify_readiness(
    actor: Annotated[commerce.Actor, Depends(commerce.require_actor)],
    db: Annotated[Session, Depends(commerce.get_db)],
):
    merchant = _approved_merchant(actor, db)
    connection = db.scalar(select(ShopifyConnection).where(ShopifyConnection.merchant_id == merchant.id))
    if connection is None:
        return {"configured": False, "ready": False, "reason": "SHOPIFY_NOT_CONNECTED"}
    required_ready = connection.status == "active" and REQUIRED_SCOPES.issubset(_required_scopes(connection.granted_scopes))
    hooks_ready = all(connection.webhook_registration.get(topic) == "registered" for topic in WEBHOOK_TOPICS)
    return {
        "configured": True, "ready": required_ready and hooks_ready,
        "connection_status": connection.status,
        "required_scopes_granted": required_ready,
        "webhooks_registered": hooks_ready,
        "products_synced": connection.products_synced_at is not None,
        "shop_currency": connection.shop_currency,
        "shopify_is_commerce_provider_only": True,
        "cal_display_authorization_required": True,
    }
