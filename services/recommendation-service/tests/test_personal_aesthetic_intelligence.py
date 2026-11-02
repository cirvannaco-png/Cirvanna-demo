from fastapi.testclient import TestClient

from app.complementer import compose_complementary_look
from app.intelligence.learning import build_learning_event
from app.main import app

TOKEN = "complementer-test-token-with-at-least-32-bytes"


def rich_payload():
    return {
        "request_id": "req-aesthetic-2",
        "user_id": "user-explicit-1",
        "preferences": {
            "aesthetics": ["elegant", "cultural"],
            "cultural_contexts": ["user-selected formal celebration styling"],
            "favorite_colors": ["teal", "cream"],
            "avoid_colors": ["neon pink"],
            "favorite_makeup_colors": ["warm bronze"],
            "favorite_jewellery_colors": ["gold"],
            "favorite_accessory_colors": ["cream"],
            "favorite_fragrance_families": ["woody", "amber"],
            "preferred_scent_profiles": ["warm", "spicy"],
            "fragrance_sensitive": False,
            "fragrance_free": False,
            "fragrance_intensity": "light",
            "fragrance_longevity": "long",
            "fragrance_occasions": ["evening", "formal"],
            "fragrance_budget_minor": 800000,
            "fragrance_budget_currency": "KES",
            "earrings_preference": "yes",
            "preferred_earring_shapes": ["huggie"],
            "preferred_metals": ["gold"],
            "necklace_preference": "yes",
            "preferred_necklace_styles": ["layered", "pendant"],
            "glasses_preference": "yes",
            "preferred_glasses_shapes": ["cat_eye"],
            "self_reported_face_shape": "round",
            "preferred_accessories": ["watch", "scarf"],
            "avoid_accessory_categories": ["brooch"],
        },
        "look": {
            "outfit_colors": ["navy"],
            "makeup_colors": ["soft brown"],
            "jewellery_colors": ["gold"],
            "accessory_colors": [],
            "jewellery_current_style": None,
            "neckline": "off_shoulder",
            "hairstyle": "up",
            "climate": "hot_humid",
            "occasion": "evening",
        },
    }


def test_complementer_coordinates_all_look_domains_with_reasons():
    result = compose_complementary_look(rich_payload())
    assert result["status"] == "ready"
    assert result["fragrance"]["families"] == ["woody", "amber"]
    assert result["fragrance"]["longevity_preference"] == "long"
    assert result["fragrance"]["budget"] == {
        "maximum_minor_units": 800000,
        "currency": "KES",
    }
    assert result["colour_coordination"]["makeup"]["suggested_directions"] == ["warm bronze"]
    assert result["necklaces"]["styles"] == ["layered", "pendant"]
    assert result["glasses"]["shapes"] == ["cat_eye"]
    assert result["other_accessories"]["preferred_categories"] == ["watch", "scarf"]
    assert result["aesthetic"]["directions"][1]["cultural_contexts"] == [
        "user-selected formal celebration styling"
    ]
    assert result["look_completion"]["principle"].startswith("Improve the look")


def test_cultural_aesthetic_requires_explicit_selected_context():
    payload = rich_payload()
    payload["preferences"]["cultural_contexts"] = []
    result = compose_complementary_look(payload)
    cultural = next(x for x in result["aesthetic"]["directions"] if x["style"] == "cultural")
    assert cultural["status"] == "needs_input"


def test_explicit_fragrance_free_preference_overrides_scent_and_occasion():
    payload = rich_payload()
    payload["preferences"]["fragrance_free"] = True
    result = compose_complementary_look(payload)
    assert result["fragrance"]["status"] == "withheld_by_preference"
    assert result["fragrance"]["families"] == []
    assert result["fragrance"]["occasion"] is None


def test_rejected_colors_and_avoided_accessories_are_not_reintroduced():
    payload = rich_payload()
    payload["preferences"]["favorite_colors"] = ["neon pink", "teal"]
    result = compose_complementary_look(payload)
    assert "neon pink" not in result["palette"]["accent_colors"]
    assert "brooch" not in result["other_accessories"]["preferred_categories"]


def test_look_completion_is_conservative_and_keeps_identity():
    result = compose_complementary_look(rich_payload())
    assert result["look_completion"]["keep"] == [
        "The user's chosen silhouette, identity and existing statement pieces."
    ]
    assert len(result["look_completion"]["suggestions"]) <= 2
    assert all(item["optional"] for item in result["look_completion"]["suggestions"])


def test_rejected_recommendation_is_a_soft_signal_not_a_hard_npl_veto():
    event = build_learning_event({
        "feedback_id": "fb-1",
        "user_id": "user-1",
        "recommendation_id": "rec-1",
        "category": "fragrance",
        "outcome": "rejected",
        "consent_to_personalization": True,
        "preference_action": "save_preference",
        "preference_value": "avoid heavy gourmand scents",
        "reason_code": "TOO_SWEET",
    })
    assert event["signal_semantics"] == "soft_preference_observation"
    assert event["may_create_hard_npl_veto"] is False
    assert event["preference_value"] == "avoid heavy gourmand scents"
    assert event["persistence"] == "handoff_required"


def test_learning_event_requires_explicit_consent():
    try:
        build_learning_event({
            "feedback_id": "fb-2",
            "user_id": "user-1",
            "recommendation_id": "rec-2",
            "category": "colour",
            "outcome": "approved",
            "consent_to_personalization": False,
        })
    except ValueError as exc:
        assert "consent" in str(exc)
    else:
        raise AssertionError("missing consent must not create a learning event")


def test_feedback_api_requires_consent_and_reports_handoff_only(monkeypatch):
    monkeypatch.setenv("COMPLEMENTER_SERVICE_TOKEN", TOKEN)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app) as client:
        body = {
            "feedback_id": "fb-api-1",
            "user_id": "user-1",
            "recommendation_id": "rec-1",
            "category": "aesthetic",
            "outcome": "approved",
            "consent_to_personalization": False,
        }
        denied = client.post("/v1/complementer/feedback", json=body, headers=headers)
        assert denied.status_code == 400
        body["consent_to_personalization"] = True
        accepted = client.post("/v1/complementer/feedback", json=body, headers=headers)
        assert accepted.status_code == 200
        assert accepted.json()["durable_persistence"] == "not_configured"
        assert accepted.json()["learning_event"]["owner"] == "CaTaCaCi/TAL"


def test_climate_only_sets_a_fallback_intensity_and_never_overrides_user_choice():
    payload = rich_payload()
    payload["preferences"]["fragrance_intensity"] = None
    assert compose_complementary_look(payload)["fragrance"]["intensity"] == "light"
    payload["preferences"]["fragrance_intensity"] = "bold"
    assert compose_complementary_look(payload)["fragrance"]["intensity"] == "bold"
