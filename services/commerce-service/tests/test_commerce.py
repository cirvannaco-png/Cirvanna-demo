import base64
import hashlib
import hmac
import json
import os
import time
import uuid

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa

os.environ.setdefault("COMMERCE_DATABASE_URL", "sqlite:///./test-commerce-import.db")
os.environ.setdefault("COMMERCE_AUTO_CREATE_SCHEMA", "true")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main


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
    monkeypatch.setenv("COMMERCE_JWT_ISSUER", "cirvanna-auth")
    monkeypatch.setenv("COMMERCE_JWT_AUDIENCE", "cirvanna-commerce")
    monkeypatch.delenv("COMMERCE_ENVIRONMENT", raising=False)
    monkeypatch.delenv("COMMERCE_AUTH_MODE", raising=False)
    monkeypatch.delenv("COMMERCE_JWT_JWKS_URL", raising=False)
    monkeypatch.delenv("COMMERCE_JWT_ROLE_CLAIM", raising=False)
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
    assert client.get("/ready").status_code == 503


def test_compare_offers_rejects_tax_quote_from_another_destination_zone(client, monkeypatch):
    a, b = _market_compare_seed(client, monkeypatch)
    _make_offer_currency_kes(b)
    db = TEST_SESSION()
    tax = db.query(main.OfferTaxQuote).filter_by(variant_id=b["variant_id"]).one()
    tax.destination_key = "Nakuru/Other"
    db.commit()
    db.close()
    response = client.post("/marketplace/compare", json={
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
    response = client.post("/marketplace/compare", json={
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


def test_multi_market_checkout_learning_and_cal_purchase_schema_revision_0010_is_registered():
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
            {"revision": "20261110_0010"},
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
    assert payload["schema_revision"] == "20261110_0010"
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
    offers = client.get("/marketplace/offers")
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
    assert saved.json()["saved"] is True
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
    response = client.get("/marketplace/offers")
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
    item = client.get("/marketplace/offers").json()["items"][0]
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
    response = client.post("/marketplace/compare", json={
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
    response = client.post("/marketplace/compare", json={
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
    response = client.post("/marketplace/compare", json={
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
    response = client.get("/marketplace/offers", params={"market_country_code":"KE","display_currency":"KES"})
    assert response.status_code == 200
    items = {item["variant_id"]: item for item in response.json()["items"]}
    assert items[b["variant_id"]]["display_price_status"] == "localized"
    assert items[b["variant_id"]]["display_currency"] == "KES"
    assert client.get("/marketplace/offers", params={"display_currency":"KES"}).status_code == 422


def test_market_aware_checkout_revalidates_quotes_and_charges_localized_total(client, monkeypatch):
    merchant, peer = _market_compare_seed(client, monkeypatch)
    _make_offer_currency_kes(peer)
    comparison = client.post("/marketplace/compare", json={
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
    default_response = client.get(base)
    assert default_response.status_code == 200, default_response.text
    default_data = default_response.json()
    assert default_data["total"] == 1
    assert default_data["items"][0]["merchant_id"] == a["merchant_id"]
    quote = default_data["items"][0]["fulfillment_quote"]
    assert float(quote["distance_km"]) == 10.0
    assert quote["display_amount_minor"] == 250

    expanded_response = client.get(base + "&radius_km=50")
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
    response = client.post("/marketplace/compare", json={
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
    response = client.get("/marketplace/offers", params={"market_country_code": "KE", "display_currency": "KES"})
    assert response.status_code == 200
    item = next(value for value in response.json()["items"] if value["variant_id"] == b["variant_id"])
    assert item["display_price_status"] == "conversion_unavailable"
    assert item["display_price_minor"] is None


def test_compare_offers_respects_user_selected_radius(client, monkeypatch):
    a, b = _market_compare_seed(client, monkeypatch)
    response = client.post("/marketplace/compare", json={
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
