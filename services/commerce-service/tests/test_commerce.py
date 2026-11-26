import base64
import hashlib
import hmac
import json
import os
import time
import uuid

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import ec, rsa

os.environ.setdefault("COMMERCE_DATABASE_URL", "sqlite:///./test-commerce-import.db")
os.environ.setdefault("COMMERCE_AUTO_CREATE_SCHEMA", "true")

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main


MARKETPLACE_READ_TOKEN = "commerce-marketplace-read-test-token-with-32-bytes"
MARKETPLACE_READ_HEADERS = {"X-Commerce-Marketplace-Read-Token": MARKETPLACE_READ_TOKEN}


TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TEST_SESSION = sessionmaker(bind=TEST_ENGINE, autoflush=False, autocommit=False, expire_on_commit=False)
ORIGINAL_ENGINE = main.engine
ORIGINAL_SESSION = main.SessionLocal



REAL_CAL_PURCHASE_RECEIPT_REQUESTER = main._request_cal_purchase_receipts


def fake_cal_receipts(request, subject_id: str, authorizations: list[dict], *, decision: str = "SHOW"):
    issued_at = main.now()
    expires_at = issued_at + main.timedelta(seconds=60)
    request_id = str(uuid.uuid4())
    receipts = []
    for item in authorizations:
        unsigned = {
            "schema_version": "1",
            "receipt_id": str(uuid.uuid4()),
            "request_id": request_id,
            "subject_id": subject_id,
            "candidate_id": item["variant_id"],
            **item,
            "catalog_version": 1,
            "decision": decision,
            "may_display": decision == "SHOW",
            "reason_codes": [] if decision == "SHOW" else ["TEST_CAL_DENIAL"],
            "policy_version": "test-cal-policy-v1",
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        key = os.getenv("CAL_PURCHASE_RECEIPT_HMAC_SECRET", "test-cal-purchase-signing-key-more-than-32-bytes")
        canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        signature = hmac.new(key.encode(), canonical, hashlib.sha256).hexdigest()
        receipts.append({**unsigned, "signature": signature})
    return receipts


def b64(value: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).rstrip(b"=").decode()


def jwt(user_id: str, role: str = "customer", email: str | None = None, **overrides) -> str:
    secret = os.environ["COMMERCE_JWT_SECRET"]
    header = b64({"alg": "HS256", "typ": "JWT"})
    claims = {
        "sub": user_id, "role": role, "iss": os.getenv("COMMERCE_JWT_ISSUER", "cirvanna-auth"),
        "aud": os.getenv("COMMERCE_JWT_AUDIENCE", "cirvanna-commerce"), "exp": int(time.time()) + 600,
    }
    if email:
        claims["email"] = email
    claims.update(overrides)
    body = b64(claims)
    sig = base64.urlsafe_b64encode(hmac.new(secret.encode(), f"{header}.{body}".encode("ascii"), hashlib.sha256).digest()).rstrip(b"=").decode()
    return f"{header}.{body}.{sig}"


def auth(user_id: str, role: str = "customer", email: str | None = None) -> dict[str, str]:
    return {"Authorization": "Bearer " + jwt(user_id, role, email)}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("COMMERCE_JWT_SECRET", "test-only-secret-at-least-32-bytes-long")
    monkeypatch.setenv("COMMERCE_MARKETPLACE_READ_TOKEN", MARKETPLACE_READ_TOKEN)
    monkeypatch.setenv("COMMERCE_JWT_ISSUER", "cirvanna-auth")
    monkeypatch.setenv("COMMERCE_JWT_AUDIENCE", "cirvanna-commerce")
    monkeypatch.setenv("COMMERCE_ENVIRONMENT", "development")
    monkeypatch.delenv("COMMERCE_MARKET_PROVIDER_VERIFICATION_REQUIRED", raising=False)
    monkeypatch.delenv("COMMERCE_AUTH_MODE", raising=False)
    monkeypatch.delenv("COMMERCE_JWT_JWKS_URL", raising=False)
    monkeypatch.delenv("COMMERCE_JWT_ROLE_CLAIM", raising=False)
    monkeypatch.setenv("COMMERCE_JWT_ROLE_CLAIM", "role")
    monkeypatch.setenv("COMMERCE_AUTO_CREATE_SCHEMA", "true")
    monkeypatch.delenv("CATALOG_API_URL", raising=False)
    monkeypatch.delenv("CATALOG_API_TOKEN", raising=False)
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("COMMERCE_CHECKOUT_SUCCESS_URL", raising=False)
    monkeypatch.delenv("COMMERCE_CHECKOUT_CANCEL_URL", raising=False)
    monkeypatch.delenv("COMMERCE_SHIPPING_COUNTRIES", raising=False)
    monkeypatch.delenv("COMMERCE_CRON_TOKEN", raising=False)
    monkeypatch.delenv("DECISION_GATEWAY_URL", raising=False)
    monkeypatch.delenv("DECISION_GATEWAY_TOKEN", raising=False)
    monkeypatch.setenv("CAL_PURCHASE_RECEIPT_HMAC_SECRET", "test-cal-purchase-signing-key-more-than-32-bytes")
    monkeypatch.setattr(main, "_request_cal_purchase_receipts", fake_cal_receipts)
    main.engine = TEST_ENGINE
    main.SessionLocal = TEST_SESSION
    with TEST_ENGINE.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    main.Base.metadata.drop_all(bind=TEST_ENGINE)
    main.Base.metadata.create_all(bind=TEST_ENGINE)
    with TestClient(main.app) as test_client:
        yield test_client
    main.Base.metadata.drop_all(bind=TEST_ENGINE)
    main.engine = ORIGINAL_ENGINE
    main.SessionLocal = ORIGINAL_SESSION


def seed_offer(stock: int = 8, price_minor: int = 250, image_urls: list[str] | None = None, owner_user_id: str = "merchant-1"):
    db = TEST_SESSION()
    merchant = main.Merchant(
        id=str(uuid.uuid4()), owner_user_id=owner_user_id, display_name="Verified Studio",
        legal_name="Verified Studio Ltd", country_code="KE", contact_email="seller@example.test",
        verification_reference="verified-by-admin-123", state="approved", commission_bps=300,
    )
    listing = main.Listing(id=str(uuid.uuid4()), merchant_id=merchant.id,
        catalog_product_id=str(uuid.uuid4()), product_name="Linen Shirt", category="Fashion",
        image_urls=image_urls or [], state="active")
    variant = main.Variant(id=str(uuid.uuid4()), listing_id=listing.id, sku="LINEN-S",
        options={"size": "S", "color": "blue"}, price_minor=price_minor, currency="KES",
        on_hand=stock, reserved_qty=0, state="active", version=1)
    db.add_all([merchant, listing, variant])
    db.commit()
    result = {"merchant_id": merchant.id, "listing_id": listing.id, "variant_id": variant.id,
        "catalog_product_id": listing.catalog_product_id}
    db.close()
    return result


def row(model, ident):
    db = TEST_SESSION()
    result = db.get(model, ident)
    if result is not None:
        db.expunge(result)
    db.close()
    return result


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self.data


def sign_stripe_event(raw: bytes, secret: str) -> str:
    timestamp = int(time.time())
    signed = str(timestamp).encode() + b"." + raw
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def configure_stripe(monkeypatch, *, session_id="cs_test_checkout_1"):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_unit_testing_only")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_unit_only_secret")
    monkeypatch.setenv("COMMERCE_CHECKOUT_SUCCESS_URL", "https://shop.example.test/success")
    monkeypatch.setenv("COMMERCE_CHECKOUT_CANCEL_URL", "https://shop.example.test/cancel")
    monkeypatch.setenv("COMMERCE_SHIPPING_COUNTRIES", "KE,US")

    def fake_post(url, **kwargs):
        assert url == "https://api.stripe.com/v1/checkout/sessions"
        assert kwargs["headers"]["Idempotency-Key"].startswith("cirvanna-order-")
        return FakeResponse({"id": session_id, "url": "https://checkout.stripe.test/" + session_id, "status": "open"})

    monkeypatch.setattr(main.httpx, "post", fake_post)


def test_health_capabilities_and_readiness_fail_closed(client):
    assert client.get("/health").status_code == 200
    capabilities = client.get("/capabilities").json()
    assert capabilities["persistent_carts"] is True
    assert capabilities["verified_payment_webhooks"] is False
    assert capabilities["virtual_twin_generation"] is False
    assert capabilities["marketplace_offer_read_requires_service_auth"] is True
    assert capabilities["marketplace_offer_read_service_auth_configured"] is True
    assert client.get("/ready").status_code == 503


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("get", "/marketplace/offers", {}),
        ("post", "/marketplace/compare", {"json": {
            "variant_ids": [str(uuid.uuid4())],
            "destination_country_code": "KE",
            "destination_key": "Nakuru/Subukia",
            "fulfillment_mode": "courier_delivery",
            "display_currency": "KES",
            "payment_method": "card",
        }}),
    ],
)
def test_raw_marketplace_read_routes_require_dedicated_gateway_token(client, monkeypatch, method, path, kwargs):
    monkeypatch.delenv("COMMERCE_MARKETPLACE_READ_TOKEN")
    missing = getattr(client, method)(path, **kwargs)
    assert missing.status_code == 503
    assert missing.json()["detail"]["code"] == "COMMERCE_MARKETPLACE_READ_AUTH_NOT_CONFIGURED"

    monkeypatch.setenv("COMMERCE_MARKETPLACE_READ_TOKEN", MARKETPLACE_READ_TOKEN)
    invalid = getattr(client, method)(
        path,
        headers={"X-Commerce-Marketplace-Read-Token": "incorrect-marketplace-read-token"},
        **kwargs,
    )
    assert invalid.status_code == 401
    assert invalid.json()["detail"]["code"] == "COMMERCE_MARKETPLACE_READ_AUTH_FAILED"


def test_compare_offers_rejects_tax_quote_from_another_destination_zone(client, monkeypatch):
    a, b = _market_compare_seed(client, monkeypatch)
    _make_offer_currency_kes(b)
    db = TEST_SESSION()
    tax = db.query(main.OfferTaxQuote).filter_by(variant_id=b["variant_id"]).one()
    tax.destination_key = "Nakuru/Other"
    db.commit()
    db.close()
    response = client.post("/marketplace/compare", headers=MARKETPLACE_READ_HEADERS, json={
        "variant_ids": [a["variant_id"], b["variant_id"]],
        "destination_country_code": "KE", "destination_key": "Nakuru/Subukia",
        "fulfillment_mode": "courier_delivery", "display_currency": "KES",
        "payment_method": "card",
    })
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["reason_code"] == "TAX_QUOTE_MISSING_OR_STALE"


def test_compare_offers_requires_same_catalog_product_identity(client, monkeypatch):
    a, b = _market_compare_seed(client, monkeypatch)
    _make_offer_currency_kes(b)
    db = TEST_SESSION()
    variant = db.get(main.Variant, b["variant_id"])
    listing = db.get(main.Listing, variant.listing_id)
    listing.catalog_product_id = str(uuid.uuid4())
    db.commit()
    db.close()
    response = client.post("/marketplace/compare", headers=MARKETPLACE_READ_HEADERS, json={
        "variant_ids": [a["variant_id"], b["variant_id"]],
        "destination_country_code": "KE", "destination_key": "Nakuru/Subukia",
        "fulfillment_mode": "courier_delivery", "display_currency": "KES",
        "payment_method": "card",
    })
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["reason_code"] == "CANONICAL_PRODUCT_MISMATCH"


def test_tax_quote_requires_explicit_destination_zone(client, monkeypatch):
    offer = seed_offer()
    token = "market-context-test-token-with-more-than-32-bytes"
    monkeypatch.setenv("COMMERCE_MARKET_CONTEXT_TOKEN", token)
    now = main.now()
    response = client.post(
        f"/internal/market-context/variants/{offer['variant_id']}/tax-quotes",
        headers={"X-Commerce-Market-Context-Token": token},
        json={
            "provider": "test-tax", "provider_quote_id": "tax-zone-quote-0001",
            "destination_country_code": "KE", "jurisdiction": "KE-Nakuru",
            "tax_category": "apparel", "basis": "exclusive",
            "amount_minor": 120, "currency": "KES", "status": "confirmed",
            "authoritative": True, "destination_key": "Nakuru/Subukia",
            "observed_at": now.isoformat(),
            "expires_at": (now + main.timedelta(minutes=30)).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["destination_key"] == "Nakuru/Subukia"


def test_multi_market_checkout_learning_and_cal_purchase_schema_revision_0011_is_registered():
    from app.main import CommerceOrder, OrderCharge, OrderItem, OfferTaxQuote, CALPurchaseAudit
    assert "fulfillment_total_minor" in CommerceOrder.__table__.columns
    assert "total_minor" in CommerceOrder.__table__.columns
    assert "tal_consent_receipt_id" in CommerceOrder.__table__.columns
    assert "destination_key" in OfferTaxQuote.__table__.columns
    assert "source_unit_price_minor" in OrderItem.__table__.columns
    assert OrderCharge.__tablename__ == "commerce_order_charges"
    assert CALPurchaseAudit.__tablename__ == "commerce_cal_purchase_audits"
    assert "offer_snapshot_sha256" in CALPurchaseAudit.__table__.columns


def test_readiness_requires_current_migration_before_production_ready(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_AUTO_CREATE_SCHEMA", "false")
    monkeypatch.setenv("CATALOG_API_URL", "https://catalog.example.test")
    monkeypatch.setenv("CATALOG_API_TOKEN", "catalog-test-token")
    monkeypatch.setenv("DECISION_GATEWAY_URL", "https://decision.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_TOKEN", "decision-gateway-test-token-more-than-32-bytes")
    monkeypatch.setenv("CAL_PURCHASE_RECEIPT_HMAC_SECRET", "test-cal-purchase-signing-key-more-than-32-bytes")
    monkeypatch.setattr(main, "_cal_gateway_probe", lambda base, token: True)
    configure_stripe(monkeypatch)

    pending = client.get("/ready")
    assert pending.status_code == 503
    pending_detail = pending.json()["detail"]
    assert pending_detail["database_connected"] is True
    assert pending_detail["schema_present"] is True
    assert pending_detail["migrations_required"] is True
    assert pending_detail["migrations_applied"] is False
    assert pending_detail["ready"] is False

    with TEST_ENGINE.begin() as connection:
        connection.execute(text(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
        ))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": "20261121_0016"},
        )

    ready = client.get("/ready")
    assert ready.status_code == 200
    payload = ready.json()
    assert payload["database_connected"] is True
    assert payload["schema_present"] is True
    assert payload["authentication_configured"] is True
    assert payload["catalog_configured"] is True
    assert payload["payment_configured"] is True
    assert payload["migrations_required"] is True
    assert payload["migrations_applied"] is True
    assert payload["schema_revision"] == "20261121_0016"
    assert payload["ready"] is True


def test_production_rejects_shared_secret_hs256_tokens(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_ENVIRONMENT", "production")
    monkeypatch.setenv("COMMERCE_AUTH_MODE", "hs256")
    response = client.get("/cart", headers=auth("production-user"))
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "AUTH_NOT_CONFIGURED"
    readiness = client.get("/ready")
    assert readiness.status_code == 503
    assert readiness.json()["detail"]["authentication_configured"] is False


def test_oidc_jwks_mode_verifies_rs256_issuer_audience_and_role(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_ENVIRONMENT", "production")
    monkeypatch.setenv("COMMERCE_AUTH_MODE", "oidc_jwks")
    monkeypatch.setenv("COMMERCE_JWT_JWKS_URL", "https://idp.example.test/.well-known/jwks.json")
    monkeypatch.setenv("COMMERCE_JWT_ISSUER", "https://idp.example.test/")
    monkeypatch.setenv("COMMERCE_JWT_AUDIENCE", "cirvanna-commerce")
    monkeypatch.setenv("COMMERCE_JWT_ROLE_CLAIM", "app_role")
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    class SigningKey:
        key = public_key

    class FakeJwksClient:
        def get_signing_key_from_jwt(self, token):
            return SigningKey()

    monkeypatch.setattr(main, "_jwks_client", lambda url: FakeJwksClient())
    claims = {
        "sub": "oidc-customer-1", "app_role": "customer",
        "iss": "https://idp.example.test/", "aud": "cirvanna-commerce",
        "exp": int(time.time()) + 300, "iat": int(time.time()),
    }
    token = pyjwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})
    actor = main.decode_actor(token)
    assert actor.user_id == "oidc-customer-1"
    assert actor.role == "customer"

    bad_claims = {**claims, "aud": "another-service"}
    bad_token = pyjwt.encode(bad_claims, private_key, algorithm="RS256", headers={"kid": "test-key"})
    rejected = client.get("/cart", headers={"Authorization": "Bearer " + bad_token})
    assert rejected.status_code == 401


def test_private_routes_require_a_signed_actor(client):
    assert client.get("/cart").status_code == 401
    assert client.get("/saved-products").status_code == 401
    assert client.get("/merchant/orders").status_code == 401


def test_customer_role_cannot_apply_or_use_merchant_routes(client):
    application = {"display_name": "Customer Studio", "legal_name": "Customer Studio Ltd",
        "country_code": "KE", "contact_email": "customer@example.test"}
    assert client.post("/merchants/applications", json=application, headers=auth("customer-merchant", "customer")).status_code == 201

    seed_offer()
    # A row owned by the subject is insufficient: authorization also requires a
    # merchant-role JWT from the trusted identity issuer.
    listing_response = client.post("/merchant/listings",
        json={"catalog_product_id": str(uuid.uuid4())}, headers=auth("merchant-1", "customer"))
    assert listing_response.status_code == 403
    assert listing_response.json()["detail"]["code"] == "MERCHANT_ROLE_REQUIRED"
    assert client.get("/merchant/orders", headers=auth("merchant-1", "customer")).status_code == 403


def test_jwt_invalid_signature_expiry_audience_and_role_fail_closed(client):
    token = jwt("user-1")
    header, body, _ = token.split(".")
    forged = f"{header}.{body}.not-a-signature"
    assert client.get("/cart", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    assert client.get("/cart", headers={"Authorization": "Bearer " + jwt("user-1", exp=int(time.time()) - 1)}).status_code == 401
    assert client.get("/cart", headers={"Authorization": "Bearer " + jwt("user-1", aud="other-service")}).status_code == 401
    assert client.get("/cart", headers={"Authorization": "Bearer " + jwt("user-1", role="superuser")}).status_code == 401


def test_merchant_application_is_persisted_and_approval_requires_verification(client):
    seller = auth("new-seller", "merchant")
    body = {"display_name": "Studio One", "legal_name": "Studio One Limited",
        "country_code": "ke", "contact_email": "seller@example.test"}
    created = client.post("/merchants/applications", json=body, headers=seller)
    assert created.status_code == 201
    assert created.json()["status"] == "pending"
    again = client.post("/merchants/applications", json=body, headers=seller)
    assert again.status_code == 409
    pending = created.json()["merchant_id"]
    # Applicants cannot self-assert a verification reference; extra fields are forbidden.
    self_asserted = client.post("/merchants/applications",
        json={**body, "verification_reference": "self-asserted-fake-reference"}, headers=seller)
    assert self_asserted.status_code == 422  # applicant cannot supply an admin-only verification field
    admin = auth("admin-1", "admin")
    denied = client.post(f"/admin/merchants/{pending}/decision", json={"decision": "approve"}, headers=admin)
    assert denied.status_code == 409
    approved = client.post(f"/admin/merchants/{pending}/decision",
        json={"decision": "approve", "verification_reference": "external-kyc-case-2026-001"}, headers=admin)
    assert approved.status_code == 200
    assert approved.json()["verification_reference"] == "external-kyc-case-2026-001"
    persisted = client.get("/merchants/me", headers=seller)
    assert persisted.status_code == 200
    assert persisted.json()["merchant_id"] == pending


def test_merchant_listing_withholds_catalog_images_until_attestation(client, monkeypatch):
    seed_offer()
    catalog_id = str(uuid.uuid4())
    monkeypatch.setattr(
        main.CatalogClient,
        "product",
        lambda self, incoming: {
            "product_id": incoming, "name": "Canonical Linen Shirt", "category": "Fashion",
            "status": "active",
            "image_urls": [
                "https://cdn.example.test/linen-front.jpg",
                "http://insecure.example.test/should-not-load.jpg",
                "javascript:alert(1)",
                "https://" + "user:password" + "@cdn.example.test/unsafe.jpg",
                "https://cdn.example.test/linen-back.jpg#fragment",
                "https://cdn.example.test/linen-back.jpg",
            ],
        },
    )
    response = client.post(
        "/merchant/listings", headers=auth("merchant-1", "merchant"),
        json={"catalog_product_id": catalog_id},
    )
    assert response.status_code == 201
    assert response.json()["image_urls"] == []
    listing_db = main.SessionLocal()
    stored_listing = listing_db.get(main.Listing, response.json()["listing_id"])
    assert stored_listing is not None
    assert stored_listing.image_urls == []
    listing_db.close()
    variant = client.post(
        f"/merchant/listings/{response.json()['listing_id']}/variants",
        headers=auth("merchant-1", "merchant"),
        json={
            "sku": "LINEN-SHIRT-001",
            "options": {"size": "M"},
            "price_minor": 2500,
            "currency": "KES",
            "initial_stock": 5,
        },
    )
    assert variant.status_code == 201
    offers = client.get("/marketplace/offers", headers=MARKETPLACE_READ_HEADERS)
    matching = next(item for item in offers.json()["items"] if item["listing_id"] == response.json()["listing_id"])
    assert matching["image_urls"] == []  # Public offers must not expose unverified source photographs.


def test_persistent_cart_is_account_scoped_and_rechecks_available_stock(client):
    offer = seed_offer(stock=3)
    buyer1 = auth("buyer-one")
    buyer2 = auth("buyer-two")
    add = client.post("/cart/items", json={"variant_id": offer["variant_id"], "quantity": 2}, headers=buyer1)
    assert add.status_code == 201
    assert add.json()["cart_refresh_required"] is True
    buyer1_cart = client.get("/cart", headers=buyer1)
    assert buyer1_cart.status_code == 200
    assert buyer1_cart.json()["items"][0]["available_stock"] == 3
    assert buyer1_cart.json()["items"][0]["quantity"] == 2
    assert client.get("/cart", headers=buyer2).json()["item_count"] == 0
    too_many = client.patch(f"/cart/items/{offer['variant_id']}", json={"quantity": 4}, headers=buyer1)
    assert too_many.status_code == 409
    remove = client.delete(f"/cart/items/{offer['variant_id']}", headers=buyer1)
    assert remove.status_code == 200
    assert remove.json()["removed_variant_id"] == offer["variant_id"]
    assert client.get("/cart", headers=buyer1).json()["items"] == []



def test_cart_add_blocks_and_audits_non_show_purchase_decision(client, monkeypatch):
    offer = seed_offer(stock=4)
    monkeypatch.setattr(
        main,
        "_request_cal_purchase_receipts",
        lambda request, subject, items: fake_cal_receipts(request, subject, items, decision="BLOCK"),
    )
    response = client.post(
        "/cart/items",
        json={"variant_id": offer["variant_id"], "quantity": 1},
        headers=auth("buyer-cal-block"),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "CAL_CART_ADD_DENIED"
    db = TEST_SESSION()
    assert db.query(main.CartItem).count() == 0
    audit = db.query(main.CALPurchaseAudit).one()
    assert audit.action == "cart_add" and audit.decision == "BLOCK"
    assert audit.catalog_product_id == offer["catalog_product_id"]
    assert audit.variant_id == offer["variant_id"]
    assert audit.merchant_id == offer["merchant_id"]
    assert len(audit.offer_snapshot_sha256) == 64
    db.close()


def test_checkout_cal_review_creates_no_order_or_stock_reservation(client, monkeypatch):
    offer = seed_offer(stock=5, price_minor=900)
    buyer = auth("buyer-cal-review", email="review@example.test")
    assert client.post(
        "/cart/items",
        json={"variant_id": offer["variant_id"], "quantity": 2},
        headers=buyer,
    ).status_code == 201
    configure_stripe(monkeypatch)

    def deny_checkout(request, subject, items):
        assert items[0]["action"] == "checkout"
        assert items[0]["offer_snapshot_sha256"]
        return fake_cal_receipts(request, subject, items, decision="REVIEW")

    monkeypatch.setattr(main, "_request_cal_purchase_receipts", deny_checkout)
    response = client.post(
        "/checkout",
        headers={**buyer, "Idempotency-Key": "cal-review-checkout-key-01"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "CAL_CHECKOUT_AUTHORIZATION_DENIED"
    assert row(main.Variant, offer["variant_id"]).reserved_qty == 0
    db = TEST_SESSION()
    assert db.query(main.CommerceOrder).count() == 0
    audit = db.query(main.CALPurchaseAudit).filter_by(action="checkout").one()
    assert audit.decision == "REVIEW"
    assert audit.order_id is None
    assert audit.offer_snapshot_sha256
    db.close()


def test_checkout_order_persists_exact_offer_bound_cal_receipt(client, monkeypatch):
    offer = seed_offer(stock=4, price_minor=700)
    buyer = auth("buyer-cal-audit")
    assert client.post(
        "/cart/items",
        json={"variant_id": offer["variant_id"], "quantity": 1},
        headers=buyer,
    ).status_code == 201
    configure_stripe(monkeypatch)
    response = client.post(
        "/checkout",
        headers={**buyer, "Idempotency-Key": "cal-audit-checkout-key-01"},
    )
    assert response.status_code == 201, response.text
    order_id = response.json()["order"]["order_id"]
    db = TEST_SESSION()
    audit = db.query(main.CALPurchaseAudit).filter_by(order_id=order_id, action="checkout").one()
    assert audit.decision == "SHOW"
    assert audit.catalog_product_id == offer["catalog_product_id"]
    assert audit.variant_id == offer["variant_id"]
    assert audit.listing_id == offer["listing_id"]
    assert audit.merchant_id == offer["merchant_id"]
    assert audit.quantity == 1
    assert audit.unit_price_minor == 700
    assert audit.currency == "KES"
    assert audit.policy_version == "test-cal-policy-v1"
    assert audit.receipt["signature"]
    assert audit.expires_at > audit.issued_at
    db.close()


def test_checkout_rejects_expired_cal_receipt_and_persists_denial_audit(client, monkeypatch):
    offer = seed_offer(stock=5, price_minor=900)
    buyer = auth("buyer-cal-expired")
    assert client.post(
        "/cart/items",
        json={"variant_id": offer["variant_id"], "quantity": 2},
        headers=buyer,
    ).status_code == 201
    configure_stripe(monkeypatch)

    def expired_receipt(request, subject, items):
        receipts = fake_cal_receipts(request, subject, items)
        receipts[0]["expires_at"] = (main.now() - main.timedelta(seconds=1)).isoformat()
        return receipts

    monkeypatch.setattr(main, "_request_cal_purchase_receipts", expired_receipt)
    response = client.post(
        "/checkout",
        headers={**buyer, "Idempotency-Key": "cal-expired-checkout-key-01"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "CAL_CHECKOUT_OFFER_CHANGED_REAUTHORIZE"
    assert row(main.Variant, offer["variant_id"]).reserved_qty == 0
    db = TEST_SESSION()
    assert db.query(main.CommerceOrder).count() == 0
    audit = db.query(main.CALPurchaseAudit).filter_by(action="checkout").one()
    assert audit.order_id is None
    assert audit.expires_at.replace(tzinfo=main.now().tzinfo) <= main.now()
    assert audit.reason_code == "OFFER_OR_RECEIPT_CHANGED_AFTER_CAL"
    db.close()


def test_checkout_rejects_offer_change_during_cal_roundtrip_and_keeps_audit(client, monkeypatch):
    offer = seed_offer(stock=5, price_minor=900)
    buyer = auth("buyer-cal-race")
    assert client.post(
        "/cart/items",
        json={"variant_id": offer["variant_id"], "quantity": 2},
        headers=buyer,
    ).status_code == 201
    configure_stripe(monkeypatch)

    def mutate_offer_after_cal(request, subject, items):
        receipts = fake_cal_receipts(request, subject, items)
        db = TEST_SESSION()
        variant = db.get(main.Variant, offer["variant_id"])
        variant.price_minor += 1
        variant.version += 1
        db.commit()
        db.close()
        return receipts

    monkeypatch.setattr(main, "_request_cal_purchase_receipts", mutate_offer_after_cal)
    response = client.post(
        "/checkout",
        headers={**buyer, "Idempotency-Key": "cal-offer-race-checkout-key-01"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "CAL_CHECKOUT_OFFER_CHANGED_REAUTHORIZE"
    current = row(main.Variant, offer["variant_id"])
    assert current.price_minor == 901
    assert current.reserved_qty == 0
    db = TEST_SESSION()
    assert db.query(main.CommerceOrder).count() == 0
    audit = db.query(main.CALPurchaseAudit).filter_by(action="checkout").one()
    assert audit.order_id is None
    assert audit.reason_code == "OFFER_OR_RECEIPT_CHANGED_AFTER_CAL"
    db.close()


def test_existing_idempotent_order_without_cal_audit_cannot_reopen_payment(client, monkeypatch):
    offer = seed_offer(stock=5)
    buyer = auth("buyer-cal-legacy")
    assert client.post(
        "/cart/items",
        json={"variant_id": offer["variant_id"], "quantity": 1},
        headers=buyer,
    ).status_code == 201
    configure_stripe(monkeypatch)
    first = client.post(
        "/checkout",
        headers={**buyer, "Idempotency-Key": "legacy-no-cal-audit-key-01"},
    )
    assert first.status_code == 201
    order_id = first.json()["order"]["order_id"]
    db = TEST_SESSION()
    db.query(main.CALPurchaseAudit).filter_by(order_id=order_id, action="checkout").delete()
    db.commit()
    db.close()
    retry = client.post(
        "/checkout",
        headers={**buyer, "Idempotency-Key": "legacy-no-cal-audit-key-01"},
    )
    assert retry.status_code == 409
    assert retry.json()["detail"]["code"] == "EXISTING_ORDER_CAL_AUTHORIZATION_MISSING"


def test_existing_order_retry_rejects_changed_line_quantity_or_price(client, monkeypatch):
    offer = seed_offer(stock=5, price_minor=800)
    buyer = auth("buyer-cal-line-change")
    assert client.post(
        "/cart/items",
        json={"variant_id": offer["variant_id"], "quantity": 1},
        headers=buyer,
    ).status_code == 201
    configure_stripe(monkeypatch)
    first = client.post(
        "/checkout",
        headers={**buyer, "Idempotency-Key": "cal-line-change-retry-key-01"},
    )
    assert first.status_code == 201
    order_id = first.json()["order"]["order_id"]

    db = TEST_SESSION()
    line = db.query(main.OrderItem).filter_by(order_id=order_id).one()
    line.unit_price_minor += 1
    db.commit()
    db.close()

    retry = client.post(
        "/checkout",
        headers={**buyer, "Idempotency-Key": "cal-line-change-retry-key-01"},
    )
    assert retry.status_code == 409
    assert retry.json()["detail"]["code"] == "EXISTING_ORDER_CAL_AUTHORIZATION_MISSING"




def test_real_cal_receipt_requester_rejects_modified_signed_offer(client, monkeypatch):
    from starlette.requests import Request

    monkeypatch.setenv("DECISION_GATEWAY_URL", "https://decision.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_TOKEN", "decision-gateway-token-with-more-than-32-bytes")
    signing_key = "cal-signing-key-with-more-than-thirty-two-bytes-long"
    monkeypatch.setenv("CAL_PURCHASE_RECEIPT_HMAC_SECRET", signing_key)
    item = {
        "catalog_product_id": str(uuid.uuid4()),
        "variant_id": str(uuid.uuid4()),
        "listing_id": str(uuid.uuid4()),
        "merchant_id": str(uuid.uuid4()),
        "action": "cart_add",
        "offer_snapshot_sha256": "a" * 64,
        "market_country_code": None,
        "destination_key_sha256": None,
        "fulfillment_mode": None,
        "display_currency": None,
        "quantity": 1,
        "unit_price_minor": 500,
        "currency": "KES",
    }
    request = Request({
        "type": "http",
        "method": "POST",
        "path": "/cart/items",
        "headers": [(b"authorization", b"Bearer user-access-token")],
    })

    class Response:
        status_code = 200
        def __init__(self, payload):
            self.payload = payload
        def json(self):
            return self.payload

    class FakeClient:
        def __init__(self, **kwargs):
            self.payload = None
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def post(self, url, headers, json):
            issued = main.now()
            unsigned = {
                "schema_version": "1",
                "receipt_id": str(uuid.uuid4()),
                "request_id": "gateway-request-001",
                "subject_id": json["user_id"],
                "candidate_id": item["variant_id"],
                **json["authorizations"][0],
                "catalog_version": 5,
                "decision": "SHOW",
                "may_display": True,
                "reason_codes": [],
                "policy_version": "test-policy-v1",
                "issued_at": issued.isoformat(),
                "expires_at": (issued + main.timedelta(seconds=45)).isoformat(),
            }
            canonical = json_module_dumps(unsigned)
            signature = hmac.new(signing_key.encode(), canonical, hashlib.sha256).hexdigest()
            tampered = {**unsigned, "unit_price_minor": 1}
            return Response({
                "subject_id": json["user_id"],
                "request_id": "gateway-request-001",
                "receipts": [{**tampered, "signature": signature}],
            })

    def json_module_dumps(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")

    monkeypatch.setattr(main.httpx, "Client", FakeClient)
    with pytest.raises(main.HTTPException) as exc:
        REAL_CAL_PURCHASE_RECEIPT_REQUESTER(request, "buyer-cal-signature", [item])
    assert exc.value.status_code == 502
    assert exc.value.detail["code"] == "CAL_PURCHASE_RECEIPT_BINDING_OR_SIGNATURE_INVALID"


def test_real_cal_receipt_requester_rejects_validly_signed_receipt_for_another_subject(client, monkeypatch):
    from starlette.requests import Request

    monkeypatch.setenv("DECISION_GATEWAY_URL", "https://decision.example.test")
    monkeypatch.setenv("DECISION_GATEWAY_TOKEN", "decision-gateway-token-with-more-than-32-bytes")
    signing_key = "cal-signing-key-with-more-than-thirty-two-bytes-long"
    monkeypatch.setenv("CAL_PURCHASE_RECEIPT_HMAC_SECRET", signing_key)
    item = {
        "catalog_product_id": str(uuid.uuid4()),
        "variant_id": str(uuid.uuid4()),
        "listing_id": str(uuid.uuid4()),
        "merchant_id": str(uuid.uuid4()),
        "action": "checkout",
        "offer_snapshot_sha256": "b" * 64,
        "market_country_code": None,
        "destination_key_sha256": None,
        "fulfillment_mode": None,
        "display_currency": None,
        "quantity": 1,
        "unit_price_minor": 500,
        "currency": "KES",
    }
    request = Request({
        "type": "http",
        "method": "POST",
        "path": "/checkout",
        "headers": [(b"authorization", b"Bearer user-access-token")],
    })

    class Response:
        status_code = 200
        def __init__(self, payload):
            self.payload = payload
        def json(self):
            return self.payload

    class FakeClient:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def post(self, url, headers, json):
            issued = main.now()
            unsigned = {
                "schema_version": "1",
                "receipt_id": str(uuid.uuid4()),
                "request_id": "gateway-request-subject-mismatch",
                "subject_id": "different-customer",
                "candidate_id": item["variant_id"],
                **json["authorizations"][0],
                "catalog_version": 5,
                "decision": "SHOW",
                "may_display": True,
                "reason_codes": [],
                "policy_version": "test-policy-v1",
                "issued_at": issued.isoformat(),
                "expires_at": (issued + main.timedelta(seconds=45)).isoformat(),
            }
            canonical = __import__("json").dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
            signature = hmac.new(signing_key.encode(), canonical, hashlib.sha256).hexdigest()
            return Response({
                "subject_id": json["user_id"],
                "request_id": "gateway-request-subject-mismatch",
                "receipts": [{**unsigned, "signature": signature}],
            })

    monkeypatch.setattr(main.httpx, "Client", FakeClient)
    with pytest.raises(main.HTTPException) as exc:
        REAL_CAL_PURCHASE_RECEIPT_REQUESTER(request, "expected-customer", [item])
    assert exc.value.status_code == 502
    assert exc.value.detail["code"] == "CAL_PURCHASE_RECEIPT_BINDING_OR_SIGNATURE_INVALID"


def test_real_cal_receipt_requester_fails_closed_without_trusted_gateway_config(client, monkeypatch):
    from starlette.requests import Request

    monkeypatch.delenv("DECISION_GATEWAY_URL", raising=False)
    monkeypatch.delenv("DECISION_GATEWAY_TOKEN", raising=False)
    monkeypatch.delenv("CAL_PURCHASE_RECEIPT_HMAC_SECRET", raising=False)
    request = Request({
        "type": "http",
        "method": "POST",
        "path": "/cart/items",
        "headers": [(b"authorization", b"Bearer user-access-token")],
    })
    item = {
        "catalog_product_id": str(uuid.uuid4()),
        "variant_id": str(uuid.uuid4()),
        "listing_id": str(uuid.uuid4()),
        "merchant_id": str(uuid.uuid4()),
        "action": "cart_add",
        "offer_snapshot_sha256": "b" * 64,
        "market_country_code": None,
        "destination_key_sha256": None,
        "fulfillment_mode": None,
        "display_currency": None,
        "quantity": 1,
        "unit_price_minor": 10,
        "currency": "KES",
    }
    with pytest.raises(main.HTTPException) as exc:
        REAL_CAL_PURCHASE_RECEIPT_REQUESTER(request, "buyer-cal-config", [item])
    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "CAL_PURCHASE_GATEWAY_NOT_CONFIGURED_OR_UNTRUSTED"



def test_inventory_adjustment_is_owner_scoped_and_cannot_cross_reserved_floor(client):
    offer = seed_offer(stock=3)
    merchant = auth("merchant-1", "merchant")
    wrong_owner = client.post(f"/merchant/variants/{offer['variant_id']}/inventory-adjustments",
        json={"quantity_delta": -1, "reason": "damage"}, headers=auth("other-merchant", "merchant"))
    assert wrong_owner.status_code == 403
    adjusted = client.post(f"/merchant/variants/{offer['variant_id']}/inventory-adjustments",
        json={"quantity_delta": -2, "reason": "cycle count"}, headers=merchant)
    assert adjusted.status_code == 200
    assert adjusted.json()["on_hand"] == 1
    invalid = client.post(f"/merchant/variants/{offer['variant_id']}/inventory-adjustments",
        json={"quantity_delta": -2, "reason": "bad count"}, headers=merchant)
    assert invalid.status_code == 409


def test_saved_products_are_persistent_and_validate_canonical_catalog(client, monkeypatch):
    pid = str(uuid.uuid4())
    monkeypatch.setattr(main.CatalogClient, "product", lambda self, incoming: {"product_id": incoming, "name": "Verified item", "status": "active"})
    buyer = auth("buyer-saved")
    saved = client.put(f"/saved-products/{pid}", headers=buyer)
    assert saved.status_code == 201
    assert saved.json() == {"catalog_product_id": pid, "saved": True}
    assert "product_name" not in saved.json()
    assert client.get("/saved-products", headers=buyer).json()["total"] == 1
    assert client.get("/saved-products", headers=auth("different-user")).json()["total"] == 0
    assert client.delete(f"/saved-products/{pid}", headers=buyer).status_code == 204
    assert client.get("/saved-products", headers=buyer).json()["total"] == 0


def test_catalog_client_rejects_non_tls_remote_url_before_network(client, monkeypatch):
    monkeypatch.setenv("CATALOG_API_URL", "http://localhost.attacker.example")
    monkeypatch.setenv("CATALOG_API_TOKEN", "not-a-real-token")
    called = []
    monkeypatch.setattr(main.httpx, "get", lambda *a, **kw: called.append(a))
    with pytest.raises(Exception):
        main.CatalogClient().product(str(uuid.uuid4()))
    assert called == []


def test_checkout_reserves_stock_idempotently_and_only_signed_paid_webhook_settles(client, monkeypatch):
    offer = seed_offer(stock=8, price_minor=250)
    buyer = auth("buyer-checkout", email="buyer@example.test")
    add = client.post("/cart/items", json={"variant_id": offer["variant_id"], "quantity": 2}, headers=buyer)
    assert add.status_code == 201
    configure_stripe(monkeypatch)
    first = client.post("/checkout", headers={**buyer, "Idempotency-Key": "checkout-order-key-0001"})
    assert first.status_code == 201
    assert first.json()["duplicate"] is False
    order = first.json()["order"]
    assert order["status"] == "pending_payment"
    assert order["subtotal_minor"] == 500
    assert order["commission_minor"] == 15
    v = row(main.Variant, offer["variant_id"])
    assert v.on_hand == 8 and v.reserved_qty == 2

    retry = client.post("/checkout", headers={**buyer, "Idempotency-Key": "checkout-order-key-0001"})
    assert retry.status_code == 201
    assert retry.json()["duplicate"] is True
    v = row(main.Variant, offer["variant_id"])
    assert v.reserved_qty == 2

    event = {"id": "evt_test_paid_0001", "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_test_checkout_1", "metadata": {"order_id": order["order_id"]},
            "payment_intent": "pi_test_checkout_1",
            "payment_status": "paid", "amount_total": 500, "currency": "kes"}}}
    raw = json.dumps(event, separators=(",", ":")).encode()
    sig = sign_stripe_event(raw, "whsec_test_unit_only_secret")
    paid = client.post("/webhooks/stripe", content=raw, headers={"Stripe-Signature": sig, "Content-Type": "application/json"})
    assert paid.status_code == 200
    assert paid.json()["duplicate"] is False
    v = row(main.Variant, offer["variant_id"])
    assert v.on_hand == 6 and v.reserved_qty == 0
    orders = client.get("/orders", headers=buyer).json()
    assert orders["total"] == 1 and orders["items"][0]["status"] == "paid"
    assert client.get("/cart", headers=buyer).json()["items"] == []
    # Ownership sync is driven only by a durable event emitted in the paid
    # settlement transaction; cart/save/try-on state cannot create this event.
    db = TEST_SESSION()
    outbox = db.query(main.CommerceOutboxEvent).filter_by(aggregate_id=order["order_id"]).all()
    assert len(outbox) == 1
    assert outbox[0].event_type == "commerce.order.paid"
    assert outbox[0].payload["buyer_user_id"] == "buyer-checkout"
    assert outbox[0].payload["ownership_authority"] == "verified_payment"
    assert outbox[0].payload["items"][0]["catalog_product_id"] == offer["catalog_product_id"]
    assert outbox[0].payload["items"][0]["quantity"] == 2
    db.close()
    replay = client.post("/webhooks/stripe", content=raw, headers={"Stripe-Signature": sig, "Content-Type": "application/json"})
    assert replay.status_code == 200 and replay.json()["duplicate"] is True


def test_verified_charge_refund_is_monotonic_and_does_not_change_order_or_wardrobe_ownership(client, monkeypatch):
    offer = seed_offer(stock=5, price_minor=500)
    buyer = auth("buyer-refund", email="buyer-refund@example.test")
    client.post("/cart/items", json={"variant_id": offer["variant_id"], "quantity": 1}, headers=buyer)
    configure_stripe(monkeypatch, session_id="cs_test_refund")
    checkout = client.post(
        "/checkout", headers={**buyer, "Idempotency-Key": "checkout-refund-key-0001"}
    )
    order_id = checkout.json()["order"]["order_id"]

    paid_event = {
        "id": "evt_refund_setup_paid",
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": "cs_test_refund",
            "metadata": {"order_id": order_id},
            "payment_intent": "pi_test_refund_0001",
            "payment_status": "paid",
            "amount_total": 500,
            "currency": "kes",
        }},
    }
    paid_raw = json.dumps(paid_event, separators=(",", ":")).encode()
    paid_sig = sign_stripe_event(paid_raw, "whsec_test_unit_only_secret")
    paid = client.post(
        "/webhooks/stripe", content=paid_raw,
        headers={"Stripe-Signature": paid_sig, "Content-Type": "application/json"},
    )
    assert paid.status_code == 200

    def refund_event(event_id, amount_refunded):
        return {
            "id": event_id,
            "type": "charge.refunded",
            "data": {"object": {
                "id": "ch_test_refund_0001",
                "payment_intent": "pi_test_refund_0001",
                "amount": 500,
                "amount_refunded": amount_refunded,
                "currency": "kes",
            }},
        }

    partial_raw = json.dumps(refund_event("evt_refund_partial", 200), separators=(",", ":")).encode()
    partial_sig = sign_stripe_event(partial_raw, "whsec_test_unit_only_secret")
    partial = client.post(
        "/webhooks/stripe", content=partial_raw,
        headers={"Stripe-Signature": partial_sig, "Content-Type": "application/json"},
    )
    assert partial.status_code == 200
    assert partial.json()["duplicate"] is False

    order = client.get(f"/orders/{order_id}", headers=buyer).json()
    assert order["status"] == "paid"
    assert order["payment_status"] == "partial_refund"
    assert order["refund_status"] == "partial_refund"
    assert order["amount_refunded_minor"] == 200

    db = TEST_SESSION()
    paid_events = db.query(main.CommerceOutboxEvent).filter_by(
        aggregate_id=order_id, event_type="commerce.order.paid"
    ).all()
    refund_events = db.query(main.CommerceOutboxEvent).filter_by(
        event_type="commerce.order.refund.updated"
    ).all()
    assert len(paid_events) == 1
    assert len(refund_events) == 1
    payload = refund_events[0].payload
    assert payload["order_id"] == order_id
    assert payload["buyer_user_id"] == "buyer-refund"
    assert payload["amount_refunded_minor"] == 200
    assert payload["physical_return_confirmed"] is False
    assert payload["ownership_effect"] == "financial_status_only"
    db.close()

    full_raw = json.dumps(refund_event("evt_refund_full", 500), separators=(",", ":")).encode()
    full_sig = sign_stripe_event(full_raw, "whsec_test_unit_only_secret")
    full = client.post(
        "/webhooks/stripe", content=full_raw,
        headers={"Stripe-Signature": full_sig, "Content-Type": "application/json"},
    )
    assert full.status_code == 200
    final_order = client.get(f"/orders/{order_id}", headers=buyer).json()
    assert final_order["status"] == "paid"
    assert final_order["payment_status"] == "refunded"
    assert final_order["amount_refunded_minor"] == 500

    stale_raw = json.dumps(refund_event("evt_refund_stale", 200), separators=(",", ":")).encode()
    stale_sig = sign_stripe_event(stale_raw, "whsec_test_unit_only_secret")
    stale = client.post(
        "/webhooks/stripe", content=stale_raw,
        headers={"Stripe-Signature": stale_sig, "Content-Type": "application/json"},
    )
    assert stale.status_code == 200
    after_stale = client.get(f"/orders/{order_id}", headers=buyer).json()
    assert after_stale["payment_status"] == "refunded"
    assert after_stale["amount_refunded_minor"] == 500
    replay = client.post(
        "/webhooks/stripe", content=full_raw,
        headers={"Stripe-Signature": full_sig, "Content-Type": "application/json"},
    )
    assert replay.status_code == 200 and replay.json()["duplicate"] is True


def test_refund_webhook_rejects_unknown_payment_intent_and_amount_mismatch(client, monkeypatch):
    configure_stripe(monkeypatch, session_id="cs_test_refund_unknown")
    unknown = {
        "id": "evt_refund_unknown",
        "type": "charge.refunded",
        "data": {"object": {
            "id": "ch_unknown",
            "payment_intent": "pi_missing",
            "amount": 100,
            "amount_refunded": 100,
            "currency": "kes",
        }},
    }
    raw = json.dumps(unknown, separators=(",", ":")).encode()
    signature = sign_stripe_event(raw, "whsec_test_unit_only_secret")
    response = client.post(
        "/webhooks/stripe", content=raw,
        headers={"Stripe-Signature": signature, "Content-Type": "application/json"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "REFUND_ORDER_NOT_FOUND_OR_NOT_PAID"


def test_stripe_webhook_rejects_invalid_signature_and_amount_mismatch(client, monkeypatch):
    offer = seed_offer()
    buyer = auth("buyer-bad-payment")
    client.post("/cart/items", json={"variant_id": offer["variant_id"], "quantity": 1}, headers=buyer)
    configure_stripe(monkeypatch, session_id="cs_test_amount")
    checkout = client.post("/checkout", headers={**buyer, "Idempotency-Key": "checkout-order-key-0002"})
    order_id = checkout.json()["order"]["order_id"]
    bad_raw = json.dumps({"id": "evt_bad_amount", "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_test_amount", "metadata": {"order_id": order_id},
            "payment_status": "paid", "amount_total": 99999, "currency": "kes"}}}, separators=(",", ":")).encode()
    assert client.post("/webhooks/stripe", content=bad_raw, headers={"Stripe-Signature": "t=1,v1=bad"}).status_code == 400
    good_sig = sign_stripe_event(bad_raw, "whsec_test_unit_only_secret")
    rejected = client.post("/webhooks/stripe", content=bad_raw, headers={"Stripe-Signature": good_sig, "Content-Type": "application/json"})
    assert rejected.status_code == 400
    assert row(main.Variant, offer["variant_id"]).reserved_qty == 1


def test_cron_expiry_requires_a_configured_constant_time_token(client, monkeypatch):
    assert client.post("/internal/expire-reservations").status_code == 401
    monkeypatch.setenv("COMMERCE_CRON_TOKEN", "a-long-test-only-cron-secret")
    assert client.post("/internal/expire-reservations", headers={"X-Commerce-Cron-Token": "wrong"}).status_code == 401


def test_inventory_audit_is_admin_only_and_detects_clean_database(client):
    offer = seed_offer()
    assert client.get("/admin/inventory/audit", headers=auth("customer-1")).status_code == 403
    response = client.get("/admin/inventory/audit", headers=auth("admin-1", "admin"))
    assert response.status_code == 200 and response.json()["ok"] is True

def test_current_actor_endpoint_uses_verified_token_subject(client):
    unauthenticated = client.get("/me")
    assert unauthenticated.status_code == 401
    response = client.get("/me", headers=auth("identity-subject-123", role="customer", email="buyer@example.test"))
    assert response.status_code == 200
    assert response.json() == {
        "user_id": "identity-subject-123",
        "role": "customer",
        "email": "buyer@example.test",
    }


def test_current_actor_endpoint_rejects_invalid_token(client):
    response = client.get("/me", headers={"Authorization": "Bearer definitely-not-a-jwt"})
    assert response.status_code == 401




def test_admin_merchant_queue_is_paginated_filtered_and_role_protected(client):
    first = client.post("/merchants/applications", headers=auth("queue-seller-1", "customer"),
        json={"display_name": "Queue Studio One", "legal_name": "Queue Studio One Ltd",
              "country_code": "KE", "contact_email": "one@example.test"})
    second = client.post("/merchants/applications", headers=auth("queue-seller-2", "customer"),
        json={"display_name": "Queue Studio Two", "legal_name": "Queue Studio Two Ltd",
              "country_code": "UG", "contact_email": "two@example.test"})
    assert first.status_code == second.status_code == 201

    assert client.get("/admin/merchants").status_code == 401
    assert client.get("/admin/merchants", headers=auth("customer-1", "customer")).status_code == 403
    assert client.get("/admin/merchants", headers=auth("merchant-1", "merchant")).status_code == 403

    response = client.get("/admin/merchants?state=pending&offset=0&limit=1",
                          headers=auth("admin-queue", "admin"))
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert len(payload["items"]) == 1
    assert payload["items"][0]["status"] == "pending"
    assert "owner_user_id" not in payload["items"][0]
    assert "verification_reference" not in payload["items"][0]

    second_page = client.get("/admin/merchants?state=pending&offset=1&limit=1",
                             headers=auth("admin-queue", "admin"))
    assert second_page.status_code == 200
    assert second_page.json()["total"] == 2
    assert second_page.json()["items"][0]["merchant_id"] != payload["items"][0]["merchant_id"]

    approved = client.post(
        f"/admin/merchants/{first.json()['merchant_id']}/decision",
        headers=auth("admin-queue", "admin"),
        json={"decision": "approve", "verification_reference": "external-review-2026-01"},
    )
    assert approved.status_code == 200
    pending_only = client.get("/admin/merchants?state=pending",
                              headers=auth("admin-queue", "admin"))
    assert pending_only.status_code == 200
    assert pending_only.json()["total"] == 1

def test_offer_response_exposes_observation_and_fails_comparison_without_catalog_identity(client):
    seed_offer()
    response = client.get("/marketplace/offers", headers=MARKETPLACE_READ_HEADERS)
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["canonical_variant_id"] is None
    assert item["observed_at"]
    assert item["is_fresh"] is True
    assert item["comparison_eligible"] is False
    assert response.json()["offer_max_age_seconds"] == 3600


def test_production_variant_creation_requires_catalog_identity(client, monkeypatch):
    seeded = seed_offer()
    monkeypatch.setenv("COMMERCE_REQUIRE_CANONICAL_VARIANT_ID", "true")
    response = client.post(
        f"/merchant/listings/{seeded['listing_id']}/variants",
        headers=auth("merchant-1", "merchant"),
        json={"sku": "LINEN-M", "options": {"size": "M"}, "price_minor": 250,
              "currency": "KES", "initial_stock": 5},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "CANONICAL_VARIANT_ID_REQUIRED"


def test_variant_creation_verifies_catalog_variant_product_binding(client, monkeypatch):
    seeded = seed_offer()
    monkeypatch.setenv("COMMERCE_REQUIRE_CANONICAL_VARIANT_ID", "true")
    monkeypatch.setenv("CATALOG_API_URL", "https://catalog.example.test")
    monkeypatch.setenv("CATALOG_API_TOKEN", "catalog-read-token")

    canonical_id = str(uuid.uuid4())
    monkeypatch.setattr(
        main.CatalogClient, "variant",
        lambda self, variant_id, expected_product_id: {
            "variant_id": canonical_id, "product_id": expected_product_id, "status": "active"
        },
    )
    response = client.post(
        f"/merchant/listings/{seeded['listing_id']}/variants",
        headers=auth("merchant-1", "merchant"),
        json={"sku": "LINEN-M", "options": {"size": "M"}, "price_minor": 250,
              "currency": "KES", "initial_stock": 5, "canonical_variant_id": canonical_id},
    )
    assert response.status_code == 201, response.text
    assert response.json()["canonical_variant_id"] == canonical_id
    assert response.json()["observed_at"]


def test_stale_offer_is_not_comparison_eligible(client, monkeypatch):
    seed_offer()
    monkeypatch.setenv("COMMERCE_OFFER_MAX_AGE_SECONDS", "60")
    original_now = main.now
    monkeypatch.setattr(main, "now", lambda: original_now() + main.timedelta(hours=2))
    item = client.get("/marketplace/offers", headers=MARKETPLACE_READ_HEADERS).json()["items"][0]
    assert item["is_fresh"] is False
    assert item["comparison_eligible"] is False

def test_inventory_adjustment_refreshes_server_observation_timestamp(client, monkeypatch):
    seeded = seed_offer()
    later = main.now() + main.timedelta(minutes=2)
    monkeypatch.setattr(main, "now", lambda: later)
    response = client.post(
        f"/merchant/variants/{seeded['variant_id']}/inventory-adjustments",
        headers=auth("merchant-1", "merchant"),
        json={"quantity_delta": 1, "reason": "restock"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["observed_at"]
    assert response.json()["on_hand"] == 9


def test_commerce_outbox_requires_sync_token_and_leases_events(client, monkeypatch):
    token = "commerce-sync-token-with-at-least-32-bytes"
    monkeypatch.setenv("COMMERCE_SYNC_TOKEN", token)
    db = TEST_SESSION()
    event_id = str(uuid.uuid4())
    db.add(main.CommerceOutboxEvent(
        event_id=event_id, aggregate_type="commerce_order", aggregate_id=str(uuid.uuid4()),
        event_type="commerce.order.paid", schema_version=1,
        payload={"event_id": event_id, "ownership_authority": "verified_payment"},
    ))
    db.commit()
    db.close()
    unauth = client.post("/internal/outbox/claim", json={"worker_id": "sync-worker"})
    assert unauth.status_code == 401
    headers = {"X-Commerce-Sync-Token": token}
    claimed = client.post("/internal/outbox/claim", headers=headers, json={"worker_id": "sync-worker"})
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["events"][0]["event_id"] == event_id
    assert claimed.json()["events"][0]["attempt"] == 1
    wrong_worker = client.post(f"/internal/outbox/{event_id}/ack", headers=headers, json={"worker_id": "other-worker"})
    assert wrong_worker.status_code == 409
    ack = client.post(f"/internal/outbox/{event_id}/ack", headers=headers, json={"worker_id": "sync-worker"})
    replay = client.post(f"/internal/outbox/{event_id}/ack", headers=headers, json={"worker_id": "sync-worker"})
    assert ack.status_code == 200 and ack.json()["status"] == "delivered"
    assert replay.status_code == 200 and replay.json()["status"] == "already_delivered"


def test_commerce_outbox_failure_schedules_retry_and_dead_letters_after_limit(client, monkeypatch):
    token = "commerce-sync-token-with-at-least-32-bytes"
    monkeypatch.setenv("COMMERCE_SYNC_TOKEN", token)
    db = TEST_SESSION()
    event_id = str(uuid.uuid4())
    db.add(main.CommerceOutboxEvent(
        event_id=event_id, aggregate_type="commerce_order", aggregate_id=str(uuid.uuid4()),
        event_type="commerce.order.paid", schema_version=1, attempts=7,
        payload={"event_id": event_id},
    ))
    db.commit()
    db.close()
    headers = {"X-Commerce-Sync-Token": token}
    claim = client.post("/internal/outbox/claim", headers=headers, json={"worker_id": "sync-worker"})
    assert claim.status_code == 200
    failed = client.post(f"/internal/outbox/{event_id}/fail", headers=headers,
                         json={"worker_id": "sync-worker", "error_code": "WARDROBE_UNAVAILABLE"})
    assert failed.status_code == 200
    assert failed.json()["status"] == "dead_lettered"
    row = TEST_SESSION().get(main.CommerceOutboxEvent, event_id)
    assert row.dead_letter_at is not None


def test_merchant_listing_directory_is_owner_scoped_and_includes_variant_inventory(client):
    offer = seed_offer(stock=7, price_minor=129900)
    seller = auth("merchant-1", "merchant")
    response = client.get("/merchant/listings?offset=0&limit=10", headers=seller)
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["listing_id"] == offer["listing_id"]
    assert payload["items"][0]["variants"][0]["variant_id"] == offer["variant_id"]
    assert payload["items"][0]["variants"][0]["available_stock"] == 7

    other_merchant = client.get("/merchant/listings", headers=auth("other-merchant", "merchant"))
    assert other_merchant.status_code == 403
    assert other_merchant.json()["detail"]["code"] == "MERCHANT_NOT_APPROVED"
    customer = client.get("/merchant/listings", headers=auth("buyer-1", "customer"))
    assert customer.status_code == 403
    assert customer.json()["detail"]["code"] == "MERCHANT_ROLE_REQUIRED"


def test_admin_merchant_directory_and_decision_history_are_admin_only(client):
    application = {
        "display_name": "North Star Studio",
        "legal_name": "North Star Studio Limited",
        "country_code": "KE",
        "contact_email": "ops@northstar.example",
    }
    created = client.post("/merchants/applications", json=application, headers=auth("north-star-owner", "customer"))
    assert created.status_code == 201
    merchant_id = created.json()["merchant_id"]

    denied = client.get("/admin/merchants", headers=auth("customer-1", "customer"))
    assert denied.status_code == 403
    denied_history = client.get("/admin/merchant-decisions", headers=auth("customer-1", "customer"))
    assert denied_history.status_code == 403

    admin = auth("founder-admin", "admin")
    directory = client.get("/admin/merchants?state=pending&offset=0&limit=10", headers=admin)
    assert directory.status_code == 200
    assert directory.json()["total"] == 1
    assert directory.json()["items"][0]["merchant_id"] == merchant_id
    assert "owner_user_id" not in directory.json()["items"][0]

    approved = client.post(
        f"/admin/merchants/{merchant_id}/decision",
        headers=admin,
        json={
            "decision": "approve",
            "verification_reference": "external-verification-case-2026-44",
            "commission_bps": 350,
            "note": "Business verification completed.",
        },
    )
    assert approved.status_code == 200
    suspended = client.post(
        f"/admin/merchants/{merchant_id}/decision",
        headers=admin,
        json={"decision": "suspend", "commission_bps": 350, "note": "Compliance review opened."},
    )
    assert suspended.status_code == 200
    history = client.get(f"/admin/merchant-decisions?merchant_id={merchant_id}&limit=10", headers=admin)
    assert history.status_code == 200
    records = history.json()["items"]
    assert history.json()["total"] == 2
    transitions = {(record["previous_state"], record["new_state"]) for record in records}
    assert transitions == {("pending", "approved"), ("approved", "suspended")}
    approval = next(record for record in records if record["decision"] == "approve")
    assert approval["actor_user_id"] == "founder-admin"
    assert approval["verification_reference"] == "external-verification-case-2026-44"
    assert approval["commission_bps"] == 350


def test_admin_merchant_directory_rejects_unknown_state_filter(client):
    response = client.get("/admin/merchants?state=all", headers=auth("founder-admin", "admin"))
    assert response.status_code == 422


def test_merchant_orders_do_not_disclose_other_merchants_order_totals(client, monkeypatch):
    own = seed_offer(stock=5, price_minor=1000)
    other_db = TEST_SESSION()
    other_merchant = main.Merchant(
        id=str(uuid.uuid4()), owner_user_id="merchant-2", display_name="Other Studio",
        legal_name="Other Studio Ltd", country_code="KE", contact_email="other@example.test",
        verification_reference="external-check-2", state="approved", commission_bps=500,
    )
    other_listing = main.Listing(
        id=str(uuid.uuid4()), merchant_id=other_merchant.id, catalog_product_id=str(uuid.uuid4()),
        product_name="Other Merchant Item", category="Fashion", image_urls=[], state="active",
    )
    other_variant = main.Variant(
        id=str(uuid.uuid4()), listing_id=other_listing.id, sku="OTHER-1", options={"size":"M"},
        price_minor=9000, currency="KES", on_hand=4, reserved_qty=0, state="active", version=1,
    )
    other_db.add_all([other_merchant, other_listing, other_variant])
    other_db.commit()
    other_variant_id = other_variant.id
    other_db.close()

    buyer = auth("multi-seller-buyer")
    assert client.post("/cart/items", headers=buyer, json={"variant_id": own["variant_id"], "quantity": 2}).status_code == 201
    assert client.post("/cart/items", headers=buyer, json={"variant_id": other_variant_id, "quantity": 1}).status_code == 201
    configure_stripe(monkeypatch, session_id="cs_test_multi_seller")
    checkout = client.post("/checkout", headers={**buyer, "Idempotency-Key":"multi-seller-order-key-01"})
    assert checkout.status_code == 201
    seller_view = client.get("/merchant/orders", headers=auth("merchant-1","merchant"))
    assert seller_view.status_code == 200
    order = seller_view.json()["items"][0]
    assert order["merchant_scope"] is True
    assert len(order["items"]) == 1
    assert order["items"][0]["variant_id"] == own["variant_id"]
    assert order["subtotal_minor"] == 2000
    assert order["commission_minor"] == 60


def test_multi_market_provider_evidence_models_are_registered_and_constrained():
    from app.main import (
        MerchantOperatingMarket, OfferFXQuote, OfferFulfillmentQuote,
        OfferTaxQuote, MarketPaymentCapability,
    )
    assert MerchantOperatingMarket.__tablename__ == "commerce_merchant_operating_markets"
    assert OfferFXQuote.__tablename__ == "commerce_offer_fx_quotes"
    assert OfferFulfillmentQuote.__tablename__ == "commerce_offer_fulfillment_quotes"
    assert OfferTaxQuote.__tablename__ == "commerce_offer_tax_quotes"
    assert MarketPaymentCapability.__tablename__ == "commerce_market_payment_capabilities"
    assert any(c.name == "ck_commerce_fx_rate_positive" for c in OfferFXQuote.__table__.constraints)
    assert any(c.name == "ck_commerce_fulfillment_charge_basis" for c in OfferFulfillmentQuote.__table__.constraints)
    assert any(c.name == "ck_commerce_tax_basis" for c in OfferTaxQuote.__table__.constraints)


def test_merchant_application_distinguishes_brand_home_legal_and_operating_markets(client):
    response = client.post("/merchants/applications", headers=auth("brand-owner"), json={
        "display_name": "Origin Studio",
        "legal_name": "Origin Studio Limited",
        "country_code": "KE",
        "brand_home_country_code": "IN",
        "legal_country_code": "KE",
        "operating_markets": ["KE", "UG"],
        "contact_email": "brand@example.test",
    })
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["brand_home_country_code"] == "IN"
    assert body["legal_country_code"] == "KE"
    assert body["country_code"] == "KE"
    from app.main import MerchantOperatingMarket
    db = TEST_SESSION()
    markets = list(db.query(MerchantOperatingMarket).filter_by(merchant_id=body["merchant_id"]).order_by(MerchantOperatingMarket.market_country_code))
    db.close()
    assert [(x.market_country_code, x.state) for x in markets] == [("KE", "pending"), ("UG", "pending")]


def test_legacy_merchant_country_backfill_contract_is_not_home_country(client):
    response = client.post("/merchants/applications", headers=auth("legacy-owner"), json={
        "display_name": "Legacy Shop",
        "legal_name": "Legacy Shop Ltd",
        "country_code": "KE",
        "contact_email": "legacy@example.test",
    })
    assert response.status_code == 201
    assert response.json()["legal_country_code"] == "KE"
    assert response.json()["brand_home_country_code"] is None


def test_variant_separates_source_price_from_offer_transaction_price(client):
    seeded = seed_offer()
    response = client.post(
        f"/merchant/listings/{seeded['listing_id']}/variants",
        headers=auth("merchant-1", "merchant"),
        json={
            "sku": "SOURCE-1",
            "options": {"size": "M"},
            "price_minor": 1200,
            "currency": "KES",
            "source_price_minor": 900,
            "source_currency": "USD",
            "initial_stock": 4,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["price_minor"] == 1200 and body["currency"] == "KES"
    assert body["source_price_minor"] == 900 and body["source_currency"] == "USD"


def test_market_declarations_are_pending_until_admin_activation(client):
    seeded = seed_offer()
    declared = client.post(
        "/merchant/markets",
        headers=auth("merchant-1", "merchant"),
        json={"market_country_code":"UG","display_currency":"UGX","locale":"en-UG"},
    )
    assert declared.status_code == 201, declared.text
    assert declared.json()["state"] == "pending"
    denied = client.put(
        f"/admin/merchants/{seeded['merchant_id']}/markets/UG",
        headers=auth("admin-1", "admin"),
        json={
            "state":"active","display_currency":"UGX","locale":"en-UG",
            "tax_provider":"test-tax","tax_provider_reference":"tax-market-ref",
            "tax_capability_observed_at":main.now().isoformat(),
            "tax_capability_expires_at":(main.now()+main.timedelta(hours=1)).isoformat(),
            "fulfillment_provider":"test-fulfillment","fulfillment_provider_reference":"fulfillment-market-ref",
            "fulfillment_capability_observed_at":main.now().isoformat(),
            "fulfillment_capability_expires_at":(main.now()+main.timedelta(hours=1)).isoformat(),
        },
    )
    assert denied.status_code == 409
    assert denied.json()["detail"]["code"] == "MARKET_PAYMENT_CAPABILITY_NOT_READY"


def _market_compare_seed(client, monkeypatch):
    from datetime import timedelta
    from decimal import Decimal
    merchant_a = seed_offer(price_minor=1800)
    merchant_b = seed_offer(price_minor=10, owner_user_id="merchant-2")
    assert merchant_a["merchant_id"] != merchant_b["merchant_id"]
    canonical_id = str(uuid.uuid4())
    db = TEST_SESSION()
    variant_a = db.get(main.Variant, merchant_a["variant_id"])
    variant_b = db.get(main.Variant, merchant_b["variant_id"])
    variant_a.canonical_variant_id = canonical_id
    variant_b.canonical_variant_id = canonical_id
    # Equivalent cross-merchant variants must resolve to the same canonical Catalog product.
    listing_a = db.get(main.Listing, merchant_a["listing_id"])
    listing_b = db.get(main.Listing, merchant_b["listing_id"])
    listing_b.catalog_product_id = listing_a.catalog_product_id
    variant_b.currency = "USD"
    variant_b.price_minor = 12
    variant_a.observed_at = main.now()
    variant_b.observed_at = main.now()
    variant_a.source_price_minor, variant_a.source_currency = 1500, "INR"
    for merchant, variant, currency, fulfillment_minor, tax_minor in [
        (merchant_a, variant_a, "KES", 250, 180),
        (merchant_b, variant_b, "USD", 2, 1),
    ]:
        market = main.MerchantOperatingMarket(
            id=str(uuid.uuid4()), merchant_id=merchant["merchant_id"], market_country_code="KE",
            state="active", display_currency="KES", locale="en-KE", activated_by="admin",
            activated_at=main.now(),
            tax_provider="test-tax", tax_provider_reference="tax-ref",
            tax_capability_observed_at=main.now(), tax_capability_expires_at=main.now()+timedelta(hours=1),
            fulfillment_provider="test-fulfillment", fulfillment_provider_reference="fulfillment-ref",
            fulfillment_capability_observed_at=main.now(), fulfillment_capability_expires_at=main.now()+timedelta(hours=1),
        )
        payment = main.MarketPaymentCapability(
            id=str(uuid.uuid4()), merchant_id=merchant["merchant_id"], market_country_code="KE",
            provider="stripe", state="active", transaction_currencies=([currency] if currency == "KES" else [currency, "KES"]),
            settlement_currencies=["KES"], payment_methods=["card"], provider_reference="test-ref",
            observed_at=main.now(), expires_at=main.now()+timedelta(hours=1),
        )
        fulfillment = main.OfferFulfillmentQuote(
            id=str(uuid.uuid4()), variant_id=variant.id, destination_country_code="KE",
            destination_key="Nakuru/Subukia", fulfillment_mode="courier_delivery",
            amount_minor=fulfillment_minor, currency=currency, status="confirmed",
            charge_basis="per_unit", distance_km=main.Decimal("10") if merchant is merchant_a else main.Decimal("40"),
            provider="test-courier", provider_quote_id=str(uuid.uuid4()),
            observed_at=main.now(), expires_at=main.now()+timedelta(hours=1),
            distance_precision_verified_at=main.now(),
        )
        tax = main.OfferTaxQuote(
            id=str(uuid.uuid4()), variant_id=variant.id, destination_country_code="KE",
            destination_key="Nakuru/Subukia", jurisdiction="KE-Nakuru", tax_category="apparel", basis="exclusive",
            amount_minor=tax_minor, currency=currency, status="confirmed", authoritative=True,
            provider="test-tax", provider_quote_id=str(uuid.uuid4()), rule_version="test-1",
            observed_at=main.now(), expires_at=main.now()+timedelta(hours=1),
        )
        db.add_all([market, payment, fulfillment, tax])
    db.add(main.OfferFXQuote(
        id=str(uuid.uuid4()), variant_id=variant_b.id, base_currency="USD", quote_currency="KES",
        rate=main.Decimal("130.000000000000"), provider="test-fx", provider_quote_id=str(uuid.uuid4()),
        rounding_rule="HALF_UP", spread_bps=0, observed_at=main.now(),
        expires_at=main.now()+timedelta(hours=1),
    ))
    db.commit()
    db.close()
    return merchant_a, merchant_b


def _make_offer_currency_kes(merchant):
    db = TEST_SESSION()
    variant = db.get(main.Variant, merchant["variant_id"])
    variant.currency = "KES"
    variant.price_minor = 1900
    payment = db.query(main.MarketPaymentCapability).filter_by(merchant_id=merchant["merchant_id"]).one()
    payment.transaction_currencies = ["KES"]
    fulfillment = db.query(main.OfferFulfillmentQuote).filter_by(variant_id=variant.id).one()
    fulfillment.currency = "KES"
    fulfillment.amount_minor = 200
    fulfillment.distance_km = main.Decimal("20")
    tax = db.query(main.OfferTaxQuote).filter_by(variant_id=variant.id).one()
    tax.currency = "KES"
    tax.amount_minor = 120
    db.commit()
    db.close()


def test_compare_offers_requires_complete_like_for_like_landed_cost(client, monkeypatch):
    a, b = _market_compare_seed(client, monkeypatch)
    _make_offer_currency_kes(b)
    response = client.post("/marketplace/compare", headers=MARKETPLACE_READ_HEADERS, json={
        "variant_ids":[a["variant_id"],b["variant_id"]],
        "destination_country_code":"KE",
        "destination_key":"Nakuru/Subukia",
        "fulfillment_mode":"courier_delivery",
        "display_currency":"KES",
        "payment_method":"card",
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "comparable", result
    assert result["display_currency"] == "KES"
    assert result["offers"][0]["landed_total_minor"] <= result["offers"][1]["landed_total_minor"]
    peer_offer = next(item for item in result["offers"] if item["merchant_id"] == b["merchant_id"])
    assert peer_offer["offer_currency"] == "KES"
    assert peer_offer["fx_quotes"]["item"] is None
    assert result["offers"][0]["tax"]["basis"] == "exclusive"


def test_compare_offers_rejects_canonical_variant_mismatch(client, monkeypatch):
    a, b = _market_compare_seed(client, monkeypatch)
    _make_offer_currency_kes(b)
    db = TEST_SESSION()
    db.get(main.Variant, b["variant_id"]).canonical_variant_id = str(uuid.uuid4())
    db.commit()
    db.close()
    response = client.post("/marketplace/compare", headers=MARKETPLACE_READ_HEADERS, json={
        "variant_ids":[a["variant_id"],b["variant_id"]],
        "destination_country_code":"KE","destination_key":"Nakuru/Subukia",
        "fulfillment_mode":"courier_delivery","display_currency":"KES",
    })
    assert response.json()["reason_code"] == "CANONICAL_VARIANT_MISMATCH"


def test_compare_offers_requires_authoritative_tax(client, monkeypatch):
    a, b = _market_compare_seed(client, monkeypatch)
    _make_offer_currency_kes(b)
    db = TEST_SESSION()
    tax = db.query(main.OfferTaxQuote).filter_by(variant_id=b["variant_id"]).one()
    tax.authoritative = False
    db.commit()
    db.close()
    response = client.post("/marketplace/compare", headers=MARKETPLACE_READ_HEADERS, json={
        "variant_ids":[a["variant_id"],b["variant_id"]],
        "destination_country_code":"KE","destination_key":"Nakuru/Subukia",
        "fulfillment_mode":"courier_delivery","display_currency":"KES",
    })
    assert response.json()["reason_code"] == "TAX_QUOTE_NOT_AUTHORITATIVE"


def test_quote_ingestion_requires_internal_market_context_token(client, monkeypatch):
    seeded = seed_offer()
    response = client.post(
        f"/internal/market-context/variants/{seeded['variant_id']}/fx-quotes",
        json={
            "provider":"test-fx","provider_quote_id":"quote-1","base_currency":"USD",
            "quote_currency":"KES","rate":"130.25","observed_at":main.now().isoformat(),
            "expires_at":(main.now()+main.timedelta(hours=1)).isoformat(),
        },
    )
    assert response.status_code == 401


def test_currency_precision_handles_zero_two_and_three_decimal_currencies():
    assert main._currency_minor_units("JPY") == 0
    assert main._currency_minor_units("KES") == 2
    assert main._currency_minor_units("KWD") == 3


def test_offers_return_display_currency_only_with_market_and_fresh_fx(client, monkeypatch):
    a, b = _market_compare_seed(client, monkeypatch)
    response = client.get("/marketplace/offers", headers=MARKETPLACE_READ_HEADERS, params={"market_country_code":"KE","display_currency":"KES"})
    assert response.status_code == 200
    items = {item["variant_id"]: item for item in response.json()["items"]}
    assert items[b["variant_id"]]["display_price_status"] == "localized"
    assert items[b["variant_id"]]["display_currency"] == "KES"
    assert client.get("/marketplace/offers", headers=MARKETPLACE_READ_HEADERS, params={"display_currency":"KES"}).status_code == 422


def test_market_aware_checkout_revalidates_quotes_and_charges_localized_total(client, monkeypatch):
    merchant, peer = _market_compare_seed(client, monkeypatch)
    _make_offer_currency_kes(peer)
    comparison = client.post("/marketplace/compare", headers=MARKETPLACE_READ_HEADERS, json={
        "variant_ids": [merchant["variant_id"], peer["variant_id"]],
        "destination_country_code": "KE", "destination_key": "Nakuru/Subukia",
        "fulfillment_mode": "courier_delivery", "display_currency": "KES", "payment_method": "card",
    })
    assert comparison.status_code == 200 and comparison.json()["status"] == "comparable"
    merchant_comparison = next(item for item in comparison.json()["offers"] if item["merchant_id"] == merchant["merchant_id"])
    variant_id = merchant["variant_id"]
    buyer_id = "buyer-market-checkout"
    db = TEST_SESSION()
    cart = main.Cart(id=str(uuid.uuid4()), user_id=buyer_id, version=1)
    db.add(cart)
    db.flush()
    db.add(main.CartItem(
        id=str(uuid.uuid4()), cart_id=cart.id, variant_id=variant_id, quantity=2,
    ))
    db.commit()
    db.close()

    configure_stripe(monkeypatch, session_id="cs_test_market_checkout")
    seen = {}
    def fake_post(url, **kwargs):
        seen.update(kwargs)
        return FakeResponse({
            "id": "cs_test_market_checkout",
            "url": "https://checkout.stripe.test/cs_test_market_checkout",
            "status": "open",
        })
    monkeypatch.setattr(main.httpx, "post", fake_post)

    response = client.post(
        "/checkout",
        headers={**auth(buyer_id), "Idempotency-Key": "market-checkout-0001"},
        json={
            "destination_country_code": "KE",
            "destination_key": "Nakuru/Subukia",
            "fulfillment_mode": "courier_delivery",
            "display_currency": "KES",
            "payment_method": "card",
        },
    )
    assert response.status_code == 201, response.text
    order = response.json()["order"]
    assert order["currency"] == "KES"
    assert order["subtotal_minor"] == 3600
    assert order["fulfillment_total_minor"] == 500
    assert order["tax_total_minor"] == 360
    assert order["total_minor"] == 4460
    assert order["total_minor"] == merchant_comparison["landed_total_minor"] * 2
    assert order["destination_country_code"] == "KE"
    assert len(order["charges"]) == 2
    stripe_data = seen["data"]
    assert not any(key.startswith("shipping_address_collection") for key in stripe_data)
    charged_total = sum(
        int(stripe_data[f"line_items[{index}][price_data][unit_amount]"])
        * int(stripe_data[f"line_items[{index}][quantity]"])
        for index in range(3)
    )
    assert charged_total == 4460
    line_names = {
        stripe_data[f"line_items[{index}][price_data][product_data][name]"]
        for index in range(3)
    }
    assert any("Courier Delivery" in name for name in line_names)
    assert any("Tax" in name for name in line_names)

    db = TEST_SESSION()
    persisted = db.get(main.CommerceOrder, order["order_id"])
    assert persisted is not None and persisted.total_minor == 4460
    main.settle_paid(db, persisted, 4460, "KES")
    assert persisted.state == "paid"
    db.close()

    changed_context = client.post(
        "/checkout",
        headers={**auth(buyer_id), "Idempotency-Key": "market-checkout-0001"},
        json={
            "destination_country_code": "KE",
            "destination_key": "Nakuru/Other",
            "fulfillment_mode": "courier_delivery",
            "display_currency": "KES",
            "payment_method": "card",
        },
    )
    assert changed_context.status_code == 409
    assert changed_context.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_CHECKOUT_CONTEXT"


def test_market_checkout_full_refund_uses_landed_charge_total_not_item_subtotal(client, monkeypatch):
    merchant, _peer = _market_compare_seed(client, monkeypatch)
    buyer_id = "buyer-market-refund"
    buyer = auth(buyer_id, email="buyer-market-refund@example.test")
    db = TEST_SESSION()
    cart = main.Cart(id=str(uuid.uuid4()), user_id=buyer_id, version=1)
    db.add(cart)
    db.flush()
    db.add(main.CartItem(id=str(uuid.uuid4()), cart_id=cart.id, variant_id=merchant["variant_id"], quantity=1))
    db.commit()
    db.close()

    configure_stripe(monkeypatch, session_id="cs_test_market_refund")
    monkeypatch.setattr(main.httpx, "post", lambda *args, **kwargs: FakeResponse({
        "id": "cs_test_market_refund",
        "url": "https://checkout.stripe.test/cs_test_market_refund",
        "status": "open",
    }))
    checkout = client.post(
        "/checkout",
        headers={**buyer, "Idempotency-Key": "market-refund-order-0001"},
        json={
            "destination_country_code": "KE",
            "destination_key": "Nakuru/Subukia",
            "fulfillment_mode": "courier_delivery",
            "display_currency": "KES",
            "payment_method": "card",
        },
    )
    assert checkout.status_code == 201, checkout.text
    order = checkout.json()["order"]
    assert order["subtotal_minor"] == 1800
    assert order["fulfillment_total_minor"] == 250
    assert order["tax_total_minor"] == 180
    assert order["total_minor"] == 2230
    assert order["total_minor"] > order["subtotal_minor"]

    paid_event = {
        "id": "evt_market_refund_setup_paid",
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": "cs_test_market_refund",
            "metadata": {"order_id": order["order_id"]},
            "payment_intent": "pi_test_market_refund_0001",
            "payment_status": "paid",
            "amount_total": 2230,
            "currency": "kes",
        }},
    }
    paid_raw = json.dumps(paid_event, separators=(",", ":")).encode()
    paid_sig = sign_stripe_event(paid_raw, "whsec_test_unit_only_secret")
    paid = client.post("/webhooks/stripe", content=paid_raw, headers={
        "Stripe-Signature": paid_sig, "Content-Type": "application/json",
    })
    assert paid.status_code == 200, paid.text

    refund_event = {
        "id": "evt_market_refund_full",
        "type": "charge.refunded",
        "data": {"object": {
            "id": "ch_test_market_refund_0001",
            "payment_intent": "pi_test_market_refund_0001",
            "amount": 2230,
            "amount_refunded": 2230,
            "currency": "kes",
        }},
    }
    refund_raw = json.dumps(refund_event, separators=(",", ":")).encode()
    refund_sig = sign_stripe_event(refund_raw, "whsec_test_unit_only_secret")
    refunded = client.post("/webhooks/stripe", content=refund_raw, headers={
        "Stripe-Signature": refund_sig, "Content-Type": "application/json",
    })
    assert refunded.status_code == 200, refunded.text
    final_order = client.get(f"/orders/{order['order_id']}", headers=buyer).json()
    assert final_order["status"] == "paid"
    assert final_order["refund_status"] == "refunded"
    assert final_order["amount_refunded_minor"] == 2230

    db = TEST_SESSION()
    event = db.query(main.CommerceOutboxEvent).filter_by(
        event_type="commerce.order.refund.updated",
    ).one()
    assert event.payload["order_total_minor"] == 2230
    db.close()


def test_active_market_cannot_bypass_checkout_context(client, monkeypatch):
    merchant, _ = _market_compare_seed(client, monkeypatch)
    buyer_id = "buyer-market-bypass"
    db = TEST_SESSION()
    cart = main.Cart(id=str(uuid.uuid4()), user_id=buyer_id, version=1)
    db.add(cart)
    db.flush()
    db.add(main.CartItem(id=str(uuid.uuid4()), cart_id=cart.id, variant_id=merchant["variant_id"], quantity=1))
    db.commit()
    db.close()
    configure_stripe(monkeypatch)
    response = client.post(
        "/checkout",
        headers={**auth(buyer_id), "Idempotency-Key": "market-checkout-0002"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "MARKET_CHECKOUT_CONTEXT_REQUIRED"


def test_marketplace_offers_default_to_30km_and_allow_user_radius_expansion(client, monkeypatch):
    a, b = _market_compare_seed(client, monkeypatch)
    base = "/marketplace/offers?market_country_code=KE&destination_key=Nakuru%2FSubukia&fulfillment_mode=courier_delivery"
    default_response = client.get(base, headers=MARKETPLACE_READ_HEADERS)
    assert default_response.status_code == 200, default_response.text
    default_data = default_response.json()
    assert default_data["total"] == 1
    assert default_data["items"][0]["merchant_id"] == a["merchant_id"]
    quote = default_data["items"][0]["fulfillment_quote"]
    assert float(quote["distance_km"]) == 10.0
    assert quote["display_amount_minor"] == 250

    expanded_response = client.get(base + "&radius_km=50", headers=MARKETPLACE_READ_HEADERS)
    assert expanded_response.status_code == 200, expanded_response.text
    expanded_data = expanded_response.json()
    assert expanded_data["total"] == 2
    usd_offer = next(item for item in expanded_data["items"] if item["merchant_id"] == b["merchant_id"])
    assert float(usd_offer["fulfillment_quote"]["distance_km"]) == 40.0
    assert usd_offer["fulfillment_quote"]["display_conversion_status"] == "localized"


def test_per_quote_fulfilment_is_not_multiplied_by_quantity(client, monkeypatch):
    merchant, _ = _market_compare_seed(client, monkeypatch)
    db = TEST_SESSION()
    quote = db.query(main.OfferFulfillmentQuote).filter_by(variant_id=merchant["variant_id"]).one()
    quote.charge_basis = "per_quote"
    buyer_id = "buyer-per-quote"
    cart = main.Cart(id=str(uuid.uuid4()), user_id=buyer_id, version=1)
    db.add(cart)
    db.flush()
    db.add(main.CartItem(id=str(uuid.uuid4()), cart_id=cart.id, variant_id=merchant["variant_id"], quantity=2))
    db.commit()
    db.close()
    configure_stripe(monkeypatch, session_id="cs_test_per_quote")
    monkeypatch.setattr(main.httpx, "post", lambda *args, **kwargs: FakeResponse({
        "id": "cs_test_per_quote", "url": "https://checkout.stripe.test/cs_test_per_quote", "status": "open",
    }))
    response = client.post("/checkout", headers={
        **auth(buyer_id), "Idempotency-Key": "market-per-quote-0001",
    }, json={
        "destination_country_code": "KE", "destination_key": "Nakuru/Subukia",
        "fulfillment_mode": "courier_delivery", "display_currency": "KES", "payment_method": "card",
    })
    assert response.status_code == 201, response.text
    order = response.json()["order"]
    assert order["subtotal_minor"] == 3600
    assert order["fulfillment_total_minor"] == 250
    assert order["tax_total_minor"] == 360
    assert order["total_minor"] == 4210
    fulfilment_charges = [charge for charge in order["charges"] if charge["charge_type"] == "fulfilment"]
    assert len(fulfilment_charges) == 1
    assert fulfilment_charges[0]["charge_basis"] == "per_quote"


def test_fulfillment_quote_ingestion_requires_explicit_charge_basis(client, monkeypatch):
    offer = seed_offer()
    token = "market-context-test-token-with-more-than-32-bytes"
    monkeypatch.setenv("COMMERCE_MARKET_CONTEXT_TOKEN", token)
    now = main.now()
    response = client.post(
        f"/internal/market-context/variants/{offer['variant_id']}/fulfillment-quotes",
        headers={"X-Commerce-Market-Context-Token": token},
        json={
            "provider": "verified-courier", "provider_quote_id": "courier-quote-0001",
            "destination_country_code": "KE", "destination_key": "Nakuru/Subukia",
            "fulfillment_mode": "courier_delivery", "charge_basis": "per_quote",
            "amount_minor": 250, "currency": "KES", "status": "confirmed",
            "distance_km": "10.0", "observed_at": now.isoformat(),
            "expires_at": (now + main.timedelta(minutes=30)).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["charge_basis"] == "per_quote"


def test_merchant_and_admin_can_review_operating_market_declarations(client):
    seller = auth("market-seller", "merchant")
    application = client.post("/merchants/applications", headers=seller, json={
        "display_name": "Global Studio", "legal_name": "Global Studio Ltd",
        "country_code": "KE", "brand_home_country_code": "IN",
        "legal_country_code": "KE", "operating_markets": ["KE", "IN"],
        "contact_email": "markets@example.test",
    })
    assert application.status_code == 201, application.text
    merchant_id = application.json()["merchant_id"]
    own = client.get("/merchants/me/markets", headers=seller)
    assert own.status_code == 200
    assert [item["market_country_code"] for item in own.json()["items"]] == ["IN", "KE"]
    assert all(item["state"] == "pending" for item in own.json()["items"])

    another_seller = client.get("/merchants/me/markets", headers=auth("different-seller", "merchant"))
    assert another_seller.status_code == 404

    denied = client.get(f"/admin/merchants/{merchant_id}/markets", headers=seller)
    assert denied.status_code == 403
    admin = client.get(f"/admin/merchants/{merchant_id}/markets", headers=auth("market-admin", "admin"))
    assert admin.status_code == 200
    assert admin.json()["merchant_id"] == merchant_id
    assert len(admin.json()["items"]) == 2


def test_compare_offers_localizes_different_offer_currencies_with_fresh_fx(client, monkeypatch):
    a, b = _market_compare_seed(client, monkeypatch)
    response = client.post("/marketplace/compare", headers=MARKETPLACE_READ_HEADERS, json={
        "variant_ids": [a["variant_id"], b["variant_id"]],
        "destination_country_code": "KE", "destination_key": "Nakuru/Subukia",
        "fulfillment_mode": "courier_delivery", "display_currency": "KES", "payment_method": "card", "radius_km": 50,
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "comparable", result
    assert result["display_currency"] == "KES"
    foreign_offer = next(item for item in result["offers"] if item["merchant_id"] == b["merchant_id"])
    assert foreign_offer["offer_currency"] == "USD"
    assert foreign_offer["item_display_price_minor"] == 1560
    assert foreign_offer["landed_total_minor"] == 1950
    assert foreign_offer["fx_quotes"]["item"]["provider"] == "test-fx"
    assert result["cheapest_variant_id"] == b["variant_id"]


def test_offer_display_price_fails_closed_when_fx_quote_is_stale(client, monkeypatch):
    _, b = _market_compare_seed(client, monkeypatch)
    db = TEST_SESSION()
    fx = db.query(main.OfferFXQuote).filter_by(variant_id=b["variant_id"]).one()
    fx.expires_at = main.now() - main.timedelta(minutes=1)
    db.commit()
    db.close()
    response = client.get("/marketplace/offers", headers=MARKETPLACE_READ_HEADERS, params={"market_country_code": "KE", "display_currency": "KES"})
    assert response.status_code == 200
    item = next(value for value in response.json()["items"] if value["variant_id"] == b["variant_id"])
    assert item["display_price_status"] == "conversion_unavailable"
    assert item["display_price_minor"] is None


def test_compare_offers_respects_user_selected_radius(client, monkeypatch):
    a, b = _market_compare_seed(client, monkeypatch)
    response = client.post("/marketplace/compare", headers=MARKETPLACE_READ_HEADERS, json={
        "variant_ids": [a["variant_id"], b["variant_id"]],
        "destination_country_code": "KE", "destination_key": "Nakuru/Subukia",
        "fulfillment_mode": "courier_delivery", "display_currency": "KES",
        "payment_method": "card", "radius_km": 30,
    })
    assert response.json()["status"] == "unavailable"
    assert response.json()["reason_code"] == "FULFILLMENT_QUOTE_OUTSIDE_RADIUS"



def test_checkout_learning_consent_is_optional_and_does_not_call_identity(monkeypatch):
    monkeypatch.delenv("IDENTITY_SERVICE_URL", raising=False)
    monkeypatch.delenv("IDENTITY_SERVICE_TOKEN", raising=False)
    assert main._verify_checkout_personalization_consent("buyer-1", None, None) is None


def test_checkout_learning_consent_resolves_canonical_receipt(monkeypatch):
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-service-token-at-least-32-bytes")
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return main.httpx.Response(200, json={
            "verified": True,
            "active": True,
            "subject_id": "buyer-1",
            "consent_id": "consent-bundle-001",
            "resource_id": None,
            "consent_version": "personalization-v1",
            "granted_scopes": ["personalization"],
            "receipt_ids": ["receipt-personalization-001"],
        })

    monkeypatch.setattr(main.httpx, "post", post)
    receipt = main._verify_checkout_personalization_consent(
        "buyer-1", "consent-bundle-001", "personalization-v1"
    )
    assert receipt == "receipt-personalization-001"
    assert calls[0][0] == "https://identity.example.test/internal/v1/consents/verify"
    assert calls[0][1]["json"]["subject_id"] == "buyer-1"
    assert calls[0][1]["json"]["required_scopes"] == ["personalization"]
    assert calls[0][1]["json"]["resource_id"] is None


def test_checkout_learning_consent_rejects_mismatched_subject(monkeypatch):
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-service-token-at-least-32-bytes")

    def post(url, **kwargs):
        return main.httpx.Response(200, json={
            "verified": True,
            "active": True,
            "subject_id": "some-other-user",
            "consent_id": "consent-bundle-001",
            "resource_id": None,
            "consent_version": "personalization-v1",
            "granted_scopes": ["personalization"],
            "receipt_ids": ["receipt-personalization-001"],
        })

    monkeypatch.setattr(main.httpx, "post", post)
    with pytest.raises(main.HTTPException) as exc:
        main._verify_checkout_personalization_consent("buyer-1", "consent-bundle-001", None)
    assert exc.value.status_code == 403



def test_checkout_started_outbox_contains_only_consent_bound_selection_snapshot(client, monkeypatch):
    offer = seed_offer(stock=5, price_minor=750)
    buyer = auth("buyer-checkout-learning", email="buyer-learning@example.test")
    added = client.post(
        "/cart/items",
        json={"variant_id": offer["variant_id"], "quantity": 1},
        headers=buyer,
    )
    assert added.status_code == 201
    configure_stripe(monkeypatch)
    monkeypatch.setattr(
        main,
        "_verify_checkout_personalization_consent",
        lambda subject_id, consent_id, consent_version: "tal-consent-receipt-0001",
    )
    response = client.post(
        "/checkout",
        headers={**buyer, "Idempotency-Key": "checkout-learning-key-0001"},
        json={"personalization_consent_id": "consent-bundle-0001"},
    )
    assert response.status_code == 201, response.text
    order_id = response.json()["order"]["order_id"]
    db = TEST_SESSION()
    event = db.query(main.CommerceOutboxEvent).filter_by(
        aggregate_id=order_id,
        event_type="commerce.checkout.started",
    ).one()
    assert event.payload["personalization_consent_receipt_id"] == "tal-consent-receipt-0001"
    assert event.payload["buyer_user_id"] == "buyer-checkout-learning"
    assert event.payload["items"][0]["catalog_product_id"] == offer["catalog_product_id"]
    assert event.payload["items"][0]["quantity"] == 1
    assert event.payload["payment_method_family"] == "card"
    assert "email" not in event.payload
    assert "address" not in event.payload
    assert "product_name" not in event.payload["items"][0]
    db.close()



def test_checkout_learning_consent_verifier_auth_failure_is_operational_error(monkeypatch):
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-service-token-at-least-32-bytes")

    def post(url, **kwargs):
        return main.httpx.Response(401)

    monkeypatch.setattr(main.httpx, "post", post)
    with pytest.raises(main.HTTPException) as exc:
        main._verify_checkout_personalization_consent("buyer-1", "consent-bundle-001", None)
    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "PERSONALIZATION_CONSENT_VERIFIER_AUTH_FAILED"



def test_checkout_learning_consent_rejects_version_mismatch(monkeypatch):
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "identity-service-token-at-least-32-bytes")

    def post(url, **kwargs):
        return main.httpx.Response(200, json={
            "verified": True,
            "active": True,
            "subject_id": "buyer-1",
            "consent_id": "consent-bundle-001",
            "resource_id": None,
            "consent_version": "personalization-v2",
            "granted_scopes": ["personalization"],
            "receipt_ids": ["receipt-personalization-001"],
        })

    monkeypatch.setattr(main.httpx, "post", post)
    with pytest.raises(main.HTTPException) as exc:
        main._verify_checkout_personalization_consent(
            "buyer-1", "consent-bundle-001", "personalization-v1"
        )
    assert exc.value.status_code == 403



def test_production_merchant_approval_fails_closed_without_provider_verification(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_MARKET_PROVIDER_VERIFICATION_REQUIRED", "true")
    monkeypatch.delenv("MERCHANT_VERIFICATION_ADAPTER_URL", raising=False)
    monkeypatch.delenv("MERCHANT_VERIFICATION_ADAPTER_TOKEN", raising=False)
    seller = auth("provider-gated-seller", "merchant")
    created = client.post("/merchants/applications", headers=seller, json={
        "display_name": "Provider Gated Studio",
        "legal_name": "Provider Gated Studio Limited",
        "legal_country_code": "KE",
        "operating_markets": ["KE"],
        "contact_email": "seller@example.test",
    })
    assert created.status_code == 201
    merchant_id = created.json()["merchant_id"]

    approval = client.post(
        f"/admin/merchants/{merchant_id}/decision",
        headers=auth("provider-gated-admin", "admin"),
        json={"decision": "approve", "verification_reference": "unverified-ref-001"},
    )

    assert approval.status_code == 503
    assert approval.json()["detail"]["code"] == "MERCHANT_VERIFICATION_ADAPTER_NOT_TRUSTED"
    stored = client.get("/merchants/me", headers=seller)
    assert stored.status_code == 200
    assert stored.json()["status"] == "pending"
    assert stored.json()["verification_reference"] is None


def test_production_fulfilment_quote_ingestion_fails_without_provider_attestation(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_MARKET_PROVIDER_VERIFICATION_REQUIRED", "true")
    monkeypatch.setenv("COMMERCE_MARKET_CONTEXT_TOKEN", "market-context-token-long-enough-for-tests")
    monkeypatch.delenv("FULFILLMENT_ADAPTER_URL", raising=False)
    monkeypatch.delenv("FULFILLMENT_ADAPTER_TOKEN", raising=False)
    seeded = seed_offer()
    observed = main.now()
    response = client.post(
        f"/internal/market-context/variants/{seeded['variant_id']}/fulfillment-quotes",
        headers={"X-Commerce-Market-Context-Token": "market-context-token-long-enough-for-tests"},
        json={
            "provider": "carrier-001",
            "provider_quote_id": "quote-001",
            "destination_country_code": "KE",
            "destination_key": "Nakuru/Subukia",
            "fulfillment_mode": "courier_delivery",
            "charge_basis": "per_quote",
            "amount_minor": 250,
            "currency": "KES",
            "status": "confirmed",
            "distance_km": 14.5,
            "observed_at": observed.isoformat(),
            "expires_at": (observed + main.timedelta(hours=1)).isoformat(),
        },
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "FULFILLMENT_ADAPTER_NOT_TRUSTED"


def test_production_readiness_exposes_provider_adapter_blockers(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_MARKET_PROVIDER_VERIFICATION_REQUIRED", "true")
    monkeypatch.delenv("MERCHANT_VERIFICATION_ADAPTER_URL", raising=False)
    monkeypatch.delenv("MERCHANT_VERIFICATION_ADAPTER_TOKEN", raising=False)
    for key in (
        "MERCHANT_VERIFICATION_ADAPTER_URL", "MERCHANT_VERIFICATION_ADAPTER_TOKEN",
        "FULFILLMENT_ADAPTER_URL", "FULFILLMENT_ADAPTER_TOKEN",
        "FX_ADAPTER_URL", "FX_ADAPTER_TOKEN",
        "TAX_ADAPTER_URL", "TAX_ADAPTER_TOKEN",
        "PAYMENT_CAPABILITY_ADAPTER_URL", "PAYMENT_CAPABILITY_ADAPTER_TOKEN",
    ):
        monkeypatch.delenv(key, raising=False)

    response = client.get("/ready")

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["provider_verification_required"] is True
    assert detail["merchant_verification_provider_ready"] is False
    assert detail["fulfillment_provider_ready"] is False
    assert detail["fx_provider_ready"] is False
    assert detail["tax_provider_ready"] is False
    assert detail["payment_capability_provider_ready"] is False



def test_production_fx_tax_and_payment_ingestion_fail_closed_without_provider_adapters(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_MARKET_PROVIDER_VERIFICATION_REQUIRED", "true")
    monkeypatch.setenv("COMMERCE_MARKET_CONTEXT_TOKEN", "market-context-token-long-enough-for-tests")
    for key in (
        "FX_ADAPTER_URL", "FX_ADAPTER_TOKEN",
        "TAX_ADAPTER_URL", "TAX_ADAPTER_TOKEN",
        "PAYMENT_CAPABILITY_ADAPTER_URL", "PAYMENT_CAPABILITY_ADAPTER_TOKEN",
    ):
        monkeypatch.delenv(key, raising=False)
    seeded = seed_offer()
    observed = main.now()
    market_token = {"X-Commerce-Market-Context-Token": "market-context-token-long-enough-for-tests"}

    fx = client.post(
        f"/internal/market-context/variants/{seeded['variant_id']}/fx-quotes",
        headers=market_token,
        json={
            "provider": "fx-provider",
            "provider_quote_id": "fx-001",
            "base_currency": "USD",
            "quote_currency": "KES",
            "rate": "129.25",
            "observed_at": observed.isoformat(),
            "expires_at": (observed + main.timedelta(minutes=5)).isoformat(),
        },
    )
    assert fx.status_code == 503
    assert fx.json()["detail"]["code"] == "FX_ADAPTER_NOT_TRUSTED"

    tax = client.post(
        f"/internal/market-context/variants/{seeded['variant_id']}/tax-quotes",
        headers=market_token,
        json={
            "provider": "tax-provider",
            "provider_quote_id": "tax-001",
            "destination_country_code": "KE",
            "destination_key": "Nakuru/Subukia",
            "jurisdiction": "KE-32",
            "tax_category": "apparel",
            "basis": "exclusive",
            "amount_minor": 180,
            "currency": "KES",
            "status": "confirmed",
            "authoritative": True,
            "rule_version": "tax-2026-01",
            "observed_at": observed.isoformat(),
            "expires_at": (observed + main.timedelta(hours=1)).isoformat(),
        },
    )
    assert tax.status_code == 503
    assert tax.json()["detail"]["code"] == "TAX_ADAPTER_NOT_TRUSTED"

    market = client.post(
        "/merchant/markets",
        headers=auth("merchant-1", "merchant"),
        json={"market_country_code": "KE", "display_currency": "KES", "locale": "en-KE"},
    )
    assert market.status_code == 201, market.text

    capability = client.put(
        f"/internal/market-context/merchants/{seeded['merchant_id']}/payment-capabilities",
        headers=market_token,
        json={
            "market_country_code": "KE",
            "provider": "stripe",
            "state": "active",
            "transaction_currencies": ["KES"],
            "settlement_currencies": ["KES"],
            "payment_methods": ["card"],
            "provider_reference": "acct-market-ke-01",
            "observed_at": observed.isoformat(),
            "expires_at": (observed + main.timedelta(hours=1)).isoformat(),
        },
    )
    assert capability.status_code == 503
    assert capability.json()["detail"]["code"] == "PAYMENT_CAPABILITY_ADAPTER_NOT_TRUSTED"


def test_shopify_currency_minor_unit_normalization():
    from app.shopify import _minor_units, _major_units

    assert _minor_units("123.45", "KES") == 12345
    assert _minor_units("123", "JPY") == 123
    assert _minor_units("12.345", "BHD") == 12345
    assert _major_units(12345, "KES") == "123.45"
    assert _major_units(123, "JPY") == "123"


def test_shopify_token_encryption_is_authenticated_and_round_trips(monkeypatch):
    import base64
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.shopify import _seal, _unseal

    monkeypatch.setenv(
        "COMMERCE_SHOPIFY_TOKEN_ENCRYPTION_KEY",
        base64.urlsafe_b64encode(b"0123456789abcdef0123456789abcdef").decode(),
    )
    connection = SimpleNamespace(id="connection-a", merchant_id="merchant-a", shop_domain="northwind.myshopify.com")
    other_store = SimpleNamespace(id="connection-b", merchant_id="merchant-b", shop_domain="other.myshopify.com")
    encrypted = _seal("shpat_private-token-value", connection, "access")
    assert "shpat_private-token-value" not in encrypted
    assert _unseal(encrypted, connection, "access") == "shpat_private-token-value"
    with pytest.raises(HTTPException):
        _unseal(encrypted, other_store, "access")
    with pytest.raises(HTTPException):
        _unseal(encrypted, connection, "refresh")


def test_shopify_token_encryption_fails_closed_without_a_valid_key(monkeypatch):
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.shopify import _seal

    monkeypatch.delenv("COMMERCE_SHOPIFY_TOKEN_ENCRYPTION_KEY", raising=False)
    connection = SimpleNamespace(id="connection-a", merchant_id="merchant-a", shop_domain="northwind.myshopify.com")
    with pytest.raises(HTTPException) as error:
        _seal("token", connection, "access")
    assert error.value.status_code == 503


def test_shopify_webhook_hmac_uses_base64_sha256():
    import base64
    import hashlib
    import hmac
    from app.shopify import _webhook_hmac_valid

    body = b'{"id":123,"title":"test"}'
    secret = "shopify-app-secret"
    signature = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    assert _webhook_hmac_valid(body, signature, secret) is True
    assert _webhook_hmac_valid(body + b" ", signature, secret) is False
    assert _webhook_hmac_valid(body, None, secret) is False


def test_shopify_oauth_shop_domain_validation_rejects_arbitrary_hosts():
    from fastapi import HTTPException
    from app.shopify import _shop_domain

    assert _shop_domain("northwind-store.myshopify.com") == "northwind-store.myshopify.com"
    for value in ("example.com", "northwind-store.myshopify.com.evil.test", "https://northwind-store.myshopify.com"):
        with pytest.raises(HTTPException):
            _shop_domain(value)


def test_shopify_inventory_snapshot_requires_complete_tracked_stock():
    from app.shopify import _inventory_totals

    complete = {
        "id": "gid://shopify/InventoryItem/1",
        "tracked": True,
        "inventoryLevels": {
            "pageInfo": {"hasNextPage": False},
            "nodes": [{
                "id": "gid://shopify/InventoryLevel/1",
                "isActive": True,
                "location": {"id": "gid://shopify/Location/1", "isActive": True},
                "quantities": [
                    {"name": "available", "quantity": 4},
                    {"name": "on_hand", "quantity": 6},
                ],
            }],
        },
    }
    assert _inventory_totals(complete) == (True, 4, 6, True)
    incomplete = {
        "id": "gid://shopify/InventoryItem/1",
        "tracked": True,
        "inventoryLevels": {
            "pageInfo": {"hasNextPage": True},
            "nodes": [{
                "id": "gid://shopify/InventoryLevel/1",
                "isActive": True,
                "location": {"id": "gid://shopify/Location/1", "isActive": True},
                "quantities": [
                    {"name": "available", "quantity": 4},
                    {"name": "on_hand", "quantity": 6},
                ],
            }],
        },
    }
    assert _inventory_totals(incomplete) == (True, None, None, False)
    assert _inventory_totals({"tracked": False}) == (False, None, None, False)


def test_shopify_product_delete_maps_to_canonical_product_gid():
    from app.shopify import _resource_gid

    assert _resource_gid("products/delete", {"id": 1234}) == "gid://shopify/Product/1234"
    assert _resource_gid("orders/updated", {"id": 456}) == "gid://shopify/Order/456"



def test_shopify_checkout_reservation_uses_deterministic_provider_draft(monkeypatch, client):
    from datetime import timedelta
    from app import shopify

    seeded = seed_offer(stock=4)
    db = TEST_SESSION()
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=seeded["merchant_id"],
        shop_domain="northwind.myshopify.com", shop_currency="KES",
        granted_scopes=["read_products", "read_inventory"], status="active",
        webhook_registration={}, installed_at=main.now(), updated_at=main.now(),
    )
    product = shopify.ShopifyProductSnapshot(
        id=str(uuid.uuid4()), connection_id=connection.id,
        shopify_product_gid="gid://shopify/Product/100", title="Linen Shirt",
        remote_status="ACTIVE", mapping_state="mapped", variants_complete=True, synced_at=main.now(),
    )
    variant_snapshot = shopify.ShopifyVariantSnapshot(
        id=str(uuid.uuid4()), connection_id=connection.id, product_snapshot_id=product.id,
        shopify_variant_gid="gid://shopify/ProductVariant/200",
        shopify_inventory_item_gid="gid://shopify/InventoryItem/300",
        sku="LINEN-S", title="Small", options={"Size": "S"}, price_minor=250,
        currency="KES", tracked=True, available_quantity=4, on_hand_quantity=4,
        inventory_complete=True, local_variant_id=seeded["variant_id"],
        canonical_variant_id=str(uuid.uuid4()), mapping_state="mapped", synced_at=main.now(),
    )
    order = main.CommerceOrder(
        id=str(uuid.uuid4()), order_number="CV-TEST-RESERVE", buyer_user_id="buyer-1",
        state="pending_payment", payment_state="pending", currency="KES",
        subtotal_minor=250, commission_minor=0, idempotency_key="shopify-reserve-test",
        expires_at=main.now() + timedelta(minutes=30),
    )
    item = main.OrderItem(
        id=str(uuid.uuid4()), order_id=order.id, merchant_id=seeded["merchant_id"],
        variant_id=seeded["variant_id"], catalog_product_id=seeded["catalog_product_id"],
        product_name="Linen Shirt", sku="LINEN-S", options={"size": "S"},
        quantity=1, unit_price_minor=250, line_total_minor=250,
        source_unit_price_minor=250, source_currency="KES", commission_bps=300, commission_minor=7,
    )
    db.add_all([connection, product, variant_snapshot, order, item])
    db.commit()
    calls = []
    provider_expiry = []
    recovery_mode = {"state": "normal", "find_calls": 0}

    def fake_graphql(conn, session, query, variables=None):
        calls.append((query, variables or {}))
        if "CirvannaFindInventoryReservation" in query:
            if recovery_mode["state"] == "unknown_state":
                return {"draftOrders": {"nodes": [{
                    "id": "gid://shopify/DraftOrder/900", "tags": [reservation_key],
                    "status": "OPEN", "ready": True,
                    "reserveInventoryUntil": provider_expiry[0], "order": None,
                }]}}
            if recovery_mode["state"] == "ambiguous_create":
                recovery_mode["find_calls"] += 1
                if recovery_mode["find_calls"] == 2:
                    return {"draftOrders": {"nodes": [{
                        "id": "gid://shopify/DraftOrder/900", "tags": [reservation_key],
                        "status": "OPEN", "ready": True,
                        "reserveInventoryUntil": provider_expiry[0], "order": None,
                    }]}}
            return {"draftOrders": {"nodes": []}}
        if "CirvannaReserveInventory" in query:
            if recovery_mode["state"] == "ambiguous_create":
                raise HTTPException(503, detail={"code": "SHOPIFY_API_UNAVAILABLE"})
            provider_expiry[:] = [variables["input"]["reserveInventoryUntil"]]
            return {"draftOrderCreate": {
                "draftOrder": {
                    "id": "gid://shopify/DraftOrder/900", "status": "OPEN", "ready": True,
                    "reserveInventoryUntil": variables["input"]["reserveInventoryUntil"],
                },
                "userErrors": [],
            }}
        if "CirvannaReadReservedDraft" in query:
            return {"draftOrder": {
                "id": "gid://shopify/DraftOrder/900", "tags": [reservation_key],
                "status": "OPEN", "ready": True,
                "reserveInventoryUntil": provider_expiry[0], "order": None,
            }}
        if "CirvannaCompleteReservedDraft" in query:
            return {"draftOrderComplete": {
                "draftOrder": {"id": "gid://shopify/DraftOrder/900", "status": "COMPLETED",
                    "order": {"id": "gid://shopify/Order/901", "name": "#CV901",
                        "displayFinancialStatus": "PAID", "displayFulfillmentStatus": "UNFULFILLED"}},
                "userErrors": [],
            }}
        raise AssertionError("Unexpected Shopify GraphQL operation")

    monkeypatch.setattr(shopify, "_graphql", fake_graphql)
    assert shopify.prepare_checkout_inventory_reservations(db, order) == 1
    reservation = db.scalar(select(shopify.ShopifyInventoryReservation).where(
        shopify.ShopifyInventoryReservation.commerce_order_id == order.id
    ))
    assert reservation is not None
    assert reservation.state == "reserved"
    assert reservation.draft_order_gid == "gid://shopify/DraftOrder/900"
    reservation_key = reservation.reservation_key
    create_call = next(call for call in calls if "CirvannaReserveInventory" in call[0])
    draft_input = create_call[1]["input"]
    assert draft_input["lineItems"] == [{
        "variantId": "gid://shopify/ProductVariant/200", "quantity": 1,
        "priceOverride": {"amount": "2.50", "currencyCode": "KES"},
    }]
    assert draft_input["presentmentCurrencyCode"] == "KES"
    assert draft_input["reserveInventoryUntil"].endswith("Z")
    assert main._aware_utc(reservation.expires_at).isoformat().replace("+00:00", "Z") == draft_input["reserveInventoryUntil"]
    assert reservation.reservation_key in draft_input["tags"]

    # A concurrent retry must not create a second Shopify draft while the lease
    # is held by the first worker.
    reservation.state = "creating"
    reservation.lease_owner = "other-worker"
    reservation.lease_until = main.now() + timedelta(seconds=30)
    db.commit()
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as in_progress:
        shopify.prepare_checkout_inventory_reservations(db, order)
    assert in_progress.value.detail["code"] == "SHOPIFY_RESERVATION_IN_PROGRESS"
    reservation.state = "reserved"
    reservation.lease_owner = None
    reservation.lease_until = None
    db.commit()
    before_retry = len(calls)
    assert shopify.prepare_checkout_inventory_reservations(db, order) == 1
    retry_calls = calls[before_retry:]
    assert len(retry_calls) == 1
    assert "CirvannaReadReservedDraft" in retry_calls[0][0]
    assert not any("CirvannaReserveInventory" in call[0] for call in retry_calls)

    # A durable UNKNOWN state must reconcile by stable tag and revalidate the
    # full provider hold before adopting the draft; an ID alone is insufficient.
    reservation.state = "unknown"
    reservation.draft_order_gid = None
    db.commit()
    recovery_mode["state"] = "unknown_state"
    before_reconcile = len(calls)
    assert shopify.prepare_checkout_inventory_reservations(db, order) == 1
    db.refresh(reservation)
    assert reservation.state == "reserved"
    assert reservation.draft_order_gid == "gid://shopify/DraftOrder/900"
    assert len([call for call in calls[before_reconcile:] if "CirvannaReserveInventory" in call[0]]) == 0

    # A timeout/ambiguous create result follows the same verification path.
    # The second stable-tag lookup finds the provider-created draft, but the
    # original create mutation is never blindly retried.
    reservation.state = "creating"
    reservation.draft_order_gid = None
    db.commit()
    recovery_mode["state"] = "ambiguous_create"
    recovery_mode["find_calls"] = 0
    before_ambiguous = len(calls)
    recovered_gid = shopify._create_inventory_draft(connection, db, reservation, [item])
    db.refresh(reservation)
    assert recovered_gid == "gid://shopify/DraftOrder/900"
    assert reservation.state == "reserved"
    assert reservation.draft_order_gid == recovered_gid
    assert len([call for call in calls[before_ambiguous:] if "CirvannaReserveInventory" in call[0]]) == 1
    recovery_mode["state"] = "normal"

    # A provider-side hold that has expired or changed since checkout creation
    # must not be completed after payment. The completion path re-reads and
    # validates the exact provider deadline before consuming the draft.
    from fastapi import HTTPException
    valid_expiry = provider_expiry[0]
    provider_expiry[0] = (main.now() - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    with pytest.raises(HTTPException) as expired_provider_hold:
        shopify._complete_shopify_inventory_reservation(connection, db, reservation)
    assert expired_provider_hold.value.detail["code"] == "SHOPIFY_RESERVED_DRAFT_NOT_COMPLETABLE"
    provider_expiry[0] = valid_expiry

    completed = shopify._complete_shopify_inventory_reservation(connection, db, reservation)
    assert completed["id"] == "gid://shopify/Order/901"
    db.refresh(reservation)
    assert reservation.state == "completed"
    assert not any("orderCreate(" in query for query, _ in calls)
    db.close()


def test_shopify_provider_reservation_expiry_readback_is_exact_and_future():
    from datetime import timedelta
    from app.shopify import _reservation_expiry_matches

    expected = (main.now() + timedelta(minutes=10)).replace(microsecond=0)
    exact = expected.isoformat().replace("+00:00", "Z")
    later = (expected + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    earlier = (expected - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")

    assert _reservation_expiry_matches(exact, expected) is True
    assert _reservation_expiry_matches(None, expected) is False
    assert _reservation_expiry_matches("", expected) is False
    assert _reservation_expiry_matches("not-a-timestamp", expected) is False
    assert _reservation_expiry_matches(expected.replace(tzinfo=None).isoformat(), expected) is False
    assert _reservation_expiry_matches(later, expected) is False
    assert _reservation_expiry_matches(earlier, expected) is False
    assert _reservation_expiry_matches((main.now() - timedelta(seconds=1)).isoformat(), expected) is False


def test_shopify_failure_does_not_release_inventory_while_existing_stripe_session_is_unconfirmed(monkeypatch):
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app import shopify

    order = SimpleNamespace(id="order-active-session", state="pending_payment", payment_session_id="cs_test_active")
    reservation = SimpleNamespace(state="failed", connection_id="connection-1", last_error=None)
    class FakeDB:
        commits = 0
        def scalar(self, _statement):
            return order
        def commit(self):
            self.commits += 1
    db = FakeDB()
    class FakeStripe:
        def expire_session(self, session_id):
            assert session_id == "cs_test_active"
            return False
    monkeypatch.setattr(main, "StripeGateway", FakeStripe)
    monkeypatch.setattr(shopify, "release_one_shopify_reservation", lambda *_: pytest.fail("provider hold released while Stripe session may still be payable"))
    monkeypatch.setattr(main, "release_reservations", lambda *_: pytest.fail("local stock released while Stripe session may still be payable"))

    with pytest.raises(HTTPException) as rejected:
        shopify._compensate_failed_checkout_reservations(db, order, [reservation])
    assert rejected.value.status_code == 503
    assert rejected.value.detail["code"] == "SHOPIFY_RESERVATION_PAYMENT_SESSION_EXPIRY_UNCONFIRMED"
    assert order.state == "pending_payment"
    assert reservation.state == "failed"
    assert reservation.last_error == "SHOPIFY_RESERVATION_PAYMENT_SESSION_EXPIRY_UNCONFIRMED"
    assert db.commits == 1


def test_shopify_failure_preserves_reservations_when_stripe_expiry_raises(monkeypatch):
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app import shopify

    order = SimpleNamespace(id="order-expiry-exception", state="pending_payment", payment_session_id="cs_test_exception")
    reservation = SimpleNamespace(state="unknown", connection_id="connection-1", last_error=None)
    class FakeDB:
        commits = 0
        def scalar(self, _statement):
            return order
        def commit(self):
            self.commits += 1
    db = FakeDB()
    class FakeStripe:
        def expire_session(self, _session_id):
            raise RuntimeError("Stripe API timeout")
    monkeypatch.setattr(main, "StripeGateway", FakeStripe)
    monkeypatch.setattr(shopify, "release_one_shopify_reservation", lambda *_: pytest.fail("provider hold released after ambiguous Stripe expiry"))
    monkeypatch.setattr(main, "release_reservations", lambda *_: pytest.fail("local stock released after ambiguous Stripe expiry"))

    with pytest.raises(HTTPException) as rejected:
        shopify._compensate_failed_checkout_reservations(db, order, [reservation])
    assert rejected.value.status_code == 503
    assert rejected.value.detail["code"] == "SHOPIFY_RESERVATION_PAYMENT_SESSION_EXPIRY_UNCONFIRMED"
    assert order.state == "pending_payment"
    assert reservation.state == "unknown"
    assert reservation.last_error == "SHOPIFY_RESERVATION_PAYMENT_SESSION_EXPIRY_UNCONFIRMED"
    assert db.commits == 1


def test_shopify_failure_expires_existing_stripe_session_before_releasing_reservations(monkeypatch):
    from types import SimpleNamespace
    from app import shopify

    order = SimpleNamespace(id="order-expire-session", state="pending_payment", payment_session_id="cs_test_expire")
    reservation = SimpleNamespace(state="failed", connection_id="connection-1", last_error=None)
    connection = SimpleNamespace(id="connection-1")
    calls = []
    class FakeDB:
        def scalar(self, _statement):
            return order
        def get(self, model, _identifier):
            return connection if model is shopify.ShopifyConnection else order
        def commit(self):
            calls.append("commit")
    db = FakeDB()
    class FakeStripe:
        def expire_session(self, session_id):
            calls.append(("expire", session_id))
            return True
    def release_provider(_connection, _db, row):
        calls.append("release_provider")
        row.state = "released"
        return True
    def release_local(_db, current, final_state):
        calls.append("release_local")
        current.state = final_state
    monkeypatch.setattr(main, "StripeGateway", FakeStripe)
    monkeypatch.setattr(shopify, "release_one_shopify_reservation", release_provider)
    monkeypatch.setattr(main, "release_reservations", release_local)

    shopify._compensate_failed_checkout_reservations(db, order, [reservation])
    assert calls.index(("expire", "cs_test_expire")) < calls.index("release_provider") < calls.index("release_local")
    assert reservation.state == "released"
    assert order.state == "checkout_failed"


def test_shopify_failure_after_payment_preserves_provider_draft_for_compensation_worker(monkeypatch):
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app import shopify

    order = SimpleNamespace(id="order-already-paid", state="paid", payment_session_id="cs_test_paid")
    reservation = SimpleNamespace(state="reserved", connection_id="connection-1", last_error=None)
    class FakeDB:
        commits = 0
        def scalar(self, _statement):
            return order
        def commit(self):
            self.commits += 1
    db = FakeDB()
    monkeypatch.setattr(main, "StripeGateway", lambda: pytest.fail("paid order must not expire its completed payment session"))
    monkeypatch.setattr(shopify, "release_one_shopify_reservation", lambda *_: pytest.fail("paid order draft must be preserved for completion/compensation"))
    monkeypatch.setattr(main, "release_reservations", lambda *_: pytest.fail("paid stock reservation must not be released"))

    with pytest.raises(HTTPException) as rejected:
        shopify._compensate_failed_checkout_reservations(db, order, [reservation])
    assert rejected.value.status_code == 503
    assert rejected.value.detail["code"] == "SHOPIFY_RESERVATION_POST_PAYMENT_RECONCILIATION_REQUIRED"
    assert order.state == "paid"
    assert reservation.state == "reserved"
    assert reservation.last_error == "SHOPIFY_RESERVATION_FAILURE_AFTER_PAYMENT"
    assert db.commits == 1


def test_shopify_existing_reserved_draft_readback_requires_exact_id_and_reservation_tag(monkeypatch):
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app import shopify

    reservation = SimpleNamespace(
        draft_order_gid="gid://shopify/DraftOrder/expected",
        reservation_key="cirvanna-reserve-expected",
        state="reserved",
        last_error=None,
    )
    connection = SimpleNamespace(id="connection-1")
    class CommitCounter:
        commits = 0
        def commit(self):
            self.commits += 1

    db = CommitCounter()
    monkeypatch.setattr(shopify, "_graphql", lambda *_args, **_kwargs: {
        "draftOrder": {
            "id": "gid://shopify/DraftOrder/other",
            "tags": ["cirvanna-reserve-other"],
            "status": "OPEN", "ready": True,
            "reserveInventoryUntil": (main.now() + __import__("datetime").timedelta(minutes=10)).isoformat().replace("+00:00", "Z"),
            "order": None,
        }
    })
    with pytest.raises(HTTPException) as rejected:
        shopify._read_verified_reservation_draft(connection, db, reservation)
    assert rejected.value.status_code == 409
    assert rejected.value.detail["code"] == "SHOPIFY_RESERVATION_READBACK_MISMATCH"
    assert reservation.state == "failed"
    assert reservation.last_error == "SHOPIFY_RESERVATION_READBACK_MISMATCH"
    assert db.commits == 1


def test_shopify_recovered_reservation_draft_is_adopted_only_after_exact_hold_verification():
    from datetime import timedelta
    from types import SimpleNamespace
    from app import shopify

    expected = main._aware_utc(main.now()).replace(microsecond=0) + timedelta(minutes=10)
    expiry = expected.isoformat().replace("+00:00", "Z")
    reservation = SimpleNamespace(
        expires_at=expected,
        draft_order_gid=None,
        state="unknown",
        lease_owner="stale-worker",
        lease_until=main.now(),
        last_error="prior-timeout",
    )

    class CommitCounter:
        commits = 0
        def commit(self):
            self.commits += 1

    db = CommitCounter()
    draft = {
        "id": "gid://shopify/DraftOrder/recovered-900",
        "status": "OPEN",
        "ready": True,
        "reserveInventoryUntil": expiry,
        "order": None,
    }
    adopted = shopify._adopt_verified_reservation_draft(db, reservation, draft)
    assert adopted == draft["id"]
    assert reservation.draft_order_gid == draft["id"]
    assert reservation.state == "reserved"
    assert reservation.lease_owner is None and reservation.lease_until is None
    assert reservation.last_error is None
    assert db.commits == 1


@pytest.mark.parametrize("mutation", ["closed", "not_ready", "missing_expiry", "expired_expiry", "different_expiry"])
def test_shopify_recovered_reservation_draft_fails_closed_on_invalid_hold(mutation):
    from datetime import timedelta
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app import shopify

    expected = main._aware_utc(main.now()).replace(microsecond=0) + timedelta(minutes=10)
    expiry = expected.isoformat().replace("+00:00", "Z")
    draft = {
        "id": "gid://shopify/DraftOrder/recovered-invalid",
        "status": "OPEN",
        "ready": True,
        "reserveInventoryUntil": expiry,
        "order": None,
    }
    if mutation == "closed":
        draft["status"] = "CLOSED"
    elif mutation == "not_ready":
        draft["ready"] = False
    elif mutation == "missing_expiry":
        draft["reserveInventoryUntil"] = None
    elif mutation == "expired_expiry":
        draft["reserveInventoryUntil"] = (main.now() - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    elif mutation == "different_expiry":
        draft["reserveInventoryUntil"] = (expected + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")

    reservation = SimpleNamespace(
        expires_at=expected,
        draft_order_gid=None,
        state="unknown",
        lease_owner="stale-worker",
        lease_until=main.now(),
        last_error=None,
    )

    class CommitCounter:
        commits = 0
        def commit(self):
            self.commits += 1

    db = CommitCounter()
    with pytest.raises(HTTPException) as rejected:
        shopify._adopt_verified_reservation_draft(db, reservation, draft)
    assert rejected.value.status_code == 409
    assert rejected.value.detail["code"] == "SHOPIFY_RESERVATION_READBACK_MISMATCH"
    assert reservation.draft_order_gid == draft["id"]
    assert reservation.state == "failed"
    assert reservation.last_error == "SHOPIFY_RESERVATION_READBACK_MISMATCH"
    assert db.commits == 1


def test_shopify_reservation_key_is_stable_and_merchant_scoped():
    from app.shopify import _reservation_key

    first = _reservation_key("order-1", "merchant-1")
    assert first == _reservation_key("order-1", "merchant-1")
    assert first != _reservation_key("order-1", "merchant-2")
    assert first.startswith("cirvanna-reserve-")


@pytest.mark.parametrize("partial_draft", [False, True])
def test_shopify_reservation_rejection_releases_local_stock_before_payment(monkeypatch, client, partial_draft):
    from datetime import timedelta
    from app import shopify

    seeded = seed_offer(stock=4)
    db = TEST_SESSION()
    variant = db.get(main.Variant, seeded["variant_id"])
    variant.reserved_qty = 1
    order = main.CommerceOrder(
        id=str(uuid.uuid4()), order_number="CV-TEST-RESERVE-FAIL", buyer_user_id="buyer-2",
        state="pending_payment", payment_state="pending", currency="KES",
        subtotal_minor=250, commission_minor=0, idempotency_key="shopify-reserve-fail",
        expires_at=main.now() + timedelta(minutes=30),
    )
    item = main.OrderItem(
        id=str(uuid.uuid4()), order_id=order.id, merchant_id=seeded["merchant_id"],
        variant_id=seeded["variant_id"], catalog_product_id=seeded["catalog_product_id"],
        product_name="Linen Shirt", sku="LINEN-S", options={"size": "S"},
        quantity=1, unit_price_minor=250, line_total_minor=250,
        source_unit_price_minor=250, source_currency="KES", commission_bps=300, commission_minor=7,
    )
    db.add_all([order, item, main.StockReservation(
        id=str(uuid.uuid4()), order_id=order.id, variant_id=variant.id,
        quantity=1, state="reserved", expires_at=order.expires_at,
    )])
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=seeded["merchant_id"],
        shop_domain="northwind.myshopify.com", shop_currency="KES",
        granted_scopes=["read_products", "read_inventory"], status="active",
        webhook_registration={}, installed_at=main.now(), updated_at=main.now(),
    )
    product = shopify.ShopifyProductSnapshot(
        id=str(uuid.uuid4()), connection_id=connection.id,
        shopify_product_gid="gid://shopify/Product/101", title="Linen Shirt",
        remote_status="ACTIVE", mapping_state="mapped", variants_complete=True, synced_at=main.now(),
    )
    snapshot = shopify.ShopifyVariantSnapshot(
        id=str(uuid.uuid4()), connection_id=connection.id, product_snapshot_id=product.id,
        shopify_variant_gid="gid://shopify/ProductVariant/201", sku="LINEN-S",
        title="Small", options={"Size": "S"}, price_minor=250, currency="KES",
        tracked=True, available_quantity=4, on_hand_quantity=4, inventory_complete=True,
        local_variant_id=variant.id, canonical_variant_id=str(uuid.uuid4()),
        mapping_state="mapped", synced_at=main.now(),
    )
    db.add_all([connection, product, snapshot])
    db.commit()

    deleted_drafts = []

    def reject_reservation(conn, session, query, variables=None):
        if "CirvannaFindInventoryReservation" in query:
            return {"draftOrders": {"nodes": []}}
        if "CirvannaReserveInventory" in query:
            return {"draftOrderCreate": {
                "draftOrder": (
                    {"id": "gid://shopify/DraftOrder/902", "status": "OPEN", "ready": False}
                    if partial_draft else None
                ),
                "userErrors": [{"field": ["input", "lineItems"], "message": "Insufficient inventory"}],
            }}
        if "CirvannaReleaseInventoryReservation" in query:
            deleted_drafts.append(variables["id"])
            return {"draftOrderDelete": {"deletedId": variables["id"], "userErrors": []}}
        raise AssertionError("Unexpected Shopify GraphQL operation")

    monkeypatch.setattr(shopify, "_graphql", reject_reservation)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        shopify.prepare_checkout_inventory_reservations(db, order)
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "SHOPIFY_INVENTORY_RESERVATION_REJECTED"
    db.refresh(order)
    db.refresh(variant)
    local = db.scalar(select(main.StockReservation).where(main.StockReservation.order_id == order.id))
    assert order.state == "checkout_failed"
    assert local.state == "released"
    assert variant.reserved_qty == 0
    assert order.payment_session_id is None
    reservation = db.scalar(select(shopify.ShopifyInventoryReservation).where(
        shopify.ShopifyInventoryReservation.commerce_order_id == order.id
    ))
    if partial_draft:
        assert deleted_drafts == ["gid://shopify/DraftOrder/902"]
        assert reservation.state == "released"
    else:
        assert deleted_drafts == []
        assert reservation.state == "release_pending"
    db.close()


def test_shopify_inventory_reservation_is_staging_only_in_production_by_default(monkeypatch):
    from app.shopify import _shopify_inventory_reservation_enabled

    monkeypatch.delenv("COMMERCE_ENVIRONMENT", raising=False)
    monkeypatch.delenv("SHOPIFY_INVENTORY_RESERVATION_PRODUCTION_ENABLED", raising=False)
    assert _shopify_inventory_reservation_enabled() is False

    monkeypatch.setenv("COMMERCE_ENVIRONMENT", "production")
    assert _shopify_inventory_reservation_enabled() is False

    monkeypatch.setenv("SHOPIFY_INVENTORY_RESERVATION_PRODUCTION_ENABLED", "true")
    assert _shopify_inventory_reservation_enabled() is True

    monkeypatch.setenv("COMMERCE_ENVIRONMENT", "staging")
    monkeypatch.delenv("SHOPIFY_INVENTORY_RESERVATION_PRODUCTION_ENABLED", raising=False)
    assert _shopify_inventory_reservation_enabled() is True


def test_shopify_required_scopes_cover_draft_reservation_without_order_write_scope():
    from app.shopify import REQUIRED_SCOPES

    from app.shopify import COMPENSATION_SCOPES
    assert {"read_draft_orders", "write_draft_orders", "read_orders"} <= REQUIRED_SCOPES
    assert "write_orders" not in REQUIRED_SCOPES
    assert COMPENSATION_SCOPES == {"write_orders"}


def test_shopify_existing_connection_without_draft_scopes_requires_reauthorization(monkeypatch, client):
    from app import shopify
    from fastapi import HTTPException

    seeded = seed_offer(stock=2)
    db = TEST_SESSION()
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=seeded["merchant_id"],
        shop_domain="legacy.myshopify.com", shop_currency="KES",
        granted_scopes=["read_products", "read_inventory", "read_locations", "read_orders"],
        status="active", webhook_registration={}, installed_at=main.now(), updated_at=main.now(),
    )
    db.add(connection)
    db.commit()
    monkeypatch.setattr(shopify, "_oauth_config", lambda: ("api-key", "x" * 32, "https://commerce.example"))
    with pytest.raises(HTTPException) as error:
        shopify._refresh_access_token(connection, db)
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "SHOPIFY_REAUTH_REQUIRED"
    db.refresh(connection)
    assert connection.status == "reauthorization_required"
    db.close()


def test_shopify_backed_stripe_checkout_disables_delayed_payment_methods(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_cirvanna")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_cirvanna")
    monkeypatch.setenv("COMMERCE_CHECKOUT_SUCCESS_URL", "https://cirvanna.example/success")
    monkeypatch.setenv("COMMERCE_CHECKOUT_CANCEL_URL", "https://cirvanna.example/cancel")
    monkeypatch.setenv("COMMERCE_SHIPPING_COUNTRIES", "KE")
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "cs_test_card_only", "url": "https://checkout.stripe.com/test", "status": "open"}

    def fake_post(url, *, data, **kwargs):
        captured.update(data)
        return Response()

    monkeypatch.setattr(main.httpx, "post", fake_post)
    order = SimpleNamespace(
        id="order-shopify-card-only", order_number="CV-CARD-ONLY",
        expires_at=main.now() + main.timedelta(minutes=30),
        destination_country_code=None, currency="KES",
    )
    result = main.StripeGateway().create_session(order, [], [], None, card_only=True)
    assert result["id"] == "cs_test_card_only"
    assert captured["payment_method_types[0]"] == "card"
    assert not any(key.startswith("payment_method_types[") and key != "payment_method_types[0]" for key in captured)
def _seed_pending_market_with_payment_capability(seeded, market_code="UG"):
    db = TEST_SESSION()
    observed = main.now()
    db.add(main.MerchantOperatingMarket(
        id=str(uuid.uuid4()), merchant_id=seeded["merchant_id"],
        market_country_code=market_code, state="pending",
        display_currency="UGX", locale="en-UG",
    ))
    db.add(main.MarketPaymentCapability(
        id=str(uuid.uuid4()), merchant_id=seeded["merchant_id"],
        market_country_code=market_code, provider="stripe", state="active",
        transaction_currencies=["UGX"], settlement_currencies=["KES"],
        payment_methods=["card"], provider_reference="acct-market-ug",
        observed_at=observed, expires_at=observed + main.timedelta(hours=1),
    ))
    db.commit()
    db.close()


def _market_activation_payload():
    observed = main.now()
    return {
        "state": "active", "display_currency": "UGX", "locale": "en-UG",
        "tax_provider": "tax-provider", "tax_provider_reference": "tax-market-ug",
        "tax_capability_observed_at": observed.isoformat(),
        "tax_capability_expires_at": (observed + main.timedelta(hours=1)).isoformat(),
        "fulfillment_provider": "carrier-provider",
        "fulfillment_provider_reference": "carrier-market-ug",
        "fulfillment_capability_observed_at": observed.isoformat(),
        "fulfillment_capability_expires_at": (observed + main.timedelta(hours=1)).isoformat(),
    }


def test_market_activation_rechecks_merchant_verification_for_new_market(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_MARKET_PROVIDER_VERIFICATION_REQUIRED", "true")
    seeded = seed_offer()
    _seed_pending_market_with_payment_capability(seeded, "UG")
    observed = {}
    def reject_stale_kyb(merchant, reference, *, operating_markets):
        observed["reference"] = reference
        observed["markets"] = sorted(operating_markets)
        raise main.HTTPException(403, detail={"code": "MERCHANT_PROVIDER_EVIDENCE_STALE"})
    monkeypatch.setattr(main, "verify_merchant_approval", reject_stale_kyb)

    response = client.put(
        f"/admin/merchants/{seeded['merchant_id']}/markets/UG",
        headers=auth("market-admin", "admin"),
        json=_market_activation_payload(),
    )

    assert response.status_code == 403
    assert observed["markets"] == ["UG"]
    assert observed["reference"] == "verified-by-admin-123"
    db = TEST_SESSION()
    market = db.query(main.MerchantOperatingMarket).filter_by(
        merchant_id=seeded["merchant_id"], market_country_code="UG"
    ).one()
    assert market.state == "pending"
    db.close()


def test_market_activation_fails_closed_when_tax_adapter_rejects_market(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_MARKET_PROVIDER_VERIFICATION_REQUIRED", "true")
    seeded = seed_offer()
    _seed_pending_market_with_payment_capability(seeded, "UG")
    monkeypatch.setattr(main, "verify_merchant_approval", lambda *_args, **_kwargs: {
        "verification_reference": "kyb-provider:case-001", "audit_note": "fresh",
    })
    def reject_tax(**_kwargs):
        raise main.HTTPException(409, detail={"code": "TAX_MARKET_PROVIDER_EVIDENCE_MISMATCH"})
    monkeypatch.setattr(main, "verify_tax_market_capability", reject_tax)

    response = client.put(
        f"/admin/merchants/{seeded['merchant_id']}/markets/UG",
        headers=auth("market-admin", "admin"),
        json=_market_activation_payload(),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "TAX_MARKET_PROVIDER_EVIDENCE_MISMATCH"
    db = TEST_SESSION()
    market = db.query(main.MerchantOperatingMarket).filter_by(
        merchant_id=seeded["merchant_id"], market_country_code="UG"
    ).one()
    assert market.state == "pending"
    db.close()


def test_fulfillment_quote_api_rejects_distance_that_would_round_inside_radius(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_MARKET_CONTEXT_TOKEN", "market-context-token-long-enough-for-tests")
    seeded = seed_offer()
    observed = main.now()
    response = client.post(
        f"/internal/market-context/variants/{seeded['variant_id']}/fulfillment-quotes",
        headers={"X-Commerce-Market-Context-Token": "market-context-token-long-enough-for-tests"},
        json={
            "provider": "carrier-001", "provider_quote_id": "quote-precision-001",
            "destination_country_code": "KE", "destination_key": "Nairobi/Westlands",
            "fulfillment_mode": "courier_delivery", "charge_basis": "per_quote",
            "amount_minor": 250, "currency": "KES", "status": "confirmed",
            "distance_km": "30.004", "observed_at": observed.isoformat(),
            "expires_at": (observed + main.timedelta(hours=1)).isoformat(),
        },
    )
    assert response.status_code == 422


def test_legacy_fulfillment_quotes_without_precision_attestation_are_excluded_from_radius_filters(client, monkeypatch):
    a, b = _market_compare_seed(client, monkeypatch)
    db = TEST_SESSION()
    legacy_quote = db.query(main.OfferFulfillmentQuote).filter_by(variant_id=a["variant_id"]).one()
    # Simulate a pre-gate row whose Numeric(9, 2) value may already have rounded
    # 30.004 km to 30.00 km. Its lost source precision cannot be reconstructed.
    legacy_quote.distance_km = main.Decimal("30.00")
    legacy_quote.distance_precision_verified_at = None
    db.commit()
    db.close()

    base = "/marketplace/offers?market_country_code=KE&destination_key=Nakuru%2FSubukia&fulfillment_mode=courier_delivery"
    default_response = client.get(base, headers=MARKETPLACE_READ_HEADERS)
    assert default_response.status_code == 200, default_response.text
    assert default_response.json()["total"] == 0

    expanded_response = client.get(base + "&radius_km=50", headers=MARKETPLACE_READ_HEADERS)
    assert expanded_response.status_code == 200, expanded_response.text
    assert expanded_response.json()["total"] == 1
    assert expanded_response.json()["items"][0]["merchant_id"] == b["merchant_id"]

    comparison = client.post("/marketplace/compare", headers=MARKETPLACE_READ_HEADERS, json={
        "variant_ids": [a["variant_id"], b["variant_id"]],
        "destination_country_code": "KE",
        "destination_key": "Nakuru/Subukia",
        "fulfillment_mode": "courier_delivery",
        "display_currency": "KES",
    })
    assert comparison.status_code == 200, comparison.text
    assert comparison.json()["status"] == "unavailable"
    assert comparison.json()["reason_code"] == "FULFILLMENT_QUOTE_MISSING_OR_STALE"


def test_local_create_all_upgrades_existing_fulfillment_quote_table():
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    legacy_engine = create_engine("sqlite://", poolclass=StaticPool)
    with legacy_engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE commerce_offer_fulfillment_quotes "
            "(id VARCHAR(36) PRIMARY KEY, distance_km NUMERIC(9, 2))"
        ))

    main._ensure_local_fulfillment_precision_column(legacy_engine)
    columns = {column["name"] for column in main.inspect(legacy_engine).get_columns(
        "commerce_offer_fulfillment_quotes"
    )}
    assert "distance_precision_verified_at" in columns
    legacy_engine.dispose()


def test_readiness_probe_pool_caps_outstanding_work():
    from threading import Event

    release = Event()
    futures = {}

    def blocked_probe():
        release.wait(timeout=3)
        return True

    for index in range(main.READINESS_PROBE_CAPACITY):
        assert main._submit_readiness_probe(futures, str(index), blocked_probe)

    assert not main._submit_readiness_probe(futures, "overflow", lambda: True)
    release.set()
    assert all(future.result(timeout=3) is True for future in futures.values())


def test_readiness_runs_cal_and_provider_probes_under_one_shared_deadline(client, monkeypatch):
    from threading import Barrier

    monkeypatch.setenv("COMMERCE_MARKET_PROVIDER_VERIFICATION_REQUIRED", "true")
    monkeypatch.setattr(main, "_cal_gateway_settings", lambda: (
        "https://cal.example.test", "cal-token", "cal-signing-key-with-more-than-32-bytes",
    ))
    rendezvous = Barrier(6, timeout=0.8)

    def probe(*_args, **_kwargs):
        rendezvous.wait()
        return True

    monkeypatch.setattr(main, "_cal_gateway_probe", probe)
    monkeypatch.setattr(main, "adapter_ready", probe)
    response = client.get("/ready")
    detail = response.json() if response.status_code == 200 else response.json()["detail"]
    assert detail["cal_gateway_ready"] is True
    assert detail["merchant_verification_provider_ready"] is True
    assert detail["fulfillment_provider_ready"] is True
    assert detail["fx_provider_ready"] is True
    assert detail["tax_provider_ready"] is True
    assert detail["payment_capability_provider_ready"] is True


def test_market_declaration_and_activation_use_the_same_parent_row_lock():
    from types import SimpleNamespace
    from sqlalchemy.dialects import postgresql

    statements = []

    class RecordingSession:
        def scalar(self, statement):
            statements.append(statement)
            return SimpleNamespace(state="approved")

    session = RecordingSession()
    actor = main.Actor(user_id="merchant-lock-test", role="merchant")
    main.approved_merchant(session, actor, for_update=True)
    main.lock_merchant_by_id(session, "merchant-lock-test")

    assert len(statements) == 2
    assert all(
        "FOR UPDATE" in str(statement.compile(dialect=postgresql.dialect()))
        for statement in statements
    )


def test_fulfillment_quote_ingestion_marks_validated_distance_precision(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_MARKET_CONTEXT_TOKEN", "market-context-token-long-enough-for-tests")
    seeded = seed_offer()
    observed = main.now()
    response = client.post(
        f"/internal/market-context/variants/{seeded['variant_id']}/fulfillment-quotes",
        headers={"X-Commerce-Market-Context-Token": "market-context-token-long-enough-for-tests"},
        json={
            "provider": "carrier-001", "provider_quote_id": "quote-precision-valid-001",
            "destination_country_code": "KE", "destination_key": "Nairobi/Westlands",
            "fulfillment_mode": "courier_delivery", "charge_basis": "per_quote",
            "amount_minor": 250, "currency": "KES", "status": "confirmed",
            "distance_km": "30.00", "observed_at": observed.isoformat(),
            "expires_at": (observed + main.timedelta(hours=1)).isoformat(),
        },
    )
    assert response.status_code == 200 or response.status_code == 201, response.text
    db = TEST_SESSION()
    quote = db.query(main.OfferFulfillmentQuote).filter_by(
        variant_id=seeded["variant_id"], provider_quote_id="quote-precision-valid-001",
    ).one()
    assert quote.distance_precision_verified_at is not None
    assert quote.distance_km == main.Decimal("30.00")
    db.close()


def _seed_shopify_compensation_case(db, seeded, *, fulfillment_status="UNFULFILLED", include_link=False):
    from app import shopify
    order_id = str(uuid.uuid4())
    order = main.CommerceOrder(
        id=order_id, order_number="CV-COMP-" + order_id[:8], buyer_user_id="buyer-compensation",
        state="paid", payment_state="paid", fulfillment_state="compensation_pending",
        currency="KES", subtotal_minor=500, total_minor=500, commission_minor=0,
        payment_intent_id="pi_compensation_" + order_id[:8],
        idempotency_key="compensation-order-" + order_id,
        expires_at=main.now() + main.timedelta(minutes=30), paid_at=main.now(),
    )
    item = main.OrderItem(
        id=str(uuid.uuid4()), order_id=order_id, merchant_id=seeded["merchant_id"],
        variant_id=seeded["variant_id"], catalog_product_id=seeded["catalog_product_id"],
        product_name="Linen Shirt", sku="LINEN-S", options={"size": "S"}, quantity=1,
        unit_price_minor=500, line_total_minor=500, source_unit_price_minor=500,
        source_currency="KES", commission_bps=300, commission_minor=15,
    )
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=seeded["merchant_id"],
        shop_domain="compensation.myshopify.com", shop_currency="KES",
        granted_scopes=["read_products", "read_inventory", "read_locations", "read_orders",
            "read_draft_orders", "write_draft_orders", "write_orders"],
        status="active", webhook_registration={}, installed_at=main.now(), updated_at=main.now(),
    )
    product_snapshot = shopify.ShopifyProductSnapshot(
        id=str(uuid.uuid4()), connection_id=connection.id,
        shopify_product_gid="gid://shopify/Product/comp-" + order_id[:8],
        title="Linen Shirt", remote_status="ACTIVE", mapping_state="mapped", variants_complete=True,
    )
    variant_snapshot = shopify.ShopifyVariantSnapshot(
        id=str(uuid.uuid4()), connection_id=connection.id, product_snapshot_id=product_snapshot.id,
        shopify_variant_gid="gid://shopify/ProductVariant/comp-" + order_id[:8],
        shopify_inventory_item_gid="gid://shopify/InventoryItem/comp-" + order_id[:8],
        sku="LINEN-S", title="S", options={"size": "S"}, price_minor=500, currency="KES",
        tracked=True, available_quantity=4, on_hand_quantity=4, inventory_complete=True,
        local_variant_id=seeded["variant_id"], mapping_state="mapped",
    )
    reservation = shopify.ShopifyInventoryReservation(
        id=str(uuid.uuid4()), connection_id=connection.id, merchant_id=seeded["merchant_id"],
        commerce_order_id=order_id, reservation_key="cirvanna-reserve-test-" + order_id[:8],
        draft_order_gid="gid://shopify/DraftOrder/" + order_id[:8], state="completion_pending",
        expires_at=main.now() - main.timedelta(minutes=5),
    )
    case = shopify.ShopifyCompensationCase(
        id=str(uuid.uuid4()), commerce_order_id=order_id, merchant_id=seeded["merchant_id"],
        connection_id=connection.id, reservation_id=reservation.id,
        state="pending", last_error="SHOPIFY_DRAFT_COMPLETION_PENDING",
    )
    rows = [order, item, connection, product_snapshot, variant_snapshot, reservation, case]
    if include_link:
        rows.append(shopify.ShopifyOrderLink(
            id=str(uuid.uuid4()), connection_id=connection.id, merchant_id=seeded["merchant_id"],
            commerce_order_id=order_id, idempotency_tag="cirvanna-link-" + order_id[:8],
            shopify_order_gid="gid://shopify/Order/" + order_id[:8],
            link_state="creating", fulfillment_status=fulfillment_status,
        ))
    db.add_all(rows)
    db.commit()
    return order, connection, reservation, case


def test_shopify_compensation_cancellation_job_must_finish_before_case_is_compensated(client, monkeypatch):
    from app import shopify
    seeded = seed_offer(stock=4)
    db = TEST_SESSION()
    order, connection, reservation, case = _seed_shopify_compensation_case(db, seeded, include_link=True)
    case.lease_owner = "test-compensation-worker"
    case.lease_until = main.now() + main.timedelta(seconds=90)
    db.commit()
    calls = []
    inventory_reads = 0
    remote_order = {
        "id": "gid://shopify/Order/comp-1", "name": "#COMP1", "cancelledAt": None,
        "displayFulfillmentStatus": "UNFULFILLED", "fulfillmentOrders": {"nodes": []},
    }

    def fake_graphql(conn, session, query, variables=None):
        nonlocal inventory_reads
        calls.append(query)
        if "CirvannaReadCompensationInventory" in query:
            inventory_reads += 1
            quantity = 8 if inventory_reads == 1 else 9
            return {"inventoryItem": {"id": variables["id"], "inventoryLevels": {
                "nodes": [{"location": {"id": "gid://shopify/Location/comp-1", "isActive": True},
                    "quantities": [{"name": "available", "quantity": quantity}]}],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }}}
        if "CirvannaReadCompensationDraft" in query:
            return {"draftOrder": {"id": reservation.draft_order_gid, "status": "COMPLETED",
                "tags": [reservation.reservation_key], "order": remote_order}}
        if "CirvannaCancelCompensatedOrder" in query:
            assert variables["refundMethod"] == {"originalPaymentMethodsRefund": False}
            assert variables["restock"] is True
            return {"orderCancel": {"job": {"id": "gid://shopify/Job/comp-1", "done": False},
                "jobResult": {"id": "gid://shopify/OrderCancelJobResult/comp-1", "done": False,
                    "status": "STARTED", "errors": [], "order": None}, "orderCancelUserErrors": []}}
        if "CirvannaReadCancellationJobResult" in query:
            return {"node": {"id": "gid://shopify/OrderCancelJobResult/comp-1", "done": True,
                "status": "SUCCEEDED", "errors": [], "order": {"id": remote_order["id"],
                    "cancelledAt": "2026-11-21T10:00:00Z", "displayFulfillmentStatus": "UNFULFILLED"}}}
        raise AssertionError("Unexpected Shopify GraphQL query")

    monkeypatch.setattr(shopify, "_graphql", fake_graphql)
    assert shopify._process_shopify_compensation_case(db, case, order) == "cancel_pending"
    db.refresh(case)
    assert case.cancellation_job_gid == "gid://shopify/OrderCancelJobResult/comp-1"
    assert case.state == "cancel_pending"
    assert shopify._process_shopify_compensation_case(db, case, order) == "compensated"
    db.refresh(case)
    db.refresh(reservation)
    db.refresh(order)
    link = db.scalar(select(shopify.ShopifyOrderLink).where(shopify.ShopifyOrderLink.commerce_order_id == order.id))
    assert case.state == "compensated"
    assert reservation.state == "compensated"
    assert link.link_state == "cancelled"
    assert order.fulfillment_state == "compensation_pending"
    assert any("CirvannaCancelCompensatedOrder" in query for query in calls)
    db.close()


def test_shopify_compensation_blocks_orders_with_active_fulfillment(client, monkeypatch):
    from app import shopify
    seeded = seed_offer(stock=4)
    db = TEST_SESSION()
    order, connection, reservation, case = _seed_shopify_compensation_case(db, seeded)
    calls = []

    def fake_graphql(conn, session, query, variables=None):
        calls.append(query)
        if "CirvannaReadCompensationDraft" in query:
            return {"draftOrder": {"id": reservation.draft_order_gid, "status": "COMPLETED",
                "tags": [reservation.reservation_key], "order": {
                    "id": "gid://shopify/Order/active-1", "cancelledAt": None,
                    "displayFulfillmentStatus": "IN_PROGRESS",
                    "fulfillmentOrders": {"nodes": [{"id": "gid://shopify/FulfillmentOrder/1", "status": "IN_PROGRESS"}]},
                }}}
        raise AssertionError("Cancellation must not be attempted for active fulfillment")

    monkeypatch.setattr(shopify, "_graphql", fake_graphql)
    assert shopify._process_shopify_compensation_case(db, case, order) == "manual_review"
    db.refresh(order)
    assert order.fulfillment_state == "manual_review"
    assert not any("CirvannaCancelCompensatedOrder" in query for query in calls)
    alert = db.scalar(select(main.CommerceOutboxEvent).where(
        main.CommerceOutboxEvent.event_type == "commerce.shopify.compensation.manual_review",
        main.CommerceOutboxEvent.aggregate_id == case.id,
    ))
    assert alert is not None and alert.payload["fulfillment_blocked"] is True
    db.close()


def test_shopify_compensation_releases_draft_when_no_order_was_created(client, monkeypatch):
    from app import shopify
    seeded = seed_offer(stock=4)
    db = TEST_SESSION()
    order, connection, reservation, case = _seed_shopify_compensation_case(db, seeded)
    deleted = []

    def fake_graphql(conn, session, query, variables=None):
        if "CirvannaReadCompensationDraft" in query:
            return {"draftOrder": {"id": reservation.draft_order_gid, "status": "OPEN",
                "tags": [reservation.reservation_key], "order": None}}
        if "CirvannaFindReservationOrder" in query:
            return {"orders": {"nodes": []}}
        if "CirvannaReleaseInventoryReservation" in query:
            deleted.append(variables["id"])
            return {"draftOrderDelete": {"deletedId": variables["id"], "userErrors": []}}
        raise AssertionError("Unexpected Shopify GraphQL query")

    monkeypatch.setattr(shopify, "_graphql", fake_graphql)
    assert shopify._process_shopify_compensation_case(db, case, order) == "compensated"
    db.refresh(reservation)
    assert reservation.state == "released"
    assert deleted == [reservation.draft_order_gid]
    db.close()


def test_stripe_refund_updated_webhook_confirms_full_compensation_refund_only(client, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_unit_only_secret")
    db = TEST_SESSION()
    order = main.CommerceOrder(
        id=str(uuid.uuid4()), order_number="CV-REFUND-CONFIRM", buyer_user_id="buyer-refund-confirm",
        state="paid", payment_state="paid", fulfillment_state="refund_pending", currency="KES",
        subtotal_minor=500, total_minor=500, commission_minor=0, payment_intent_id="pi_refund_confirm",
        idempotency_key="refund-confirm-order", expires_at=main.now() + main.timedelta(minutes=30), paid_at=main.now(),
    )
    attempt = main.StripeRefundAttempt(
        id=str(uuid.uuid4()), order_id=order.id, payment_intent_id="pi_refund_confirm",
        amount_minor=500, currency="KES", idempotency_key="cirvanna-compensation-refund-confirm",
        state="provider_succeeded", attempts=1,
    )
    db.add_all([order, attempt])
    db.commit()
    event = {"id": "evt_refund_compensation_confirm", "type": "refund.updated", "data": {"object": {
        "id": "re_compensation_1", "payment_intent": "pi_refund_confirm", "amount": 500,
        "currency": "kes", "status": "succeeded", "metadata": {
            "commerce_order_id": order.id, "compensation_key": attempt.idempotency_key,
        },
    }}}
    raw = json.dumps(event, separators=(",", ":")).encode()
    signature = sign_stripe_event(raw, "whsec_test_unit_only_secret")
    response = client.post("/webhooks/stripe", content=raw, headers={"Stripe-Signature": signature})
    assert response.status_code == 200, response.text
    db.refresh(order)
    db.refresh(attempt)
    assert order.state == "paid"
    assert order.payment_state == "refunded"
    assert order.refund_state == "refunded"
    assert order.fulfillment_state == "refunded"
    assert order.amount_refunded_minor == 500
    assert attempt.state == "confirmed"
    replay = client.post("/webhooks/stripe", content=raw, headers={"Stripe-Signature": signature})
    assert replay.status_code == 200 and replay.json()["duplicate"] is True
    stale_failure = {"id": "evt_refund_compensation_stale_failure", "type": "refund.updated", "data": {"object": {
        "id": "re_compensation_1", "payment_intent": "pi_refund_confirm", "amount": 500,
        "currency": "kes", "status": "failed", "failure_reason": "stale event", "metadata": {
            "commerce_order_id": order.id, "compensation_key": attempt.idempotency_key,
        },
    }}}
    stale_raw = json.dumps(stale_failure, separators=(",", ":")).encode()
    stale_signature = sign_stripe_event(stale_raw, "whsec_test_unit_only_secret")
    stale_response = client.post("/webhooks/stripe", content=stale_raw, headers={"Stripe-Signature": stale_signature})
    assert stale_response.status_code == 200, stale_response.text
    db.refresh(order)
    db.refresh(attempt)
    assert attempt.state == "confirmed"
    assert order.refund_state == "refunded"
    assert order.fulfillment_state == "refunded"
    db.close()


def test_stripe_compensation_refund_uses_stable_idempotency_key_and_no_checkout_config(client, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_refund_gateway")
    attempt = main.StripeRefundAttempt(
        id=str(uuid.uuid4()), order_id="order-refund-gateway", payment_intent_id="pi_refund_gateway",
        amount_minor=725, currency="KES", idempotency_key="cirvanna-compensation-refund-stable",
        state="prepared", attempts=0,
    )
    captured = {}

    def fake_post(url, **kwargs):
        captured.update({"url": url, **kwargs})
        return FakeResponse({"id": "re_refund_gateway", "payment_intent": "pi_refund_gateway",
            "amount": 725, "currency": "kes", "status": "pending"})

    monkeypatch.setattr(main.httpx, "post", fake_post)
    response = main.StripeGateway().create_compensation_refund(attempt)
    assert response["id"] == "re_refund_gateway"
    assert captured["url"] == "https://api.stripe.com/v1/refunds"
    assert captured["headers"]["Idempotency-Key"] == attempt.idempotency_key
    assert captured["data"]["metadata[commerce_order_id]"] == attempt.order_id
    assert captured["data"]["metadata[compensation_key]"] == attempt.idempotency_key


def test_ambiguous_shopify_order_cancel_is_never_reissued(client, monkeypatch):
    from app import shopify
    from fastapi import HTTPException
    seeded = seed_offer(stock=4)
    db = TEST_SESSION()
    order, connection, reservation, case = _seed_shopify_compensation_case(db, seeded)
    case.lease_owner = "test-compensation-worker"
    case.lease_until = main.now() + main.timedelta(seconds=90)
    db.commit()
    mutation_calls = []

    def ambiguous_graphql(conn, session, query, variables=None):
        if "CirvannaReadCompensationInventory" in query:
            return {"inventoryItem": {"id": variables["id"], "inventoryLevels": {
                "nodes": [{"location": {"id": "gid://shopify/Location/comp-1", "isActive": True},
                    "quantities": [{"name": "available", "quantity": 8}]}],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }}}
        if "CirvannaReadCompensationDraft" in query:
            return {"draftOrder": {"id": reservation.draft_order_gid, "status": "COMPLETED",
                "tags": [reservation.reservation_key], "order": {
                    "id": "gid://shopify/Order/ambiguous-cancel", "cancelledAt": None,
                    "displayFulfillmentStatus": "UNFULFILLED", "fulfillmentOrders": {"nodes": []},
                }}}
        if "CirvannaCancelCompensatedOrder" in query:
            mutation_calls.append(variables["orderId"])
            raise HTTPException(503, detail={"code": "SHOPIFY_API_UNAVAILABLE"})
        if "CirvannaReconcileAmbiguousCancellation" in query:
            return {"order": {"id": variables["id"], "cancelledAt": None,
                "displayFulfillmentStatus": "UNFULFILLED"}}
        raise AssertionError("Unexpected Shopify GraphQL query")

    monkeypatch.setattr(shopify, "_graphql", ambiguous_graphql)
    with pytest.raises(HTTPException):
        shopify._process_shopify_compensation_case(db, case, order)
    db.refresh(case)
    assert case.state == "cancel_requesting"
    assert shopify._process_shopify_compensation_case(db, case, order) == "manual_review"
    assert mutation_calls == ["gid://shopify/Order/ambiguous-cancel"]
    db.close()


def test_paid_shopify_order_is_not_fulfillment_ready_until_provider_order_is_linked(client):
    from app import shopify
    seeded = seed_offer(stock=3)
    db = TEST_SESSION()
    variant = db.get(main.Variant, seeded["variant_id"])
    variant.reserved_qty = 1
    order = main.CommerceOrder(
        id=str(uuid.uuid4()), order_number="CV-PROVIDER-GATE", buyer_user_id="buyer-provider-gate",
        state="pending_payment", payment_state="pending", fulfillment_state="ready", currency="KES",
        subtotal_minor=250, total_minor=250, commission_minor=0, idempotency_key="provider-gate-order",
        expires_at=main.now() + main.timedelta(minutes=30), payment_session_id="cs_provider_gate",
    )
    item = main.OrderItem(
        id=str(uuid.uuid4()), order_id=order.id, merchant_id=seeded["merchant_id"],
        variant_id=seeded["variant_id"], catalog_product_id=seeded["catalog_product_id"],
        product_name="Linen Shirt", sku="LINEN-S", options={"size": "S"}, quantity=1,
        unit_price_minor=250, line_total_minor=250, source_unit_price_minor=250,
        source_currency="KES", commission_bps=300, commission_minor=7,
    )
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=seeded["merchant_id"], shop_domain="gate.myshopify.com",
        shop_currency="KES", granted_scopes=["read_products", "read_inventory", "read_locations", "read_orders",
            "read_draft_orders", "write_draft_orders"], status="active", webhook_registration={},
        installed_at=main.now(), updated_at=main.now(),
    )
    reservation = shopify.ShopifyInventoryReservation(
        id=str(uuid.uuid4()), connection_id=connection.id, merchant_id=seeded["merchant_id"],
        commerce_order_id=order.id, reservation_key="cirvanna-reserve-provider-gate",
        draft_order_gid="gid://shopify/DraftOrder/700", state="reserved",
        expires_at=order.expires_at,
    )
    db.add_all([order, item, connection, reservation, main.StockReservation(
        id=str(uuid.uuid4()), order_id=order.id, variant_id=variant.id, quantity=1,
        state="reserved", expires_at=order.expires_at,
    )])
    db.commit()
    main.settle_paid(db, order, 250, "KES", payment_intent_id="pi_provider_gate")
    db.flush()
    assert order.state == "paid"
    assert order.fulfillment_state == "provider_pending"
    assert main.order_json(db, order)["fulfillment_ready"] is False
    event = db.scalar(select(main.CommerceOutboxEvent).where(
        main.CommerceOutboxEvent.aggregate_id == order.id,
        main.CommerceOutboxEvent.event_type == "commerce.order.paid",
    ))
    assert event.payload["fulfillment_ready"] is False
    assert event.payload["fulfillment_state"] == "provider_pending"
    db.close()


def test_compensation_does_not_refund_multiseller_order_with_non_shopify_seller(client):
    from app import shopify
    seeded = seed_offer(stock=4)
    second = seed_offer(stock=4, owner_user_id="merchant-2")
    db = TEST_SESSION()
    order, connection, reservation, case = _seed_shopify_compensation_case(db, seeded)
    second_item = main.OrderItem(
        id=str(uuid.uuid4()), order_id=order.id, merchant_id=second["merchant_id"],
        variant_id=second["variant_id"], catalog_product_id=second["catalog_product_id"],
        product_name="Other item", sku="OTHER-S", options={}, quantity=1,
        unit_price_minor=100, line_total_minor=100, source_unit_price_minor=100,
        source_currency="KES", commission_bps=300, commission_minor=3,
    )
    db.add(second_item)
    db.commit()
    shopify.begin_shopify_compensation(db, order, "SHOPIFY_DRAFT_COMPLETION_PENDING")
    db.refresh(order)
    cases = list(db.scalars(select(shopify.ShopifyCompensationCase).where(
        shopify.ShopifyCompensationCase.commerce_order_id == order.id,
    )).all())
    assert order.fulfillment_state == "manual_review"
    assert len(cases) == 1
    assert not db.scalar(select(main.StripeRefundAttempt).where(main.StripeRefundAttempt.order_id == order.id))
    db.close()


def test_compensation_refund_request_is_durable_and_reconciled_before_retry(client, monkeypatch):
    from app import shopify
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_compensation_refund")
    db = TEST_SESSION()
    order = main.CommerceOrder(
        id=str(uuid.uuid4()), order_number="CV-REFUND-RECON", buyer_user_id="buyer-refund-recon",
        state="paid", payment_state="paid", fulfillment_state="refund_pending", currency="KES",
        subtotal_minor=725, total_minor=725, commission_minor=0, payment_intent_id="pi_refund_recon",
        idempotency_key="refund-reconciliation-order", expires_at=main.now() + main.timedelta(minutes=30), paid_at=main.now(),
    )
    db.add(order)
    db.commit()
    posts = []

    def fake_post(url, **kwargs):
        posts.append(kwargs)
        return FakeResponse({"id": "re_refund_recon", "payment_intent": "pi_refund_recon",
            "amount": 725, "currency": "kes", "status": "pending"})

    def fake_get(url, **kwargs):
        return FakeResponse({"data": [{"id": "re_refund_recon", "payment_intent": "pi_refund_recon",
            "amount": 725, "currency": "kes", "status": "pending",
            "metadata": {"compensation_key": posts[0]["headers"]["Idempotency-Key"]}}]})

    monkeypatch.setattr(main.httpx, "post", fake_post)
    assert shopify._process_compensation_refund(db, order) == "provider_pending"
    attempt = db.scalar(select(main.StripeRefundAttempt).where(main.StripeRefundAttempt.order_id == order.id))
    assert attempt is not None and attempt.state == "provider_pending"
    assert order.refund_state == "none"
    monkeypatch.setattr(main.httpx, "get", fake_get)
    assert shopify._process_compensation_refund(db, order) == "provider_pending"
    assert len(posts) == 1
    assert posts[0]["headers"]["Idempotency-Key"] == attempt.idempotency_key
    db.close()


def test_ambiguous_stripe_refund_beyond_safe_idempotency_window_requires_manual_review(client, monkeypatch):
    from app import shopify
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_compensation_refund")
    db = TEST_SESSION()
    order = main.CommerceOrder(
        id=str(uuid.uuid4()), order_number="CV-REFUND-AMBIG", buyer_user_id="buyer-refund-ambig",
        state="paid", payment_state="paid", fulfillment_state="refund_pending", currency="KES",
        subtotal_minor=725, total_minor=725, commission_minor=0, payment_intent_id="pi_refund_ambig",
        idempotency_key="refund-ambiguous-order", expires_at=main.now() + main.timedelta(minutes=30), paid_at=main.now(),
    )
    db.add(order)
    db.commit()
    posts = []

    def timeout_post(url, **kwargs):
        posts.append(kwargs)
        raise main.httpx.TimeoutException("simulated ambiguous timeout")

    monkeypatch.setattr(main.httpx, "post", timeout_post)
    assert shopify._process_compensation_refund(db, order) == "ambiguous"
    attempt = db.scalar(select(main.StripeRefundAttempt).where(main.StripeRefundAttempt.order_id == order.id))
    attempt.requested_at = main.now() - main.timedelta(hours=21)
    db.commit()
    monkeypatch.setattr(main.httpx, "get", lambda url, **kwargs: FakeResponse({"data": []}))
    assert shopify._process_compensation_refund(db, order) == "manual_review"
    db.refresh(order)
    db.refresh(attempt)
    assert len(posts) == 1
    assert attempt.state == "manual_review"
    assert order.fulfillment_state == "manual_review"
    assert order.refund_state == "none"
    db.close()


def test_compensation_worker_requests_stripe_refund_only_after_all_seller_cases_are_compensated(client, monkeypatch):
    from app import shopify
    monkeypatch.setenv("COMMERCE_SHOPIFY_SYNC_TOKEN", "shopify-sync-token-with-more-than-32-bytes")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_compensation_worker")
    seeded = seed_offer(stock=4)
    db = TEST_SESSION()
    order, connection, reservation, case = _seed_shopify_compensation_case(db, seeded)
    case.state = "compensated"
    reservation.state = "compensated"
    db.commit()
    captured = {}

    def fake_post(url, **kwargs):
        captured.update({"url": url, **kwargs})
        return FakeResponse({"id": "re_compensation_worker", "payment_intent": order.payment_intent_id,
            "amount": 500, "currency": "kes", "status": "pending"})

    monkeypatch.setattr(main.httpx, "post", fake_post)
    response = client.post("/internal/shopify/compensate-paid-orders", headers={
        "X-Commerce-Shopify-Sync-Token": "shopify-sync-token-with-more-than-32-bytes",
    })
    assert response.status_code == 200, response.text
    assert response.json()["refunds_requested_or_reconciled"] == 1
    attempt = db.scalar(select(main.StripeRefundAttempt).where(main.StripeRefundAttempt.order_id == order.id))
    db.refresh(order)
    assert attempt is not None and attempt.state == "provider_pending"
    assert order.fulfillment_state == "refund_pending"
    assert order.refund_state == "none"
    assert captured["url"] == "https://api.stripe.com/v1/refunds"
    assert captured["headers"]["Idempotency-Key"] == attempt.idempotency_key
    db.close()



def test_shopify_compensation_scope_is_opt_in_for_oauth_install(client, monkeypatch):
    from urllib.parse import parse_qs, urlsplit
    monkeypatch.setenv("SHOPIFY_API_KEY", "shopify-api-key")
    monkeypatch.setenv("SHOPIFY_API_SECRET", "s" * 40)
    monkeypatch.setenv("SHOPIFY_APP_BASE_URL", "https://marketplace.cirvanna.example")
    seeded = seed_offer(stock=2)
    merchant = row(main.Merchant, seeded["merchant_id"])
    headers = auth(merchant.owner_user_id, "merchant")
    monkeypatch.delenv("SHOPIFY_COMPENSATION_SCOPE_ENABLED", raising=False)
    standard = client.get("/integrations/shopify/install?shop=scope-test.myshopify.com", headers=headers, follow_redirects=False)
    assert standard.status_code == 302
    standard_scope = set(parse_qs(urlsplit(standard.headers["location"]).query)["scope"][0].split(","))
    assert "write_orders" not in standard_scope

    monkeypatch.setenv("SHOPIFY_COMPENSATION_SCOPE_ENABLED", "true")
    expanded = client.get("/integrations/shopify/install?shop=scope-test.myshopify.com", headers=headers, follow_redirects=False)
    assert expanded.status_code == 302
    expanded_scope = set(parse_qs(urlsplit(expanded.headers["location"]).query)["scope"][0].split(","))
    assert "write_orders" in expanded_scope
    assert {"read_draft_orders", "write_draft_orders"} <= expanded_scope


def test_paid_shopify_order_with_disconnected_store_is_blocked_and_sent_to_manual_review(client, monkeypatch):
    from app import shopify
    token = "shopify-sync-token-with-more-than-32-bytes"
    monkeypatch.setenv("COMMERCE_SHOPIFY_SYNC_TOKEN", token)
    seeded = seed_offer(stock=4)
    db = TEST_SESSION()
    order, connection, reservation, case = _seed_shopify_compensation_case(db, seeded)
    order.fulfillment_state = "provider_pending"
    connection.status = "uninstalled"
    reservation.state = "reserved"
    case.state = "pending"
    db.commit()

    exported = client.post("/internal/shopify/export-paid-orders", headers={"X-Commerce-Shopify-Sync-Token": token})
    assert exported.status_code == 200, exported.text
    db.refresh(order)
    assert order.fulfillment_state == "compensation_pending"

    compensated = client.post("/internal/shopify/compensate-paid-orders", headers={"X-Commerce-Shopify-Sync-Token": token})
    assert compensated.status_code == 200, compensated.text
    db.refresh(order)
    db.refresh(case)
    assert case.state == "manual_review"
    assert order.fulfillment_state == "manual_review"
    assert not db.scalar(select(main.StripeRefundAttempt).where(main.StripeRefundAttempt.order_id == order.id))
    db.close()


def test_previously_cancelled_shopify_order_requires_restock_evidence(client, monkeypatch):
    from app import shopify
    seeded = seed_offer(stock=4)
    db = TEST_SESSION()
    order, connection, reservation, case = _seed_shopify_compensation_case(db, seeded)
    calls = []

    def fake_graphql(conn, session, query, variables=None):
        calls.append(query)
        if "CirvannaReadCompensationDraft" in query:
            return {"draftOrder": {"id": reservation.draft_order_gid, "status": "COMPLETED",
                "tags": [reservation.reservation_key], "order": {
                    "id": "gid://shopify/Order/already-cancelled", "cancelledAt": "2026-11-21T09:00:00Z",
                    "displayFulfillmentStatus": "UNFULFILLED", "fulfillmentOrders": {"nodes": []},
                }}}
        raise AssertionError("An already-cancelled order must not be cancelled again")

    monkeypatch.setattr(shopify, "_graphql", fake_graphql)
    assert shopify._process_shopify_compensation_case(db, case, order) == "manual_review"
    db.refresh(order)
    assert order.fulfillment_state == "manual_review"
    assert not any("CirvannaCancelCompensatedOrder" in query for query in calls)
    db.close()


def test_shopify_compensation_refuses_cancellation_when_any_inventory_location_is_inactive(client, monkeypatch):
    from app import shopify
    seeded = seed_offer(stock=4)
    db = TEST_SESSION()
    order, connection, reservation, case = _seed_shopify_compensation_case(db, seeded)
    calls = []

    def fake_graphql(conn, session, query, variables=None):
        calls.append(query)
        if "CirvannaReadCompensationDraft" in query:
            return {"draftOrder": {"id": reservation.draft_order_gid, "status": "COMPLETED",
                "tags": [reservation.reservation_key], "order": {
                    "id": "gid://shopify/Order/inactive-location", "cancelledAt": None,
                    "displayFulfillmentStatus": "UNFULFILLED"}}}
        if "CirvannaReadCompensationInventory" in query:
            return {"inventoryItem": {"id": variables["id"], "inventoryLevels": {
                "nodes": [{"location": {"id": "gid://shopify/Location/inactive", "isActive": False},
                    "quantities": [{"name": "available", "quantity": 8}]}],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }}}
        raise AssertionError("Cancellation must not run with an inactive inventory location")

    monkeypatch.setattr(shopify, "_graphql", fake_graphql)
    assert shopify._process_shopify_compensation_case(db, case, order) == "manual_review"
    assert not any("CirvannaCancelCompensatedOrder" in query for query in calls)
    db.refresh(order)
    assert order.fulfillment_state == "manual_review"
    db.close()


def test_shopify_successful_cancel_without_inventory_restock_delta_is_manual_review(client, monkeypatch):
    from app import shopify
    seeded = seed_offer(stock=4)
    db = TEST_SESSION()
    order, connection, reservation, case = _seed_shopify_compensation_case(db, seeded)
    case.lease_owner = "test-compensation-worker"
    case.lease_until = main.now() + main.timedelta(seconds=90)
    db.commit()
    inventory_reads = 0

    def fake_graphql(conn, session, query, variables=None):
        nonlocal inventory_reads
        if "CirvannaReadCompensationInventory" in query:
            inventory_reads += 1
            return {"inventoryItem": {"id": variables["id"], "inventoryLevels": {
                "nodes": [{"location": {"id": "gid://shopify/Location/active", "isActive": True},
                    "quantities": [{"name": "available", "quantity": 8}]}],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }}}
        if "CirvannaReadCompensationDraft" in query:
            return {"draftOrder": {"id": reservation.draft_order_gid, "status": "COMPLETED",
                "tags": [reservation.reservation_key], "order": {
                    "id": "gid://shopify/Order/no-restock", "cancelledAt": None,
                    "displayFulfillmentStatus": "UNFULFILLED"}}}
        if "CirvannaCancelCompensatedOrder" in query:
            return {"orderCancel": {"job": {"id": "gid://shopify/Job/no-restock", "done": False},
                "jobResult": {"id": "gid://shopify/OrderCancelJobResult/no-restock", "done": False,
                    "status": "STARTED", "errors": [], "order": None}, "orderCancelUserErrors": []}}
        if "CirvannaReadCancellationJobResult" in query:
            return {"node": {"id": "gid://shopify/OrderCancelJobResult/no-restock", "done": True,
                "status": "SUCCEEDED", "errors": [], "order": {"id": "gid://shopify/Order/no-restock",
                    "cancelledAt": "2026-11-21T10:00:00Z", "displayFulfillmentStatus": "UNFULFILLED"}}}
        raise AssertionError("Unexpected Shopify GraphQL query")

    monkeypatch.setattr(shopify, "_graphql", fake_graphql)
    assert shopify._process_shopify_compensation_case(db, case, order) == "cancel_pending"
    db.refresh(case)
    assert shopify._process_shopify_compensation_case(db, case, order) == "manual_review"
    db.refresh(order)
    assert inventory_reads == 2
    assert case.state == "manual_review"
    assert order.fulfillment_state == "manual_review"
    db.close()


def test_shopify_inventory_levels_are_fully_paginated_before_stock_is_marked_complete(monkeypatch):
    from app import shopify
    db = TEST_SESSION()
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=str(uuid.uuid4()), shop_domain="inventory-pages.myshopify.com",
        shop_currency="KES", granted_scopes=["read_inventory", "read_locations"], status="active",
        webhook_registration={}, installed_at=main.now(), updated_at=main.now(),
    )
    first = {
        "id": "gid://shopify/InventoryItem/100", "tracked": True,
        "inventoryLevels": {"nodes": [{"id": "gid://shopify/InventoryLevel/1", "isActive": True,
            "location": {"id": "gid://shopify/Location/1", "isActive": True},
            "quantities": [{"name": "available", "quantity": 4}, {"name": "on_hand", "quantity": 6}]}],
            "pageInfo": {"hasNextPage": True, "endCursor": "inventory-cursor-1"}},
    }
    calls = []

    def fake_graphql(conn, session, query, variables=None):
        calls.append(variables)
        assert variables["id"] == first["id"]
        assert variables["after"] == "inventory-cursor-1"
        return {"inventoryItem": {"id": first["id"], "inventoryLevels": {
            "nodes": [{"id": "gid://shopify/InventoryLevel/2", "isActive": True,
                "location": {"id": "gid://shopify/Location/2", "isActive": True},
                "quantities": [{"name": "available", "quantity": 3}, {"name": "on_hand", "quantity": 5}]}],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        }}}

    monkeypatch.setattr(shopify, "_graphql", fake_graphql)
    complete = shopify._complete_inventory_levels(connection, db, first)
    assert len(calls) == 1
    assert shopify._inventory_totals(complete) == (True, 7, 11, True)
    db.close()


def test_shopify_inventory_levels_stay_unsellable_when_page_budget_is_exhausted(monkeypatch):
    from app import shopify
    db = TEST_SESSION()
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=str(uuid.uuid4()), shop_domain="inventory-pages-limit.myshopify.com",
        shop_currency="KES", granted_scopes=["read_inventory", "read_locations"], status="active",
        webhook_registration={}, installed_at=main.now(), updated_at=main.now(),
    )
    first = {"id": "gid://shopify/InventoryItem/101", "tracked": True,
        "inventoryLevels": {"nodes": [{"id": "gid://shopify/InventoryLevel/1", "isActive": True,
            "location": {"id": "gid://shopify/Location/1", "isActive": True},
            "quantities": [{"name": "available", "quantity": 4}, {"name": "on_hand", "quantity": 6}]}],
            "pageInfo": {"hasNextPage": True, "endCursor": "cursor-1"}}}

    def fake_graphql(conn, session, query, variables=None):
        return {"inventoryItem": {"id": first["id"], "inventoryLevels": {
            "nodes": [{"id": "gid://shopify/InventoryLevel/2", "isActive": True,
                "location": {"id": "gid://shopify/Location/2", "isActive": True},
                "quantities": [{"name": "available", "quantity": 3}, {"name": "on_hand", "quantity": 5}]}],
            "pageInfo": {"hasNextPage": True, "endCursor": "cursor-2"},
        }}}

    monkeypatch.setattr(shopify, "_graphql", fake_graphql)
    partial = shopify._complete_inventory_levels(connection, db, first, max_pages=1)
    assert shopify._inventory_totals(partial) == (True, None, None, False)
    db.close()


def test_shopify_product_webhooks_are_coalesced_to_one_catalog_sync_per_store(client, monkeypatch):
    from app import shopify
    token = "shopify-sync-token-with-more-than-32-bytes"
    monkeypatch.setenv("COMMERCE_SHOPIFY_SYNC_TOKEN", token)
    seeded = seed_offer(stock=3)
    db = TEST_SESSION()
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=seeded["merchant_id"], shop_domain="coalesce.myshopify.com",
        shop_currency="KES", granted_scopes=["read_products", "read_inventory", "read_locations", "read_orders"],
        status="active", webhook_registration={}, installed_at=main.now(), updated_at=main.now(),
    )
    events = [
        shopify.ShopifyWebhookEvent(id=str(uuid.uuid4()), shop_domain=connection.shop_domain,
            delivery_id="delivery-products-update", topic="products/update", payload_sha256="a" * 64),
        shopify.ShopifyWebhookEvent(id=str(uuid.uuid4()), shop_domain=connection.shop_domain,
            delivery_id="delivery-inventory-update", topic="inventory_levels/update", payload_sha256="b" * 64),
    ]
    db.add_all([connection, *events])
    db.commit()
    calls = []
    monkeypatch.setattr(shopify, "_sync_products", lambda conn, session, **kwargs: calls.append(conn.id) or {"has_more": False})
    response = client.post("/internal/shopify/process-events", headers={"X-Commerce-Shopify-Sync-Token": token})
    assert response.status_code == 200, response.text
    assert response.json()["processed"] == 2
    assert calls == [connection.id]
    db.refresh(events[0])
    db.refresh(events[1])
    assert events[0].state == events[1].state == "processed"
    db.close()


def test_shopify_product_webhook_batch_failure_does_not_repeat_catalog_sync(client, monkeypatch):
    from app import shopify
    from fastapi import HTTPException
    token = "shopify-sync-token-with-more-than-32-bytes"
    monkeypatch.setenv("COMMERCE_SHOPIFY_SYNC_TOKEN", token)
    seeded = seed_offer(stock=3)
    db = TEST_SESSION()
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=seeded["merchant_id"], shop_domain="coalesce-fail.myshopify.com",
        shop_currency="KES", granted_scopes=["read_products", "read_inventory", "read_locations", "read_orders"],
        status="active", webhook_registration={}, installed_at=main.now(), updated_at=main.now(),
    )
    events = [
        shopify.ShopifyWebhookEvent(id=str(uuid.uuid4()), shop_domain=connection.shop_domain,
            delivery_id="delivery-products-update-fail", topic="products/update", payload_sha256="c" * 64),
        shopify.ShopifyWebhookEvent(id=str(uuid.uuid4()), shop_domain=connection.shop_domain,
            delivery_id="delivery-inventory-update-fail", topic="inventory_levels/update", payload_sha256="d" * 64),
    ]
    db.add_all([connection, *events])
    db.commit()
    calls = []

    def fail_sync(conn, session, **kwargs):
        calls.append(conn.id)
        raise HTTPException(503, detail={"code": "SHOPIFY_API_UNAVAILABLE"})

    monkeypatch.setattr(shopify, "_sync_products", fail_sync)
    response = client.post("/internal/shopify/process-events", headers={"X-Commerce-Shopify-Sync-Token": token})
    assert response.status_code == 200, response.text
    assert response.json()["failed"] == 2
    assert calls == [connection.id]
    for event in events:
        db.refresh(event)
        assert event.state == "pending"
    db.close()


def test_shopify_reconciliation_paginates_active_stores(client, monkeypatch):
    from app import shopify
    token = "shopify-sync-token-with-more-than-32-bytes"
    monkeypatch.setenv("COMMERCE_SHOPIFY_SYNC_TOKEN", token)
    seeded = [seed_offer(stock=2, owner_user_id=f"merchant-reconcile-{i}") for i in range(3)]
    db = TEST_SESSION()
    connections = []
    for i, item in enumerate(seeded):
        connection = shopify.ShopifyConnection(
            id=f"00000000-0000-0000-0000-00000000000{i+1}", merchant_id=item["merchant_id"],
            shop_domain=f"reconcile-{i}.myshopify.com", shop_currency="KES",
            granted_scopes=["read_products", "read_inventory", "read_locations", "read_orders"],
            status="active", webhook_registration={}, installed_at=main.now(), updated_at=main.now(),
        )
        connections.append(connection)
    db.add_all(connections)
    db.commit()
    webhook_checks = []
    monkeypatch.setattr(shopify, "_webhook_base_url", lambda: "https://commerce.example")
    monkeypatch.setattr(shopify, "_register_webhooks", lambda conn, session, callback: webhook_checks.append(conn.id) or {
        topic: "registered" for topic in shopify.WEBHOOK_TOPICS
    })
    monkeypatch.setattr(shopify, "_sync_products", lambda conn, session, **kwargs: {"has_more": False})

    first = client.post("/internal/shopify/reconcile?connection_limit=2", headers={"X-Commerce-Shopify-Sync-Token": token})
    assert first.status_code == 200, first.text
    assert first.json()["stores_checked"] == 2
    assert first.json()["webhooks_verified"] == 2 * len(shopify.WEBHOOK_TOPICS)
    cursor = first.json()["next_after_connection_id"]
    assert cursor == connections[1].id
    second = client.post(f"/internal/shopify/reconcile?connection_limit=2&after_connection_id={cursor}",
        headers={"X-Commerce-Shopify-Sync-Token": token})
    assert second.status_code == 200, second.text
    assert second.json()["stores_checked"] == 1
    assert second.json()["webhooks_verified"] == len(shopify.WEBHOOK_TOPICS)
    assert second.json()["next_after_connection_id"] is None
    assert webhook_checks == [connections[0].id, connections[1].id, connections[2].id]
    db.close()


def test_shopify_product_sync_persists_page_cursor_and_resumes_after_later_page_failure(client, monkeypatch):
    from app import shopify
    from fastapi import HTTPException
    seeded = seed_offer(stock=2)
    db = TEST_SESSION()
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=seeded["merchant_id"], shop_domain="cursor-resume.myshopify.com",
        shop_currency="KES", granted_scopes=["read_products", "read_inventory", "read_locations", "read_orders"],
        status="active", webhook_registration={}, installed_at=main.now(), updated_at=main.now(),
    )
    db.add(connection)
    db.commit()

    def page(variant_id, sku, *, has_next, cursor=None):
        return {"shop": {"id": "gid://shopify/Shop/1", "name": "Cursor Shop", "currencyCode": "KES"},
            "productVariants": {"edges": [{"node": {
                "id": f"gid://shopify/ProductVariant/{variant_id}", "title": sku, "sku": sku,
                "price": "10.00", "selectedOptions": [],
                "product": {"id": "gid://shopify/Product/1", "title": "Cursor Product",
                    "handle": "cursor-product", "vendor": "Cirvanna", "productType": "Apparel",
                    "status": "ACTIVE", "updatedAt": "2026-11-21T10:00:00Z"},
                "inventoryItem": {"id": f"gid://shopify/InventoryItem/{variant_id}", "tracked": False},
            }}], "pageInfo": {"hasNextPage": has_next, "endCursor": cursor}}}

    calls = []

    def fail_second_page(conn, session, query, variables=None):
        calls.append(variables["after"])
        if variables["after"] is None:
            return page("101", "CURSOR-A", has_next=True, cursor="cursor-page-1")
        raise HTTPException(503, detail={"code": "SHOPIFY_API_UNAVAILABLE"})

    monkeypatch.setattr(shopify, "_graphql", fail_second_page)
    with pytest.raises(HTTPException):
        shopify._sync_products(connection, db, max_pages=5)
    db.rollback()
    db.refresh(connection)
    assert connection.products_cursor == "cursor-page-1"
    assert connection.products_sync_started_at is not None
    assert connection.products_sync_lease_owner is None
    assert connection.products_sync_lease_until is None
    persisted = db.scalar(select(shopify.ShopifyVariantSnapshot).where(
        shopify.ShopifyVariantSnapshot.connection_id == connection.id,
    ))
    assert persisted is not None and persisted.sku == "CURSOR-A"

    resumed_calls = []

    def resume_second_page(conn, session, query, variables=None):
        resumed_calls.append(variables["after"])
        assert variables["after"] == "cursor-page-1"
        return page("102", "CURSOR-B", has_next=False)

    monkeypatch.setattr(shopify, "_graphql", resume_second_page)
    result = shopify._sync_products(connection, db, max_pages=5)
    assert resumed_calls == ["cursor-page-1"]
    assert result["pages_processed"] == 1 and result["has_more"] is False
    db.refresh(connection)
    assert connection.products_cursor is None
    assert connection.products_sync_started_at is None
    assert connection.products_sync_lease_owner is None
    assert connection.products_sync_lease_until is None
    snapshots = list(db.scalars(select(shopify.ShopifyVariantSnapshot).where(
        shopify.ShopifyVariantSnapshot.connection_id == connection.id,
    )).all())
    assert {item.sku for item in snapshots} == {"CURSOR-A", "CURSOR-B"}
    db.close()


def test_shopify_reconciliation_reports_failed_store_for_targeted_retry(client, monkeypatch):
    from app import shopify
    from fastapi import HTTPException
    token = "shopify-sync-token-with-more-than-32-bytes"
    monkeypatch.setenv("COMMERCE_SHOPIFY_SYNC_TOKEN", token)
    seeded = seed_offer(stock=2)
    db = TEST_SESSION()
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=seeded["merchant_id"], shop_domain="reconcile-failed.myshopify.com",
        shop_currency="KES", granted_scopes=["read_products", "read_inventory", "read_locations", "read_orders"],
        status="active", webhook_registration={}, installed_at=main.now(), updated_at=main.now(),
    )
    db.add(connection)
    db.commit()
    monkeypatch.setattr(shopify, "_webhook_base_url", lambda: "https://commerce.example")
    monkeypatch.setattr(shopify, "_register_webhooks", lambda conn, session, callback: {
        topic: "registered" for topic in shopify.WEBHOOK_TOPICS
    })
    monkeypatch.setattr(shopify, "_sync_products", lambda *args, **kwargs: (_ for _ in ()).throw(
        HTTPException(503, detail={"code": "SHOPIFY_API_UNAVAILABLE"})))
    response = client.post(f"/internal/shopify/reconcile?connection_id={connection.id}",
        headers={"X-Commerce-Shopify-Sync-Token": token})
    assert response.status_code == 200, response.text
    assert response.json()["failed_connection_ids"] == [connection.id]
    conflict = client.post(f"/internal/shopify/reconcile?connection_id={connection.id}&after_connection_id={connection.id}",
        headers={"X-Commerce-Shopify-Sync-Token": token})
    assert conflict.status_code == 400
    db.close()



def test_shopify_catalog_sync_lease_blocks_concurrent_store_sync(client, monkeypatch):
    from app import shopify
    from fastapi import HTTPException
    seeded = seed_offer(stock=2)
    db = TEST_SESSION()
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=seeded["merchant_id"], shop_domain="lease.myshopify.com",
        shop_currency="KES", granted_scopes=["read_products", "read_inventory", "read_locations", "read_orders"],
        status="active", webhook_registration={}, installed_at=main.now(), updated_at=main.now(),
        products_sync_lease_owner="another-worker", products_sync_lease_until=main.now() + main.timedelta(minutes=5),
    )
    db.add(connection)
    db.commit()
    monkeypatch.setattr(shopify, "_graphql", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("Provider API must not be called while another worker owns the lease")))
    with pytest.raises(HTTPException) as error:
        shopify._sync_products(connection, db)
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "SHOPIFY_CATALOG_SYNC_ALREADY_RUNNING"
    db.refresh(connection)
    assert connection.products_sync_lease_owner == "another-worker"
    db.close()


def test_shopify_contextual_pricing_batches_and_paginates_mapped_variants(client, monkeypatch):
    from app import shopify
    seeded = seed_offer(stock=2)
    db = TEST_SESSION()
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=seeded["merchant_id"], shop_domain="markets.myshopify.com",
        shop_currency="KES", granted_scopes=["read_products", "read_inventory", "read_locations", "read_orders"],
        status="active", webhook_registration={}, installed_at=main.now(), updated_at=main.now(),
    )
    product = shopify.ShopifyProductSnapshot(
        id=str(uuid.uuid4()), connection_id=connection.id,
        shopify_product_gid="gid://shopify/Product/contextual-pricing", title="Contextual Pricing",
        remote_status="ACTIVE", mapping_state="mapped", variants_complete=True,
    )
    market = main.MerchantOperatingMarket(
        id=str(uuid.uuid4()), merchant_id=seeded["merchant_id"], market_country_code="KE",
        state="active", display_currency="KES", locale="en-KE",
    )
    variants = []
    for index in range(1, 56):
        variants.append(shopify.ShopifyVariantSnapshot(
            id=f"00000000-0000-0000-0000-{index:012d}", connection_id=connection.id,
            product_snapshot_id=product.id, shopify_variant_gid=f"gid://shopify/ProductVariant/{index}",
            shopify_inventory_item_gid=f"gid://shopify/InventoryItem/{index}", sku=f"CP-{index}",
            title=f"Variant {index}", options={}, price_minor=1000, currency="KES",
            tracked=True, available_quantity=2, on_hand_quantity=2, inventory_complete=True,
            mapping_state="mapped",
        ))
    db.add_all([connection, product, market, *variants])
    db.commit()
    calls = []

    def fake_graphql(conn, session, query, variables=None):
        calls.append(list(variables["ids"]))
        return {"nodes": [{"id": gid, "contextualPricing": {
            "price": {"amount": "15.00", "currencyCode": "KES"},
            "compareAtPrice": {"amount": "18.00", "currencyCode": "KES"},
        }} for gid in variables["ids"]]}

    monkeypatch.setattr(shopify, "_graphql", fake_graphql)
    headers = auth(row(main.Merchant, seeded["merchant_id"]).owner_user_id, "merchant")
    first = client.post("/integrations/shopify/markets/KE/sync-pricing?limit=52", headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["variants_updated"] == 52
    assert first.json()["batches"] == 2
    assert first.json()["has_more"] is True
    assert [len(batch) for batch in calls] == [50, 2]
    cursor = first.json()["next_after_snapshot_id"]

    second = client.post(f"/integrations/shopify/markets/KE/sync-pricing?after_snapshot_id={cursor}&limit=100",
        headers=headers)
    assert second.status_code == 200, second.text
    assert second.json()["variants_updated"] == 3
    assert second.json()["has_more"] is False
    assert [len(batch) for batch in calls] == [50, 2, 3]
    db.refresh(variants[0])
    assert variants[0].regional_prices["KE"]["amount_minor"] == 1500
    assert variants[0].regional_prices["KE"]["compare_at_amount_minor"] == 1800
    assert variants[0].regional_prices["KE"]["landed_cost"] is False
    db.close()


def test_shopify_contextual_pricing_rejects_pending_operating_market(client, monkeypatch):
    from app import shopify
    seeded = seed_offer(stock=2)
    db = TEST_SESSION()
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=seeded["merchant_id"], shop_domain="pending-market.myshopify.com",
        shop_currency="KES", granted_scopes=["read_products", "read_inventory", "read_locations", "read_orders"],
        status="active", webhook_registration={}, installed_at=main.now(), updated_at=main.now(),
    )
    db.add_all([connection, main.MerchantOperatingMarket(
        id=str(uuid.uuid4()), merchant_id=seeded["merchant_id"], market_country_code="KE",
        state="pending", display_currency="KES", locale="en-KE",
    )])
    db.commit()
    monkeypatch.setattr(shopify, "_graphql", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("Pending market must be rejected before provider pricing calls")))
    owner = row(main.Merchant, seeded["merchant_id"]).owner_user_id
    response = client.post("/integrations/shopify/markets/KE/sync-pricing", headers=auth(owner, "merchant"))
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "MERCHANT_MARKET_NOT_ACTIVE"
    db.close()


def test_shopify_shop_redaction_preserves_manual_fulfillment_hold_through_later_payment(client, monkeypatch):
    import base64
    import hashlib
    import hmac
    import json
    from app import shopify

    secret = "s" * 40
    token = "shopify-sync-token-with-more-than-32-bytes"
    monkeypatch.setenv("SHOPIFY_API_KEY", "shopify-api-key")
    monkeypatch.setenv("SHOPIFY_API_SECRET", secret)
    monkeypatch.setenv("SHOPIFY_APP_BASE_URL", "https://commerce.example")
    monkeypatch.setenv("COMMERCE_SHOPIFY_SYNC_TOKEN", token)
    seeded = seed_offer(stock=4)
    db = TEST_SESSION()
    order, connection, reservation, case = _seed_shopify_compensation_case(db, seeded)
    connection_id, reservation_id = connection.id, reservation.id
    order.state = "pending_payment"
    order.payment_state = "pending"
    order.fulfillment_state = "provider_pending"
    order.paid_at = None
    db.delete(case)
    variant = db.get(main.Variant, seeded["variant_id"])
    variant.reserved_qty = 1
    db.add(main.StockReservation(
        id=str(uuid.uuid4()), order_id=order.id, variant_id=variant.id, quantity=1,
        state="reserved", expires_at=main.now() + main.timedelta(minutes=30),
    ))
    db.commit()

    payload = json.dumps({"shop_domain": connection.shop_domain}).encode()
    signature = base64.b64encode(hmac.new(secret.encode(), payload, hashlib.sha256).digest()).decode()
    received = client.post("/webhooks/shopify", content=payload, headers={
        "X-Shopify-Hmac-Sha256": signature,
        "X-Shopify-Topic": "shop/redact",
        "X-Shopify-Shop-Domain": connection.shop_domain,
        "X-Shopify-Webhook-Id": "shop-redact-delivery-1",
    })
    assert received.status_code == 200, received.text
    processed = client.post("/internal/shopify/process-events", headers={"X-Commerce-Shopify-Sync-Token": token})
    assert processed.status_code == 200, processed.text
    assert processed.json()["processed"] == 1 and processed.json()["failed"] == 0
    db.refresh(order)
    assert order.fulfillment_state == "manual_review"
    db.expire_all()
    assert db.get(shopify.ShopifyConnection, connection_id) is None
    assert db.get(shopify.ShopifyInventoryReservation, reservation_id) is None
    assert db.scalar(select(shopify.ShopifyWebhookEvent).where(
        shopify.ShopifyWebhookEvent.shop_domain == "compensation.myshopify.com"
    )) is None

    main.settle_paid(db, order, 500, "KES", order.payment_intent_id)
    db.commit()
    db.refresh(order)
    assert order.state == "paid"
    assert order.fulfillment_state == "manual_review"
    paid_event = db.scalar(select(main.CommerceOutboxEvent).where(
        main.CommerceOutboxEvent.aggregate_id == order.id,
        main.CommerceOutboxEvent.event_type == "commerce.order.paid",
    ))
    assert paid_event is not None
    assert paid_event.payload["fulfillment_ready"] is False
    review_event = db.scalar(select(main.CommerceOutboxEvent).where(
        main.CommerceOutboxEvent.aggregate_id == order.id,
        main.CommerceOutboxEvent.event_type == "commerce.shopify.compensation.manual_review",
    ))
    assert review_event is not None and review_event.payload["fulfillment_blocked"] is True
    db.close()


def test_shopify_inventory_totals_fail_closed_on_duplicate_location_or_malformed_quantities():
    from app.shopify import _inventory_totals
    base = {
        "id": "gid://shopify/InventoryItem/77", "tracked": True,
        "inventoryLevels": {"pageInfo": {"hasNextPage": False}, "nodes": [
            {"id": "gid://shopify/InventoryLevel/77", "isActive": True,
             "location": {"id": "gid://shopify/Location/77", "isActive": True},
             "quantities": [{"name": "available", "quantity": 4}, {"name": "on_hand", "quantity": 6}]},
        ]},
    }
    duplicate_location = {**base, "inventoryLevels": {**base["inventoryLevels"], "nodes": [
        *base["inventoryLevels"]["nodes"],
        {"id": "gid://shopify/InventoryLevel/78", "isActive": True,
         "location": {"id": "gid://shopify/Location/77", "isActive": True},
         "quantities": [{"name": "available", "quantity": 2}, {"name": "on_hand", "quantity": 2}]},
    ]}}
    assert _inventory_totals(duplicate_location) == (True, None, None, False)
    malformed_quantities = {**base, "inventoryLevels": {**base["inventoryLevels"], "nodes": [{
        **base["inventoryLevels"]["nodes"][0],
        "quantities": [{"name": "available", "quantity": True}, {"name": "available", "quantity": 9}],
    }]}}
    assert _inventory_totals(malformed_quantities) == (True, None, None, False)
    missing_page_info = {**base, "inventoryLevels": {"nodes": base["inventoryLevels"]["nodes"]}}
    assert _inventory_totals(missing_page_info) == (True, None, None, False)


def test_shopify_inventory_level_pagination_fails_closed_on_repeated_cursor(monkeypatch):
    from app import shopify
    db = TEST_SESSION()
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=str(uuid.uuid4()), shop_domain="repeated-cursor.myshopify.com",
        shop_currency="KES", granted_scopes=["read_inventory", "read_locations"], status="active",
        webhook_registration={}, installed_at=main.now(), updated_at=main.now(),
    )
    first = {"id": "gid://shopify/InventoryItem/102", "tracked": True,
        "inventoryLevels": {"nodes": [{"id": "gid://shopify/InventoryLevel/1", "isActive": True,
            "location": {"id": "gid://shopify/Location/1", "isActive": True},
            "quantities": [{"name": "available", "quantity": 4}, {"name": "on_hand", "quantity": 6}]}],
            "pageInfo": {"hasNextPage": True, "endCursor": "same-cursor"}}}
    calls = []
    def fake_graphql(conn, session, query, variables=None):
        calls.append(variables["after"])
        return {"inventoryItem": {"id": first["id"], "inventoryLevels": {
            "nodes": [{"id": "gid://shopify/InventoryLevel/2", "isActive": True,
                "location": {"id": "gid://shopify/Location/2", "isActive": True},
                "quantities": [{"name": "available", "quantity": 3}, {"name": "on_hand", "quantity": 5}]}],
            "pageInfo": {"hasNextPage": True, "endCursor": "same-cursor"},
        }}}
    monkeypatch.setattr(shopify, "_graphql", fake_graphql)
    partial = shopify._complete_inventory_levels(connection, db, first)
    assert calls == ["same-cursor"]
    assert shopify._inventory_totals(partial) == (True, None, None, False)
    db.close()


def test_shopify_readiness_does_not_report_catalog_complete_after_interrupted_sync(client):
    from app import shopify
    seeded = seed_offer(stock=2)
    db = TEST_SESSION()
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=seeded["merchant_id"], shop_domain="readiness.myshopify.com",
        shop_currency="KES", granted_scopes=list(shopify.REQUIRED_SCOPES), status="active",
        webhook_registration={topic: "registered" for topic in shopify.WEBHOOK_TOPICS},
        products_synced_at=main.now(), products_sync_started_at=main.now(),
        products_sync_lease_until=main.now() - main.timedelta(minutes=1),
        installed_at=main.now(), updated_at=main.now(),
    )
    db.add(connection)
    db.commit()
    owner = row(main.Merchant, seeded["merchant_id"]).owner_user_id
    response = client.get("/integrations/shopify/readiness", headers=auth(owner, "merchant"))
    assert response.status_code == 200, response.text
    assert response.json()["ready"] is True  # connection and webhooks are configured
    assert response.json()["catalog_ready"] is False
    assert response.json()["products_sync_complete"] is False
    assert response.json()["products_sync_in_progress"] is False
    assert response.json()["products_sync_recovery_required"] is True
    db.close()


def test_shopify_catalog_lease_outlives_worst_case_nested_inventory_page(client, monkeypatch):
    from app import shopify
    from datetime import timezone
    seeded = seed_offer(stock=2)
    db = TEST_SESSION()
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=seeded["merchant_id"],
        shop_domain="lease-duration.myshopify.com", shop_currency="KES",
        granted_scopes=["read_products", "read_inventory", "read_locations", "read_orders"],
        status="active", webhook_registration={}, installed_at=main.now(), updated_at=main.now(),
    )
    db.add(connection)
    db.commit()
    observed = []

    def fake_graphql(conn, session, query, variables=None):
        other = TEST_SESSION()
        persisted = other.get(shopify.ShopifyConnection, connection.id)
        lease_until = persisted.products_sync_lease_until
        if lease_until.tzinfo is None:
            lease_until = lease_until.replace(tzinfo=timezone.utc)
        observed.append((lease_until - main.now()).total_seconds())
        other.close()
        return {
            "shop": {"id": "gid://shopify/Shop/lease", "name": "Lease", "currencyCode": "KES"},
            "productVariants": {"edges": [], "pageInfo": {"hasNextPage": False, "endCursor": None}},
        }

    monkeypatch.setattr(shopify, "_graphql", fake_graphql)
    result = shopify._sync_products(connection, db, max_pages=1)
    assert result["pages_processed"] == 1
    assert observed and observed[0] >= 119 * 60
    assert shopify.CATALOG_SYNC_LEASE_MINUTES * 20 * 60 > 80 * 60
    db.close()


def test_shopify_targeted_reconcile_returns_explicit_error_for_inactive_connection(client, monkeypatch):
    from app import shopify
    token = "shopify-sync-token-with-more-than-32-bytes"
    monkeypatch.setenv("COMMERCE_SHOPIFY_SYNC_TOKEN", token)
    seeded = seed_offer(stock=2)
    db = TEST_SESSION()
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=seeded["merchant_id"],
        shop_domain="reconcile-inactive.myshopify.com", shop_currency="KES",
        granted_scopes=["read_products", "read_inventory", "read_locations", "read_orders"],
        status="reauthorization_required", webhook_registration={},
        installed_at=main.now(), updated_at=main.now(),
    )
    db.add(connection)
    db.commit()
    response = client.post(
        f"/internal/shopify/reconcile?connection_id={connection.id}",
        headers={"X-Commerce-Shopify-Sync-Token": token},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "SHOPIFY_CONNECTION_NOT_ACTIVE"
    assert response.json()["detail"]["connection_status"] == "reauthorization_required"
    db.close()


def test_shopify_inventory_levels_are_fully_paginated_before_stock_is_marked_complete(monkeypatch):
    from app import shopify
    db = TEST_SESSION()
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=str(uuid.uuid4()), shop_domain="inventory-pages.myshopify.com",
        shop_currency="KES", granted_scopes=["read_inventory", "read_locations"], status="active",
        webhook_registration={}, installed_at=main.now(), updated_at=main.now(),
    )
    first = {
        "id": "gid://shopify/InventoryItem/100", "tracked": True,
        "inventoryLevels": {"nodes": [{"id": "gid://shopify/InventoryLevel/1", "isActive": True,
            "location": {"id": "gid://shopify/Location/1", "isActive": True},
            "quantities": [{"name": "available", "quantity": 4}, {"name": "on_hand", "quantity": 6}]}],
            "pageInfo": {"hasNextPage": True, "endCursor": "inventory-cursor-1"}},
    }
    connection.products_sync_lease_owner = "catalog-sync-worker"
    connection.products_sync_lease_until = main.now() + main.timedelta(seconds=30)
    main.Base.metadata.create_all(bind=db.get_bind())
    db.add(connection)
    db.commit()
    calls = []

    def fake_graphql(conn, session, query, variables=None):
        calls.append(variables)
        assert variables["id"] == first["id"]
        assert variables["after"] == "inventory-cursor-1"
        return {"inventoryItem": {"id": first["id"], "inventoryLevels": {
            "nodes": [{"id": "gid://shopify/InventoryLevel/2", "isActive": True,
                "location": {"id": "gid://shopify/Location/2", "isActive": True},
                "quantities": [{"name": "available", "quantity": 3}, {"name": "on_hand", "quantity": 5}]}],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        }}}

    monkeypatch.setattr(shopify, "_graphql", fake_graphql)
    complete = shopify._complete_inventory_levels(connection, db, first, lease_owner="catalog-sync-worker")
    db.refresh(connection)
    assert len(calls) == 1
    lease_until = connection.products_sync_lease_until
    if lease_until.tzinfo is None:
        lease_until = lease_until.replace(tzinfo=main.now().tzinfo)
    assert lease_until > main.now() + main.timedelta(minutes=14)
    assert shopify._inventory_totals(complete) == (True, 7, 11, True)
    db.close()


def test_shopify_inventory_levels_stay_unsellable_when_page_budget_is_exhausted(monkeypatch):
    from app import shopify
    db = TEST_SESSION()
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=str(uuid.uuid4()), shop_domain="inventory-pages-limit.myshopify.com",
        shop_currency="KES", granted_scopes=["read_inventory", "read_locations"], status="active",
        webhook_registration={}, installed_at=main.now(), updated_at=main.now(),
    )
    first = {"id": "gid://shopify/InventoryItem/101", "tracked": True,
        "inventoryLevels": {"nodes": [{"id": "gid://shopify/InventoryLevel/1", "isActive": True,
            "location": {"id": "gid://shopify/Location/1", "isActive": True},
            "quantities": [{"name": "available", "quantity": 4}, {"name": "on_hand", "quantity": 6}]}],
            "pageInfo": {"hasNextPage": True, "endCursor": "cursor-1"}}}

    def fake_graphql(conn, session, query, variables=None):
        return {"inventoryItem": {"id": first["id"], "inventoryLevels": {
            "nodes": [{"id": "gid://shopify/InventoryLevel/2", "isActive": True,
                "location": {"id": "gid://shopify/Location/2", "isActive": True},
                "quantities": [{"name": "available", "quantity": 3}, {"name": "on_hand", "quantity": 5}]}],
            "pageInfo": {"hasNextPage": True, "endCursor": "cursor-2"},
        }}}

    monkeypatch.setattr(shopify, "_graphql", fake_graphql)
    partial = shopify._complete_inventory_levels(connection, db, first, max_pages=1)
    assert shopify._inventory_totals(partial) == (True, None, None, False)
    db.close()


def test_shopify_product_webhooks_are_coalesced_to_one_catalog_sync_per_store(client, monkeypatch):
    from app import shopify
    token = "shopify-sync-token-with-more-than-32-bytes"
    monkeypatch.setenv("COMMERCE_SHOPIFY_SYNC_TOKEN", token)
    seeded = seed_offer(stock=3)
    db = TEST_SESSION()
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=seeded["merchant_id"], shop_domain="coalesce.myshopify.com",
        shop_currency="KES", granted_scopes=["read_products", "read_inventory", "read_locations", "read_orders"],
        status="active", webhook_registration={}, installed_at=main.now(), updated_at=main.now(),
    )
    events = [
        shopify.ShopifyWebhookEvent(id=str(uuid.uuid4()), shop_domain=connection.shop_domain,
            delivery_id="delivery-products-update", topic="products/update", payload_sha256="a" * 64),
        shopify.ShopifyWebhookEvent(id=str(uuid.uuid4()), shop_domain=connection.shop_domain,
            delivery_id="delivery-inventory-update", topic="inventory_levels/update", payload_sha256="b" * 64),
    ]
    db.add_all([connection, *events])
    db.commit()
    calls = []
    monkeypatch.setattr(shopify, "_sync_products", lambda conn, session, **kwargs: calls.append(conn.id) or {"has_more": False})
    response = client.post("/internal/shopify/process-events", headers={"X-Commerce-Shopify-Sync-Token": token})
    assert response.status_code == 200, response.text
    assert response.json()["processed"] == 2
    assert calls == [connection.id]
    db.refresh(events[0])
    db.refresh(events[1])
    assert events[0].state == events[1].state == "processed"
    db.close()


def test_shopify_product_webhook_batch_failure_does_not_repeat_catalog_sync(client, monkeypatch):
    from app import shopify
    from fastapi import HTTPException
    token = "shopify-sync-token-with-more-than-32-bytes"
    monkeypatch.setenv("COMMERCE_SHOPIFY_SYNC_TOKEN", token)
    seeded = seed_offer(stock=3)
    db = TEST_SESSION()
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=seeded["merchant_id"], shop_domain="coalesce-fail.myshopify.com",
        shop_currency="KES", granted_scopes=["read_products", "read_inventory", "read_locations", "read_orders"],
        status="active", webhook_registration={}, installed_at=main.now(), updated_at=main.now(),
    )
    events = [
        shopify.ShopifyWebhookEvent(id=str(uuid.uuid4()), shop_domain=connection.shop_domain,
            delivery_id="delivery-products-update-fail", topic="products/update", payload_sha256="c" * 64),
        shopify.ShopifyWebhookEvent(id=str(uuid.uuid4()), shop_domain=connection.shop_domain,
            delivery_id="delivery-inventory-update-fail", topic="inventory_levels/update", payload_sha256="d" * 64),
    ]
    db.add_all([connection, *events])
    db.commit()
    calls = []

    def fail_sync(conn, session, **kwargs):
        calls.append(conn.id)
        raise HTTPException(503, detail={"code": "SHOPIFY_API_UNAVAILABLE"})

    monkeypatch.setattr(shopify, "_sync_products", fail_sync)
    response = client.post("/internal/shopify/process-events", headers={"X-Commerce-Shopify-Sync-Token": token})
    assert response.status_code == 200, response.text
    assert response.json()["failed"] == 2
    assert calls == [connection.id]
    for event in events:
        db.refresh(event)
        assert event.state == "pending"
    db.close()


def test_shopify_reconciliation_paginates_active_stores(client, monkeypatch):
    from app import shopify
    token = "shopify-sync-token-with-more-than-32-bytes"
    monkeypatch.setenv("COMMERCE_SHOPIFY_SYNC_TOKEN", token)
    seeded = [seed_offer(stock=2, owner_user_id=f"merchant-reconcile-{i}") for i in range(3)]
    db = TEST_SESSION()
    connections = []
    for i, item in enumerate(seeded):
        connection = shopify.ShopifyConnection(
            id=f"00000000-0000-0000-0000-00000000000{i+1}", merchant_id=item["merchant_id"],
            shop_domain=f"reconcile-{i}.myshopify.com", shop_currency="KES",
            granted_scopes=["read_products", "read_inventory", "read_locations", "read_orders"],
            status="active", webhook_registration={}, installed_at=main.now(), updated_at=main.now(),
        )
        connections.append(connection)
    db.add_all(connections)
    db.commit()
    webhook_checks = []
    monkeypatch.setattr(shopify, "_webhook_base_url", lambda: "https://commerce.example")
    monkeypatch.setattr(shopify, "_register_webhooks", lambda conn, session, callback: webhook_checks.append(conn.id) or {
        topic: "registered" for topic in shopify.WEBHOOK_TOPICS
    })
    monkeypatch.setattr(shopify, "_sync_products", lambda conn, session, **kwargs: {"has_more": False})

    first = client.post("/internal/shopify/reconcile?connection_limit=2", headers={"X-Commerce-Shopify-Sync-Token": token})
    assert first.status_code == 200, first.text
    assert first.json()["stores_checked"] == 2
    assert first.json()["webhooks_verified"] == 2 * len(shopify.WEBHOOK_TOPICS)
    cursor = first.json()["next_after_connection_id"]
    assert cursor == connections[1].id
    second = client.post(f"/internal/shopify/reconcile?connection_limit=2&after_connection_id={cursor}",
        headers={"X-Commerce-Shopify-Sync-Token": token})
    assert second.status_code == 200, second.text
    assert second.json()["stores_checked"] == 1
    assert second.json()["webhooks_verified"] == len(shopify.WEBHOOK_TOPICS)
    assert second.json()["next_after_connection_id"] is None
    assert webhook_checks == [connections[0].id, connections[1].id, connections[2].id]
    db.close()


def test_shopify_product_sync_persists_page_cursor_and_resumes_after_later_page_failure(client, monkeypatch):
    from app import shopify
    from fastapi import HTTPException
    seeded = seed_offer(stock=2)
    db = TEST_SESSION()
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=seeded["merchant_id"], shop_domain="cursor-resume.myshopify.com",
        shop_currency="KES", granted_scopes=["read_products", "read_inventory", "read_locations", "read_orders"],
        status="active", webhook_registration={}, installed_at=main.now(), updated_at=main.now(),
    )
    db.add(connection)
    db.commit()

    def page(variant_id, sku, *, has_next, cursor=None):
        return {"shop": {"id": "gid://shopify/Shop/1", "name": "Cursor Shop", "currencyCode": "KES"},
            "productVariants": {"edges": [{"node": {
                "id": f"gid://shopify/ProductVariant/{variant_id}", "title": sku, "sku": sku,
                "price": "10.00", "selectedOptions": [],
                "product": {"id": "gid://shopify/Product/1", "title": "Cursor Product",
                    "handle": "cursor-product", "vendor": "Cirvanna", "productType": "Apparel",
                    "status": "ACTIVE", "updatedAt": "2026-11-21T10:00:00Z"},
                "inventoryItem": {"id": f"gid://shopify/InventoryItem/{variant_id}", "tracked": False},
            }}], "pageInfo": {"hasNextPage": has_next, "endCursor": cursor}}}

    calls = []

    def fail_second_page(conn, session, query, variables=None):
        calls.append(variables["after"])
        if variables["after"] is None:
            return page("101", "CURSOR-A", has_next=True, cursor="cursor-page-1")
        raise HTTPException(503, detail={"code": "SHOPIFY_API_UNAVAILABLE"})

    monkeypatch.setattr(shopify, "_graphql", fail_second_page)
    with pytest.raises(HTTPException):
        shopify._sync_products(connection, db, max_pages=5)
    db.rollback()
    db.refresh(connection)
    assert connection.products_cursor == "cursor-page-1"
    assert connection.products_sync_started_at is not None
    assert connection.products_sync_lease_owner is None
    assert connection.products_sync_lease_until is None
    persisted = db.scalar(select(shopify.ShopifyVariantSnapshot).where(
        shopify.ShopifyVariantSnapshot.connection_id == connection.id,
    ))
    assert persisted is not None and persisted.sku == "CURSOR-A"

    resumed_calls = []

    def resume_second_page(conn, session, query, variables=None):
        resumed_calls.append(variables["after"])
        assert variables["after"] == "cursor-page-1"
        return page("102", "CURSOR-B", has_next=False)

    monkeypatch.setattr(shopify, "_graphql", resume_second_page)
    result = shopify._sync_products(connection, db, max_pages=5)
    assert resumed_calls == ["cursor-page-1"]
    assert result["pages_processed"] == 1 and result["has_more"] is False
    db.refresh(connection)
    assert connection.products_cursor is None
    assert connection.products_sync_started_at is None
    assert connection.products_sync_lease_owner is None
    assert connection.products_sync_lease_until is None
    snapshots = list(db.scalars(select(shopify.ShopifyVariantSnapshot).where(
        shopify.ShopifyVariantSnapshot.connection_id == connection.id,
    )).all())
    assert {item.sku for item in snapshots} == {"CURSOR-A", "CURSOR-B"}
    db.close()


def test_shopify_reconciliation_reports_failed_store_for_targeted_retry(client, monkeypatch):
    from app import shopify
    from fastapi import HTTPException
    token = "shopify-sync-token-with-more-than-32-bytes"
    monkeypatch.setenv("COMMERCE_SHOPIFY_SYNC_TOKEN", token)
    seeded = seed_offer(stock=2)
    db = TEST_SESSION()
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=seeded["merchant_id"], shop_domain="reconcile-failed.myshopify.com",
        shop_currency="KES", granted_scopes=["read_products", "read_inventory", "read_locations", "read_orders"],
        status="active", webhook_registration={}, installed_at=main.now(), updated_at=main.now(),
    )
    db.add(connection)
    db.commit()
    monkeypatch.setattr(shopify, "_webhook_base_url", lambda: "https://commerce.example")
    monkeypatch.setattr(shopify, "_register_webhooks", lambda conn, session, callback: {
        topic: "registered" for topic in shopify.WEBHOOK_TOPICS
    })
    monkeypatch.setattr(shopify, "_sync_products", lambda *args, **kwargs: (_ for _ in ()).throw(
        HTTPException(503, detail={"code": "SHOPIFY_API_UNAVAILABLE"})))
    response = client.post(f"/internal/shopify/reconcile?connection_id={connection.id}",
        headers={"X-Commerce-Shopify-Sync-Token": token})
    assert response.status_code == 200, response.text
    assert response.json()["failed_connection_ids"] == [connection.id]
    conflict = client.post(f"/internal/shopify/reconcile?connection_id={connection.id}&after_connection_id={connection.id}",
        headers={"X-Commerce-Shopify-Sync-Token": token})
    assert conflict.status_code == 400
    db.close()



def test_shopify_catalog_sync_lease_blocks_concurrent_store_sync(client, monkeypatch):
    from app import shopify
    from fastapi import HTTPException
    seeded = seed_offer(stock=2)
    db = TEST_SESSION()
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=seeded["merchant_id"], shop_domain="lease.myshopify.com",
        shop_currency="KES", granted_scopes=["read_products", "read_inventory", "read_locations", "read_orders"],
        status="active", webhook_registration={}, installed_at=main.now(), updated_at=main.now(),
        products_sync_lease_owner="another-worker", products_sync_lease_until=main.now() + main.timedelta(minutes=5),
    )
    db.add(connection)
    db.commit()
    monkeypatch.setattr(shopify, "_graphql", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("Provider API must not be called while another worker owns the lease")))
    with pytest.raises(HTTPException) as error:
        shopify._sync_products(connection, db)
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "SHOPIFY_CATALOG_SYNC_ALREADY_RUNNING"
    db.refresh(connection)
    assert connection.products_sync_lease_owner == "another-worker"
    db.close()


def test_shopify_contextual_pricing_batches_and_paginates_mapped_variants(client, monkeypatch):
    from app import shopify
    seeded = seed_offer(stock=2)
    db = TEST_SESSION()
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=seeded["merchant_id"], shop_domain="markets.myshopify.com",
        shop_currency="KES", granted_scopes=["read_products", "read_inventory", "read_locations", "read_orders"],
        status="active", webhook_registration={}, installed_at=main.now(), updated_at=main.now(),
    )
    product = shopify.ShopifyProductSnapshot(
        id=str(uuid.uuid4()), connection_id=connection.id,
        shopify_product_gid="gid://shopify/Product/contextual-pricing", title="Contextual Pricing",
        remote_status="ACTIVE", mapping_state="mapped", variants_complete=True,
    )
    market = main.MerchantOperatingMarket(
        id=str(uuid.uuid4()), merchant_id=seeded["merchant_id"], market_country_code="KE",
        state="active", display_currency="KES", locale="en-KE",
    )
    variants = []
    for index in range(1, 56):
        variants.append(shopify.ShopifyVariantSnapshot(
            id=f"00000000-0000-0000-0000-{index:012d}", connection_id=connection.id,
            product_snapshot_id=product.id, shopify_variant_gid=f"gid://shopify/ProductVariant/{index}",
            shopify_inventory_item_gid=f"gid://shopify/InventoryItem/{index}", sku=f"CP-{index}",
            title=f"Variant {index}", options={}, price_minor=1000, currency="KES",
            tracked=True, available_quantity=2, on_hand_quantity=2, inventory_complete=True,
            mapping_state="mapped",
        ))
    db.add_all([connection, product, market, *variants])
    db.commit()
    calls = []

    def fake_graphql(conn, session, query, variables=None):
        calls.append(list(variables["ids"]))
        return {"nodes": [{"id": gid, "contextualPricing": {
            "price": {"amount": "15.00", "currencyCode": "KES"},
            "compareAtPrice": {"amount": "18.00", "currencyCode": "KES"},
        }} for gid in variables["ids"]]}

    monkeypatch.setattr(shopify, "_graphql", fake_graphql)
    headers = auth(row(main.Merchant, seeded["merchant_id"]).owner_user_id, "merchant")
    first = client.post("/integrations/shopify/markets/KE/sync-pricing?limit=52", headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["variants_updated"] == 52
    assert first.json()["batches"] == 2
    assert first.json()["has_more"] is True
    assert [len(batch) for batch in calls] == [50, 2]
    cursor = first.json()["next_after_snapshot_id"]

    second = client.post(f"/integrations/shopify/markets/KE/sync-pricing?after_snapshot_id={cursor}&limit=100",
        headers=headers)
    assert second.status_code == 200, second.text
    assert second.json()["variants_updated"] == 3
    assert second.json()["has_more"] is False
    assert [len(batch) for batch in calls] == [50, 2, 3]
    db.refresh(variants[0])
    assert variants[0].regional_prices["KE"]["amount_minor"] == 1500
    assert variants[0].regional_prices["KE"]["compare_at_amount_minor"] == 1800
    assert variants[0].regional_prices["KE"]["landed_cost"] is False
    db.close()


def test_shopify_contextual_pricing_rejects_pending_operating_market(client, monkeypatch):
    from app import shopify
    seeded = seed_offer(stock=2)
    db = TEST_SESSION()
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=seeded["merchant_id"], shop_domain="pending-market.myshopify.com",
        shop_currency="KES", granted_scopes=["read_products", "read_inventory", "read_locations", "read_orders"],
        status="active", webhook_registration={}, installed_at=main.now(), updated_at=main.now(),
    )
    db.add_all([connection, main.MerchantOperatingMarket(
        id=str(uuid.uuid4()), merchant_id=seeded["merchant_id"], market_country_code="KE",
        state="pending", display_currency="KES", locale="en-KE",
    )])
    db.commit()
    monkeypatch.setattr(shopify, "_graphql", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("Pending market must be rejected before provider pricing calls")))
    owner = row(main.Merchant, seeded["merchant_id"]).owner_user_id
    response = client.post("/integrations/shopify/markets/KE/sync-pricing", headers=auth(owner, "merchant"))
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "MERCHANT_MARKET_NOT_ACTIVE"
    db.close()


def test_shopify_inventory_totals_fail_closed_on_duplicate_location_or_malformed_quantities():
    from app.shopify import _inventory_totals
    base = {
        "id": "gid://shopify/InventoryItem/77", "tracked": True,
        "inventoryLevels": {"pageInfo": {"hasNextPage": False}, "nodes": [
            {"id": "gid://shopify/InventoryLevel/77", "isActive": True,
             "location": {"id": "gid://shopify/Location/77", "isActive": True},
             "quantities": [{"name": "available", "quantity": 4}, {"name": "on_hand", "quantity": 6}]},
        ]},
    }
    duplicate_location = {**base, "inventoryLevels": {**base["inventoryLevels"], "nodes": [
        *base["inventoryLevels"]["nodes"],
        {"id": "gid://shopify/InventoryLevel/78", "isActive": True,
         "location": {"id": "gid://shopify/Location/77", "isActive": True},
         "quantities": [{"name": "available", "quantity": 2}, {"name": "on_hand", "quantity": 2}]},
    ]}}
    assert _inventory_totals(duplicate_location) == (True, None, None, False)
    malformed_quantities = {**base, "inventoryLevels": {**base["inventoryLevels"], "nodes": [{
        **base["inventoryLevels"]["nodes"][0],
        "quantities": [{"name": "available", "quantity": True}, {"name": "available", "quantity": 9}],
    }]}}
    assert _inventory_totals(malformed_quantities) == (True, None, None, False)
    missing_page_info = {**base, "inventoryLevels": {"nodes": base["inventoryLevels"]["nodes"]}}
    assert _inventory_totals(missing_page_info) == (True, None, None, False)


def test_shopify_inventory_level_pagination_fails_closed_on_repeated_cursor(monkeypatch):
    from app import shopify
    db = TEST_SESSION()
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=str(uuid.uuid4()), shop_domain="repeated-cursor.myshopify.com",
        shop_currency="KES", granted_scopes=["read_inventory", "read_locations"], status="active",
        webhook_registration={}, installed_at=main.now(), updated_at=main.now(),
    )
    first = {"id": "gid://shopify/InventoryItem/102", "tracked": True,
        "inventoryLevels": {"nodes": [{"id": "gid://shopify/InventoryLevel/1", "isActive": True,
            "location": {"id": "gid://shopify/Location/1", "isActive": True},
            "quantities": [{"name": "available", "quantity": 4}, {"name": "on_hand", "quantity": 6}]}],
            "pageInfo": {"hasNextPage": True, "endCursor": "same-cursor"}}}
    calls = []
    def fake_graphql(conn, session, query, variables=None):
        calls.append(variables["after"])
        return {"inventoryItem": {"id": first["id"], "inventoryLevels": {
            "nodes": [{"id": "gid://shopify/InventoryLevel/2", "isActive": True,
                "location": {"id": "gid://shopify/Location/2", "isActive": True},
                "quantities": [{"name": "available", "quantity": 3}, {"name": "on_hand", "quantity": 5}]}],
            "pageInfo": {"hasNextPage": True, "endCursor": "same-cursor"},
        }}}
    monkeypatch.setattr(shopify, "_graphql", fake_graphql)
    partial = shopify._complete_inventory_levels(connection, db, first)
    assert calls == ["same-cursor"]
    assert shopify._inventory_totals(partial) == (True, None, None, False)
    db.close()


def test_shopify_readiness_does_not_report_catalog_complete_after_interrupted_sync(client):
    from app import shopify
    seeded = seed_offer(stock=2)
    db = TEST_SESSION()
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=seeded["merchant_id"], shop_domain="readiness.myshopify.com",
        shop_currency="KES", granted_scopes=list(shopify.REQUIRED_SCOPES), status="active",
        webhook_registration={topic: "registered" for topic in shopify.WEBHOOK_TOPICS},
        products_synced_at=main.now(), products_sync_started_at=main.now(),
        products_sync_lease_until=main.now() - main.timedelta(minutes=1),
        installed_at=main.now(), updated_at=main.now(),
    )
    db.add(connection)
    db.commit()
    owner = row(main.Merchant, seeded["merchant_id"]).owner_user_id
    response = client.get("/integrations/shopify/readiness", headers=auth(owner, "merchant"))
    assert response.status_code == 200, response.text
    assert response.json()["ready"] is True  # connection and webhooks are configured
    assert response.json()["catalog_ready"] is False
    assert response.json()["products_sync_complete"] is False
    assert response.json()["products_sync_in_progress"] is False
    assert response.json()["products_sync_recovery_required"] is True
    db.close()


def test_shopify_compensation_refuses_cancel_after_lease_is_reclaimed(client, monkeypatch):
    from app import shopify
    from fastapi import HTTPException
    seeded = seed_offer(stock=4)
    db = TEST_SESSION()
    order, connection, reservation, case = _seed_shopify_compensation_case(db, seeded)
    case.lease_owner = "test-compensation-worker"
    case.lease_until = main.now() + main.timedelta(seconds=90)
    db.commit()
    mutation_calls = []

    def fake_graphql(conn, session, query, variables=None):
        if "CirvannaReadCompensationDraft" in query:
            return {"draftOrder": {"id": reservation.draft_order_gid, "status": "COMPLETED",
                "tags": [reservation.reservation_key], "order": {
                    "id": "gid://shopify/Order/lease-fence", "cancelledAt": None,
                    "displayFulfillmentStatus": "UNFULFILLED", "fulfillmentOrders": {"nodes": []},
                }}}
        if "CirvannaReadCompensationInventory" in query:
            session.query(shopify.ShopifyCompensationCase).filter_by(id=case.id).update(
                {"lease_owner": "replacement-worker"}, synchronize_session=False
            )
            session.commit()
            return {"inventoryItem": {"id": variables["id"], "inventoryLevels": {
                "nodes": [{"id": "gid://shopify/InventoryLevel/lease-fence",
                    "location": {"id": "gid://shopify/Location/lease-fence", "isActive": True},
                    "quantities": [{"name": "available", "quantity": 8},
                        {"name": "on_hand", "quantity": 8}]}],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }}}
        if "CirvannaCancelCompensatedOrder" in query:
            mutation_calls.append(variables["orderId"])
            raise AssertionError("A worker with a reclaimed lease must not cancel")
        raise AssertionError("Unexpected Shopify GraphQL query")

    monkeypatch.setattr(shopify, "_graphql", fake_graphql)
    with pytest.raises(HTTPException) as error:
        shopify._process_shopify_compensation_case(db, case, order)
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "SHOPIFY_COMPENSATION_LEASE_LOST"
    assert mutation_calls == []
    db.close()



def test_shopify_inventory_pagination_stops_when_catalog_sync_lease_is_reclaimed(monkeypatch):
    from app import shopify
    from fastapi import HTTPException
    db = TEST_SESSION()
    main.Base.metadata.create_all(bind=db.get_bind())
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=str(uuid.uuid4()), shop_domain="inventory-lease-loss.myshopify.com",
        shop_currency="KES", granted_scopes=["read_inventory", "read_locations"], status="active",
        webhook_registration={}, installed_at=main.now(), updated_at=main.now(),
        products_sync_lease_owner="catalog-sync-worker",
        products_sync_lease_until=main.now() + main.timedelta(seconds=30),
    )
    db.add(connection)
    db.commit()
    first = {
        "id": "gid://shopify/InventoryItem/lease-loss", "tracked": True,
        "inventoryLevels": {"nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": "cursor-1"}},
    }
    calls = []

    def fake_graphql(conn, session, query, variables=None):
        calls.append(variables)
        session.query(shopify.ShopifyConnection).filter_by(id=connection.id).update(
            {"products_sync_lease_owner": "replacement-worker"}, synchronize_session=False
        )
        session.commit()
        return {"inventoryItem": {"id": first["id"], "inventoryLevels": {
            "nodes": [{"id": "gid://shopify/InventoryLevel/lease-loss",
                "location": {"id": "gid://shopify/Location/lease-loss", "isActive": True},
                "quantities": [{"name": "available", "quantity": 3}, {"name": "on_hand", "quantity": 3}]}],
            "pageInfo": {"hasNextPage": True, "endCursor": "cursor-2"},
        }}}

    monkeypatch.setattr(shopify, "_graphql", fake_graphql)
    with pytest.raises(HTTPException) as error:
        shopify._complete_inventory_levels(connection, db, first, lease_owner="catalog-sync-worker")
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "SHOPIFY_CATALOG_SYNC_LEASE_LOST"
    assert len(calls) == 1
    db.close()


def test_shopify_reconciliation_rejects_targeted_non_active_store(client, monkeypatch):
    from app import shopify
    token = "shopify-sync-token-with-more-than-32-bytes"
    monkeypatch.setenv("COMMERCE_SHOPIFY_SYNC_TOKEN", token)
    db = TEST_SESSION()
    connection = shopify.ShopifyConnection(
        id=str(uuid.uuid4()), merchant_id=str(uuid.uuid4()), shop_domain="reconcile-revoked.myshopify.com",
        shop_currency="KES", granted_scopes=[], status="revoked",
        webhook_registration={}, installed_at=main.now(), updated_at=main.now(),
    )
    db.add(connection)
    db.commit()
    response = client.post(
        f"/internal/shopify/reconcile?connection_id={connection.id}",
        headers={"X-Commerce-Shopify-Sync-Token": token},
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "SHOPIFY_CONNECTION_NOT_ACTIVE"
    assert response.json()["detail"]["connection_status"] == "revoked"
    db.close()


def test_shopify_staged_products_are_private_and_scoped_to_approved_merchant_owner(client):
    from app.shopify import ShopifyConnection, ShopifyProductSnapshot, ShopifyVariantSnapshot

    owner_offer = seed_offer(owner_user_id="shopify-owner-1")
    connection = ShopifyConnection(
        id=str(uuid.uuid4()),
        merchant_id=owner_offer["merchant_id"],
        shop_domain="owner-one.myshopify.com",
        shop_currency="KES",
        status="active",
    )
    product = ShopifyProductSnapshot(
        id=str(uuid.uuid4()),
        connection_id=connection.id,
        shopify_product_gid="gid://shopify/Product/1001",
        title="Private staged product",
        remote_status="ACTIVE",
        mapping_state="staged",
        variants_complete=True,
    )
    variant = ShopifyVariantSnapshot(
        id=str(uuid.uuid4()),
        connection_id=connection.id,
        product_snapshot_id=product.id,
        shopify_variant_gid="gid://shopify/ProductVariant/2001",
        sku="PRIVATE-SKU-1",
        title="Default",
        options={"size": "M"},
        price_minor=12000,
        currency="KES",
        tracked=True,
        available_quantity=3,
        inventory_complete=True,
        mapping_state="staged",
    )
    db = TEST_SESSION()
    db.add_all([connection, product, variant])
    db.commit()
    db.close()

    # The owner can inspect their own staging records.
    owner_response = client.get(
        "/integrations/shopify/staged-products",
        headers=auth("shopify-owner-1", "merchant"),
    )
    assert owner_response.status_code == 200, owner_response.text
    assert owner_response.json()["visibility"] == "merchant_only_staging"
    assert [item["title"] for item in owner_response.json()["items"]] == ["Private staged product"]

    # A customer cannot use the merchant staging API, even when the user ID is the owner.
    customer_response = client.get(
        "/integrations/shopify/staged-products",
        headers=auth("shopify-owner-1", "customer"),
    )
    assert customer_response.status_code == 403
    assert customer_response.json()["detail"]["code"] == "MERCHANT_ROLE_REQUIRED"

    # Another approved merchant receives no connection and cannot enumerate the owner's rows.
    seed_offer(owner_user_id="shopify-owner-2")
    other_response = client.get(
        "/integrations/shopify/staged-products",
        headers=auth("shopify-owner-2", "merchant"),
    )
    assert other_response.status_code == 404
    assert other_response.json()["detail"]["code"] == "SHOPIFY_CONNECTION_NOT_FOUND"

    # Anonymous shopper traffic is rejected before any staging data is queried.
    anonymous_response = client.get("/integrations/shopify/staged-products")
    assert anonymous_response.status_code == 401


def test_commerce_purchase_age_evidence_headers_are_subject_and_request_bound():
    from starlette.requests import Request
    attestation = {
        "subject_id": "buyer-age-1", "request_id": "checkout-age-001",
        "purpose": "shopper_eligibility", "jti": str(uuid.uuid4()),
    }
    request = Request({
        "type": "http",
        "headers": [
            (b"x-cirvanna-age-attestation", json.dumps(attestation).encode()),
            (b"x-cirvanna-age-attestation-signature", b"a" * 64),
            (b"x-cirvanna-age-evidence-request-id", b"checkout-age-001"),
        ],
    })
    fields = main._commerce_age_evidence_fields(request, "buyer-age-1")
    assert fields["request_id"] == "checkout-age-001"
    assert fields["age_attestation"] == attestation
    assert fields["age_attestation_signature"] == "a" * 64


def test_commerce_purchase_age_evidence_rejects_wrong_subject():
    from starlette.requests import Request
    attestation = {
        "subject_id": "another-buyer", "request_id": "checkout-age-002",
        "purpose": "shopper_eligibility",
    }
    request = Request({
        "type": "http",
        "headers": [
            (b"x-cirvanna-age-attestation", json.dumps(attestation).encode()),
            (b"x-cirvanna-age-attestation-signature", b"a" * 64),
            (b"x-cirvanna-age-evidence-request-id", b"checkout-age-002"),
        ],
    })
    with pytest.raises(HTTPException):
        main._commerce_age_evidence_fields(request, "buyer-age-1")


def test_commerce_purchase_age_evidence_rejects_partial_headers():
    from starlette.requests import Request
    request = Request({
        "type": "http",
        "headers": [(b"x-cirvanna-age-attestation-signature", b"a" * 64)],
    })
    with pytest.raises(HTTPException):
        main._commerce_age_evidence_fields(request, "buyer-age-1")


def test_oidc_jwks_mode_verifies_es256_supabase_tokens(client, monkeypatch):
    monkeypatch.setenv("COMMERCE_ENVIRONMENT", "production")
    monkeypatch.setenv("COMMERCE_AUTH_MODE", "oidc_jwks")
    monkeypatch.setenv("COMMERCE_JWT_JWKS_URL", "https://opmfudcofezmatqqsfho.supabase.co/auth/v1/.well-known/jwks.json")
    monkeypatch.setenv("COMMERCE_JWT_ISSUER", "https://opmfudcofezmatqqsfho.supabase.co/auth/v1")
    monkeypatch.setenv("COMMERCE_JWT_AUDIENCE", "authenticated")
    monkeypatch.setenv("COMMERCE_JWT_ROLE_CLAIM", "app_role")
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    class SigningKey:
        key = public_key

    class FakeJwksClient:
        def get_signing_key_from_jwt(self, token):
            return SigningKey()

    monkeypatch.setattr(main, "_jwks_client", lambda url: FakeJwksClient())
    claims = {
        "sub": "supabase-customer-1",
        "role": "authenticated",
        "app_role": "customer",
        "iss": "https://opmfudcofezmatqqsfho.supabase.co/auth/v1",
        "aud": "authenticated",
        "exp": int(time.time()) + 300,
        "iat": int(time.time()),
    }
    token = pyjwt.encode(claims, private_key, algorithm="ES256", headers={"kid": "supabase-es256-test"})
    actor = main.decode_actor(token)
    assert actor.user_id == "supabase-customer-1"
    assert actor.role == "customer"

    forged_role = {**claims, "app_role": "root"}
    bad_token = pyjwt.encode(forged_role, private_key, algorithm="ES256", headers={"kid": "supabase-es256-test"})
    rejected = client.get("/cart", headers={"Authorization": "Bearer " + bad_token})
    assert rejected.status_code == 401
