import pytest
from fastapi.testclient import TestClient

from app import main

TOKEN = "gateway-discovery-test-token-with-32-bytes"
P1 = "2e4c0b5a-d9b4-4b96-87f0-5c92f120d14f"
P2 = "3e4c0b5a-d9b4-4b96-87f0-5c92f120d14f"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("CIRVANNA_API_TOKEN", TOKEN)
    monkeypatch.setenv("CIRVANNA_AUDIT_DB", str(tmp_path / "audit.sqlite3"))
    monkeypatch.setenv("CIRVANNA_REQUIRE_VERIFIED_IDENTITY", "true")
    return TestClient(main.app)


def payload():
    return {
        "user_id": "subject-verified-1",
        "query": "cotton shirt",
        "category": "shirt",
        "currency": "KES",
        "limit": 10,
        "context": {"age_years": 25, "location": "Nairobi", "occasion": "everyday", "climate": "warm"},
    }


def auth():
    return {
        "Authorization": f"Bearer {TOKEN}",
        "X-End-User-Authorization": "Bearer verified-user-token",
    }


def product(pid, name, attrs):
    return {
        "product_id": pid, "sku": "SKU-" + pid[:4], "name": name, "category": "shirt",
        "brand": "Cirvanna", "price_minor": 10000, "currency": "KES",
        "attributes": attrs, "image_urls": [], "status": "active", "catalog_version": 1,
    }


def offer(pid, variant, price):
    return {
        "catalog_product_id": pid, "variant_id": variant, "listing_id": "listing-" + variant,
        "merchant_id": "merchant-1", "merchant_name": "Merchant", "product_name": "Shirt",
        "category": "shirt", "image_urls": [], "sku": "SKU-" + variant,
        "options": {"size": "M"}, "price_minor": price, "currency": "KES", "available_stock": 4,
    }


def test_discovery_returns_only_products_authorized_by_cal(client, monkeypatch):
    from usi import StylePreference, USIProfile
    products = [product(P1, "Minimal shirt", {"style": "minimal", "material": "cotton"}), product(P2, "Classic shirt", {"style": "classic", "material": "cotton"})]
    offers = [offer(P1, "v1", 10000), offer(P2, "v2", 9000)]
    profile = USIProfile(
        profile_id="profile-1", user_id="subject-verified-1", version="2",
        preferences=(StylePreference(preference_id="p1", user_id="subject-verified-1", attribute="minimal"),),
    )
    monkeypatch.setattr(main, "_resolve_verified_subject", lambda _token: "subject-verified-1")
    monkeypatch.setattr(main, "_load_verified_usi_profile", lambda _subject: profile)
    monkeypatch.setattr(main, "_discover_catalog_and_offers", lambda _payload: (products, offers))
    show = main.CandidateDecisionOutput(
        product_id=P1, sku="SKU-1", name="Minimal shirt", category="shirt", brand="Cirvanna",
        price_minor=10000, currency="KES", image_urls=[], catalog_version=1, verdict="show",
        may_display=True, reasons=[], policy_version="policy-1", arbitration_contract_version="1",
        decision_pipeline_contract_version="1",
    )
    review = main.CandidateDecisionOutput(
        product_id=P2, sku="SKU-2", name="Classic shirt", category="shirt", brand="Cirvanna",
        price_minor=9000, currency="KES", image_urls=[], catalog_version=1, verdict="review",
        may_display=False, reasons=[], policy_version="policy-1", arbitration_contract_version="1",
        decision_pipeline_contract_version="1",
    )
    monkeypatch.setattr(main, "evaluate_decisions", lambda *_args: main.DecisionResponse(
        schema_version="1.0", request_id="req-1", created_at="2026-11-02T00:00:00Z", candidates=[show, review]
    ))
    response = client.post("/v1/discover", headers=auth(), json=payload())
    assert response.status_code == 200, response.text
    data = response.json()
    assert [item["product"]["product_id"] for item in data["displayable_products"]] == [P1]
    assert data["withheld_candidate_ids"][0]["product_id"] == P2
    assert "product" not in data["withheld_candidate_ids"][0]
    assert data["display_authority"] == "CaTaCaCi/CAL"


def test_discovery_fails_closed_when_verified_identity_is_disabled(client, monkeypatch):
    monkeypatch.setenv("CIRVANNA_REQUIRE_VERIFIED_IDENTITY", "false")
    response = client.post("/v1/discover", headers=auth(), json=payload())
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "VERIFIED_IDENTITY_REQUIRED_FOR_DISCOVERY"


def test_rank_score_is_weighted_explicit_match_not_probability():
    from usi import StylePreference, USIProfile
    profile = USIProfile(
        profile_id="profile-1", user_id="subject-1", version="1",
        preferences=(
            StylePreference(preference_id="a", user_id="subject-1", attribute="minimal", weight=0.75),
            StylePreference(preference_id="b", user_id="subject-1", attribute="linen", weight=0.25),
        ),
    )
    score = main._style_rank_score(product(P1, "Minimal linen", {"style": "minimal"}), profile)
    assert score == pytest.approx(0.75)
