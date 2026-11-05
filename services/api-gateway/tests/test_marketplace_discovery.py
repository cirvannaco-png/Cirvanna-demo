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
    monkeypatch.setattr(main, "_load_verified_usi_profile", lambda _subject, **_kwargs: profile)
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


def test_wardrobe_match_uses_only_exact_declared_item_attributes():
    item = {
        "item_id": "closet-1",
        "category": "tops",
        "attributes": ["blue", "cotton", "minimal"],
    }
    candidate = product(P1, "Blue linen shirt", {"color": "blue", "material": "linen", "style": "minimal"})
    result = main._wardrobe_match(candidate, [item])
    assert result["owned_item_ids"] == ["closet-1"]
    assert result["matched_attributes"] == ["blue", "minimal"]
    assert result["score"] == pytest.approx(0.10)


def test_eepl_context_handoff_rejects_missing_or_stale_provenance():
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    stale = (now - timedelta(hours=8)).isoformat()
    context = main.ContextInput(
        location="Subukia",
        occasion="everyday",
        climate="warm",
        location_source="user_declared",
        location_observed_at=now.isoformat(),
        occasion_source="user_declared",
        occasion_observed_at=now.isoformat(),
        climate_source="weather_provider",
        climate_observed_at=stale,
    )
    normalized, evidence = main._fresh_context_for_eepl(context, strict=True)
    assert normalized.location == "Subukia"
    assert normalized.occasion == "everyday"
    assert normalized.climate is None
    assert evidence["location"]["status"] == "current"
    assert evidence["occasion"]["status"] == "current"
    assert evidence["climate"]["status"] == "stale_or_future"


def test_eepl_wardrobe_context_requires_explicit_timestamp_and_source():
    context = main.ContextInput(location="Nairobi", occasion="formal", climate="warm")
    normalized, evidence = main._fresh_context_for_eepl(context, strict=True)
    assert normalized.location is None
    assert normalized.occasion is None
    assert normalized.climate is None
    assert all(item["status"] == "missing_value_or_provenance" for item in evidence.values())


def test_discovery_uses_verified_wardrobe_and_suppresses_owned_catalog_product(client, monkeypatch):
    from usi import USIProfile, StylePreference
    monkeypatch.setenv("NPL_SERVICE_URL", "https://npl.example.test")
    monkeypatch.setenv("NPL_SERVICE_TOKEN", "npl-internal-token-more-than-thirty-two-bytes")
    monkeypatch.setenv("NPL_EVIDENCE_HMAC_SECRET", "npl-evidence-secret-more-than-thirty-two-bytes")
    products = [
        product(P1, "Blue linen shirt", {"color": "blue", "material": "linen", "style": "minimal"}),
        product(P2, "Classic cotton shirt", {"color": "white", "material": "cotton", "style": "classic"}),
    ]
    offers = [offer(P1, "v1", 10000), offer(P2, "v2", 9000)]
    profile = USIProfile(
        profile_id="profile-1", user_id="subject-verified-1", version="2",
        preferences=(StylePreference(preference_id="p1", user_id="subject-verified-1", attribute="minimal"),),
    )
    monkeypatch.setattr(main, "_resolve_verified_subject", lambda _token: "subject-verified-1")
    monkeypatch.setattr(main, "_load_verified_usi_profile", lambda _subject, **_kwargs: profile)
    monkeypatch.setattr(main, "_load_verified_wardrobe", lambda _subject: [{
        "owner_user_id": "subject-verified-1",
        "item_id": "closet-1",
        "category": "tops",
        "attributes": ["blue", "minimal"],
        "catalog_product_id": P1,
        "status": "active",
    }])
    monkeypatch.setattr(main, "_load_consent_aware_wardrobe_likes", lambda _subject: {})
    monkeypatch.setattr(main, "_discover_catalog_and_offers", lambda _payload: (products, offers))
    captured = {}
    show = main.CandidateDecisionOutput(
        product_id=P2, sku="SKU-2", name="Classic cotton shirt", category="shirt", brand="Cirvanna",
        price_minor=9000, currency="KES", image_urls=[], catalog_version=1, verdict="show",
        may_display=True, reasons=[], policy_version="policy-1", arbitration_contract_version="1",
        decision_pipeline_contract_version="1",
    )
    def decisions(request, _authorization):
        captured["context"] = request.context
        return main.DecisionResponse(schema_version="1.0", request_id="req-wardrobe", created_at="2026-11-05T00:00:00Z", candidates=[show])
    monkeypatch.setattr(main, "evaluate_decisions", decisions)
    request = {
        **payload(),
        "use_wardrobe_context": True,
        "context": {
            "age_years": 25,
            "location": "Subukia",
            "location_source": "user_declared",
            "location_observed_at": "2026-11-05T03:00:00Z",
            "occasion": "everyday",
            "occasion_source": "user_declared",
            "occasion_observed_at": "2026-11-05T03:00:00Z",
            "climate": "warm",
            "climate_source": "user_declared",
            "climate_observed_at": "2026-11-05T03:00:00Z",
        },
    }
    response = client.post("/v1/discover", headers=auth(), json=request)
    assert response.status_code == 200, response.text
    data = response.json()
    assert [x["product"]["product_id"] for x in data["displayable_products"]] == [P2]
    assert data["withheld_candidate_ids"][0]["reason_code"] == "ALREADY_IN_WARDROBE"
    assert data["displayable_products"][0]["wardrobe_compatibility"]["matched_owned_item_ids"] == []
    assert captured["context"].location == "Subukia"
    assert data["wardrobe_context"]["active_item_count"] == 1


def test_wardrobe_discovery_fails_closed_without_npl_configuration(client, monkeypatch):
    monkeypatch.delenv("NPL_SERVICE_URL", raising=False)
    monkeypatch.delenv("NPL_SERVICE_TOKEN", raising=False)
    monkeypatch.delenv("NPL_EVIDENCE_HMAC_SECRET", raising=False)
    monkeypatch.setattr(main, "_resolve_verified_subject", lambda _token: "subject-verified-1")
    monkeypatch.setattr(main, "_load_verified_usi_profile", lambda _subject, **_kwargs: object())
    response = client.post("/v1/discover", headers=auth(), json={**payload(), "use_wardrobe_context": True})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "NPL_PROVIDER_REQUIRED_FOR_WARDROBE_DISCOVERY"


def test_wardrobe_match_adds_bounded_consent_feedback_bonus():
    product = {
        "category": "shirt",
        "attributes": {"color": "blue", "material": "cotton", "style": "minimal"},
    }
    wardrobe = [{
        "item_id": "owned-1",
        "category": "tops",
        "attributes": ["blue", "cotton"],
    }]
    no_feedback = main._wardrobe_match(product, wardrobe, {})
    positive = main._wardrobe_match(product, wardrobe, {"minimal": 0.15, "blue": 0.15})
    assert positive["score"] > no_feedback["score"]
    assert positive["consented_positive_feedback_score"] == 0.15
    assert positive["positive_feedback_attributes"] == ["blue", "minimal"]
    assert positive["score"] <= 0.40


def test_wardrobe_positive_tal_features_ignore_revoked_consent_and_nonpositive_events(monkeypatch):
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    class FakeResponse:
        status_code = 200
        def json(self):
            return {
                "subject_id": "subject-1",
                "consent_receipts": [
                    {"receipt_id": "revoked", "scope": "style_learning", "granted": True, "revoked_at": now.isoformat()},
                    {"receipt_id": "active", "scope": "style_learning", "granted": True, "revoked_at": None},
                ],
                "events": [
                    {"event_id":"like-1","event_kind":"observation","feature_key":"wardrobe.feedback.like","consent_receipt_id":"revoked","observed_at":now.isoformat(),"expires_at":(now+timedelta(days=1)).isoformat(),"value":'{"attributes":["blue"]}'},
                    {"event_id":"like-2","event_kind":"observation","feature_key":"wardrobe.feedback.like","consent_receipt_id":"active","observed_at":now.isoformat(),"expires_at":(now+timedelta(days=1)).isoformat(),"value":'{"attributes":["linen","blue"]}'},
                    {"event_id":"dislike-1","event_kind":"observation","feature_key":"wardrobe.feedback.dislike","consent_receipt_id":"active","observed_at":now.isoformat(),"expires_at":(now+timedelta(days=1)).isoformat(),"value":'{"attributes":["leather"]}'},
                    {"event_id":"expired","event_kind":"observation","feature_key":"wardrobe.feedback.wear","consent_receipt_id":"active","observed_at":now.isoformat(),"expires_at":(now-timedelta(days=1)).isoformat(),"value":'{"attributes":["wool"]}'},
                ],
            }
    class FakeClient:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def get(self,*args,**kwargs): return FakeResponse()
    monkeypatch.setenv("IDENTITY_SERVICE_URL","https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN","identity-internal-token-more-than-thirty-two-bytes")
    monkeypatch.setattr(main.httpx,"Client",FakeClient)
    result=main._load_consent_aware_wardrobe_likes("subject-1")
    assert result == {"blue":0.03,"linen":0.03}


def test_wardrobe_learning_without_identity_provider_has_no_personalization_bonus(monkeypatch):
    monkeypatch.delenv("IDENTITY_SERVICE_URL", raising=False)
    monkeypatch.delenv("IDENTITY_SERVICE_TOKEN", raising=False)
    assert main._load_consent_aware_wardrobe_likes("subject-1") == {}


def test_wardrobe_discovery_can_use_closet_without_identity_profile_provider(monkeypatch):
    monkeypatch.delenv("IDENTITY_SERVICE_URL", raising=False)
    monkeypatch.delenv("IDENTITY_SERVICE_TOKEN", raising=False)
    profile = main._load_verified_usi_profile("verified-subject-1", allow_without_consent=True)
    assert profile.user_id == "verified-subject-1"
    assert profile.preferences == ()
    assert profile.version == "profile-storage-provider-not-configured"


def test_standard_discovery_still_requires_usi_profile_provider(monkeypatch):
    monkeypatch.delenv("IDENTITY_SERVICE_URL", raising=False)
    monkeypatch.delenv("IDENTITY_SERVICE_TOKEN", raising=False)
    with pytest.raises(main.HTTPException) as error:
        main._load_verified_usi_profile("verified-subject-1")
    assert error.value.status_code == 503
