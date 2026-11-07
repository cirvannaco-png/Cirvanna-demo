from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from npl import NegativePreference, PreferenceSource, TargetType

from app import main


GATEWAY_TOKEN = "integration-gateway-token"
END_USER = "Bearer signed-user-session"


def request_body():
    return {
        "request_id": "pnelly-daily-001",
        "user_id": "signed-user-42",
        "local_date": "2026-11-05",
        "occasion": "work",
        "climate": "hot_dry",
        "wardrobe_items": [
            {
                "item_id": "shirt-001",
                "owner_user_id": "signed-user-42",
                "display_name": "Linen shirt",
                "category": "tops",
                "attributes": ["blue", "linen"],
                "status": "active",
            }
        ],
    }


def test_pnelly_gateway_requires_internal_and_verified_end_user_authentication(monkeypatch):
    monkeypatch.setenv("CIRVANNA_API_TOKEN", GATEWAY_TOKEN)
    client = TestClient(main.app)
    assert client.post("/v1/pnelly/daily-looks", json=request_body()).status_code == 401

    response = client.post(
        "/v1/pnelly/daily-looks",
        headers={"Authorization": f"Bearer {GATEWAY_TOKEN}"},
        json=request_body(),
    )
    assert response.status_code == 401


def test_pnelly_gateway_checks_subject_and_uses_only_active_usi_profile(monkeypatch):
    monkeypatch.setenv("CIRVANNA_API_TOKEN", GATEWAY_TOKEN)
    monkeypatch.setenv("NPL_SERVICE_URL", "https://npl.example.test")
    monkeypatch.setenv("NPL_SERVICE_TOKEN", "npl-internal-token-more-than-thirty-two-bytes")
    monkeypatch.setenv("NPL_EVIDENCE_HMAC_SECRET", "npl-evidence-secret-more-than-thirty-two-bytes")
    monkeypatch.setattr(main, "_resolve_verified_subject", lambda _header: "signed-user-42")
    profile = SimpleNamespace(preferences=[
        SimpleNamespace(attribute="color:teal", active=True),
        SimpleNamespace(attribute="style:editorial", active=False),
        SimpleNamespace(attribute="silhouette:relaxed", active=True),
        SimpleNamespace(attribute="culture:declared-context", active=True),
    ])
    observed = {}

    def load_profile(subject, *, allow_without_consent):
        observed["profile_subject"] = subject
        observed["allow_without_consent"] = allow_without_consent
        return profile

    def compose(payload, style_signals, feedback_signals):
        observed["payload"] = payload
        observed["style_signals"] = style_signals
        observed["feedback_signals"] = feedback_signals
        return {
            "schema_version": "1.0",
            "request_id": payload.request_id,
            "mode": "pnelly_wardrobe_daily_looks",
            "recommendation": {
                "look_count": 3,
                "looks": [{"role": role, "item_ids": ["shirt-001"]} for role in ("everyday", "elevated", "explore")],
            },
        }

    monkeypatch.setattr(main, "_load_verified_usi_profile", load_profile)
    monkeypatch.setattr(main, "_load_persisted_npl_preferences", lambda **_kwargs: ())
    monkeypatch.setattr(main, "_load_consent_aware_wardrobe_likes", lambda _subject: {"teal": 0.12, "linen": 0.06})
    monkeypatch.setattr(main, "_pnelly_daily_looks", compose)
    client = TestClient(main.app)
    response = client.post(
        "/v1/pnelly/daily-looks",
        headers={"Authorization": f"Bearer {GATEWAY_TOKEN}", "X-End-User-Authorization": END_USER},
        json=request_body(),
    )
    assert response.status_code == 200, response.text
    assert observed["profile_subject"] == "signed-user-42"
    assert observed["allow_without_consent"] is True
    assert observed["style_signals"] == ["color:teal", "silhouette:relaxed"]
    assert observed["feedback_signals"] == ["feedback:teal", "feedback:linen"]
    assert response.json()["mode"] == "pnelly_wardrobe_daily_looks"


def test_pnelly_gateway_rejects_subject_or_wardrobe_scope_mismatch(monkeypatch):
    monkeypatch.setenv("CIRVANNA_API_TOKEN", GATEWAY_TOKEN)
    client = TestClient(main.app)
    monkeypatch.setattr(main, "_resolve_verified_subject", lambda _header: "signed-user-42")
    headers = {
        "Authorization": f"Bearer {GATEWAY_TOKEN}",
        "X-End-User-Authorization": END_USER,
    }

    body = request_body()
    body["user_id"] = "another-user"
    response = client.post("/v1/pnelly/daily-looks", headers=headers, json=body)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "REQUEST_SUBJECT_MISMATCH"

    body = request_body()
    body["wardrobe_items"][0]["owner_user_id"] = "another-user"
    response = client.post("/v1/pnelly/daily-looks", headers=headers, json=body)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "WARDROBE_SUBJECT_MISMATCH"


def test_pnelly_gateway_rejects_non_active_wardrobe_snapshot(monkeypatch):
    monkeypatch.setenv("CIRVANNA_API_TOKEN", GATEWAY_TOKEN)
    monkeypatch.setattr(main, "_resolve_verified_subject", lambda _header: "signed-user-42")
    client = TestClient(main.app)
    body = request_body()
    body["wardrobe_items"][0]["status"] = "archived"
    response = client.post(
        "/v1/pnelly/daily-looks",
        headers={"Authorization": f"Bearer {GATEWAY_TOKEN}", "X-End-User-Authorization": END_USER},
        json=body,
    )
    assert response.status_code == 422


def test_pnelly_filters_explicit_npl_hard_vetoes_from_wardrobe(monkeypatch):
    def persisted_preferences(*, request_id, user_id, product_id, attributes):
        if product_id == "shirt-001":
            return (NegativePreference(
                preference_id="avoid-shirt",
                user_id=user_id,
                target_type=TargetType.ITEM,
                target_value="shirt-001",
                source=PreferenceSource.USER_DECLARED,
            ),)
        if "red" in {value.casefold() for value in attributes}:
            return (NegativePreference(
                preference_id="avoid-red",
                user_id=user_id,
                target_type=TargetType.ATTRIBUTE,
                target_value="red",
                source=PreferenceSource.USER_DECLARED,
            ),)
        return ()

    monkeypatch.setattr(main, "_load_persisted_npl_preferences", persisted_preferences)
    items = [
        {"item_id": "shirt-001", "display_name": "Linen shirt", "category": "tops", "attributes": ["blue"]},
        {"item_id": "red-skirt", "display_name": "Red skirt", "category": "skirts", "attributes": ["red"]},
        {"item_id": "navy-trousers", "display_name": "Navy trousers", "category": "trousers", "attributes": ["navy"]},
    ]
    allowed, excluded_count, excluded_ids = main._filter_npl_blocked_wardrobe_items(
        request_id="pnelly-npl-001",
        user_id="signed-user-42",
        wardrobe_items=items,
    )
    assert [item["item_id"] for item in allowed] == ["navy-trousers"]
    assert excluded_count == 2
    assert excluded_ids == ["shirt-001", "red-skirt"]


def test_pnelly_fails_closed_when_persistent_npl_is_not_configured(monkeypatch):
    monkeypatch.setenv("CIRVANNA_API_TOKEN", GATEWAY_TOKEN)
    monkeypatch.delenv("NPL_SERVICE_URL", raising=False)
    monkeypatch.delenv("NPL_SERVICE_TOKEN", raising=False)
    monkeypatch.delenv("NPL_EVIDENCE_HMAC_SECRET", raising=False)
    monkeypatch.setattr(main, "_resolve_verified_subject", lambda _header: "signed-user-42")
    monkeypatch.setattr(main, "_load_verified_usi_profile", lambda *_args, **_kwargs: SimpleNamespace(preferences=[]))
    client = TestClient(main.app)
    response = client.post(
        "/v1/pnelly/daily-looks",
        headers={"Authorization": f"Bearer {GATEWAY_TOKEN}", "X-End-User-Authorization": END_USER},
        json=request_body(),
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "PNELLY_NPL_PROVIDER_NOT_CONFIGURED"


def test_legacy_tari_gateway_route_is_hidden_compatibility_alias(monkeypatch):
    # The canonical handler is registered at both paths during one migration window.
    assert "/v1/pnelly/daily-looks" in main.app.openapi()["paths"]
    assert "/v1/tari/daily-looks" not in main.app.openapi()["paths"]



def test_pnelly_evaluation_trace_inventory_and_npl_blocks_are_gateway_populated(monkeypatch):
    monkeypatch.setenv("CIRVANNA_API_TOKEN", GATEWAY_TOKEN)
    monkeypatch.setenv("PNELLY_EVALUATION_TRACE_ENABLED", "true")
    monkeypatch.setenv("PNELLY_EVALUATION_TRACE_HMAC_SECRET", "trace-secret-with-at-least-thirty-two-bytes")
    monkeypatch.setattr(main, "_resolve_verified_subject", lambda _header: "signed-user-42")
    monkeypatch.setattr(main, "_load_verified_usi_profile", lambda *_args, **_kwargs: SimpleNamespace(preferences=[]))
    monkeypatch.setattr(main, "_pnelly_npl_provider_configured", lambda: True)
    captured = {}
    def filter_items(*, request_id, user_id, wardrobe_items):
        captured["filter_input"] = wardrobe_items
        return wardrobe_items[1:], 1, [wardrobe_items[0]["item_id"]]
    def compose(payload, style_signals, feedback_signals):
        captured["payload"] = payload
        return {"request_id": payload.request_id, "recommendation": {"evaluation_trace": {"trace_version": "1.0"}}}
    monkeypatch.setattr(main, "_filter_npl_blocked_wardrobe_items", filter_items)
    monkeypatch.setattr(main, "_load_consent_aware_wardrobe_likes", lambda _subject: {})
    monkeypatch.setattr(main, "_pnelly_daily_looks", compose)
    body = request_body()
    body["evaluation_wardrobe_items"] = [{
        "item_id": "attacker-item", "owner_user_id": "signed-user-42",
        "display_name": "attacker", "category": "tops", "attributes": [], "status": "active",
    }]
    body["hard_excluded_item_ids"] = ["attacker-item"]
    response = TestClient(main.app).post(
        "/v1/pnelly/daily-looks",
        headers={"Authorization": f"Bearer {GATEWAY_TOKEN}", "X-End-User-Authorization": END_USER},
        json=body,
    )
    assert response.status_code == 200, response.text
    safe = captured["payload"]
    assert [item["item_id"] for item in safe.wardrobe_items] == [
        item["item_id"] for item in body["wardrobe_items"][1:]
    ]
    assert [item["item_id"] for item in safe.evaluation_wardrobe_items] == [
        item["item_id"] for item in body["wardrobe_items"]
    ]
    assert safe.hard_excluded_item_ids == [body["wardrobe_items"][0]["item_id"]]
    assert "attacker-item" not in [item["item_id"] for item in safe.evaluation_wardrobe_items]


def test_pnelly_evaluation_trace_fails_closed_without_hmac_secret(monkeypatch):
    monkeypatch.setenv("CIRVANNA_API_TOKEN", GATEWAY_TOKEN)
    monkeypatch.setenv("PNELLY_EVALUATION_TRACE_ENABLED", "true")
    monkeypatch.delenv("PNELLY_EVALUATION_TRACE_HMAC_SECRET", raising=False)
    monkeypatch.setattr(main, "_resolve_verified_subject", lambda _header: "signed-user-42")
    monkeypatch.setattr(main, "_load_verified_usi_profile", lambda *_args, **_kwargs: SimpleNamespace(preferences=[]))
    monkeypatch.setattr(main, "_pnelly_npl_provider_configured", lambda: True)
    client = TestClient(main.app)
    response = client.post(
        "/v1/pnelly/daily-looks",
        headers={"Authorization": f"Bearer {GATEWAY_TOKEN}", "X-End-User-Authorization": END_USER},
        json=request_body(),
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "PNELLY_EVALUATION_TRACE_SIGNING_NOT_CONFIGURED"
