from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.pnelly_preferences import (
    PnellyPreferenceMutationIn,
    deactivate_pnelly_style_preference,
    list_pnelly_style_preferences,
    replace_pnelly_style_preference,
)


def future_expiry() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()


class Response:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


class Client:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)

    async def put(self, url, **kwargs):
        self.calls.append(("PUT", url, kwargs))
        return self.responses.pop(0)


def consent():
    return Response([{
        "receipt_id": "profile-receipt-001", "scope": "profile_storage",
        "granted": True, "revoked_at": None, "expires_at": future_expiry(),
    }])


def profile(version=3):
    return {
        "subject_id": "customer-42",
        "profile_version": version,
        "preferences": [
            {"preference_id": "pnelly-old-001", "attribute": "style:elegant", "weight": 0.8,
             "active": True, "source": "pnelly_user_confirmed", "source_request_id": "request-save-001"},
            {"preference_id": "pnelly-old-002", "attribute": "color:teal", "weight": 0.8,
             "active": False, "source": "pnelly_user_confirmed", "source_request_id": "request-save-002"},
            {"preference_id": "user-declared-001", "attribute": "style:romantic", "weight": 1.0,
             "active": True, "source": "user_declared"},
        ],
    }


def mutation(**overrides):
    data = {
        "request_id": "request-change-001",
        "consent_receipt_id": "profile-receipt-001",
        "expected_version": 3,
    }
    data.update(overrides)
    return PnellyPreferenceMutationIn(**data)


def test_list_returns_only_pnelly_owned_preferences_and_requires_exact_receipt():
    client = Client([consent(), Response(profile())])
    result = asyncio.run(list_pnelly_style_preferences(
        client, base="https://identity.example.test", token="internal-token", subject="customer-42",
        receipt_id="profile-receipt-001",
    ))
    assert result["profile_version"] == 3
    assert [item["preference_id"] for item in result["preferences"]] == ["pnelly-old-001", "pnelly-old-002"]
    assert result["preferences"][0]["active"] is True
    assert result["preferences"][1]["active"] is False
    assert len(client.calls) == 2


def test_deactivate_changes_only_target_pnelly_preference_with_version_check():
    before = profile()
    after = profile(version=4)
    after["preferences"][0]["active"] = False
    client = Client([consent(), Response(before), Response(after)])
    result = asyncio.run(deactivate_pnelly_style_preference(
        client, base="https://identity.example.test", token="internal-token", subject="customer-42",
        preference_id="pnelly-old-001", payload=mutation(),
    ))
    assert result["status"] == "deactivated"
    assert result["profile_version"] == 4
    sent = client.calls[-1][2]["json"]["preferences"]
    assert sent[0]["active"] is False
    assert sent[1]["active"] is False
    assert sent[2]["source"] == "user_declared"
    assert client.calls[-1][2]["json"]["consent_receipt_id"] == "profile-receipt-001"


def test_replace_creates_new_provenance_and_deactivates_old_preference():
    before = profile()
    after = profile(version=4)
    after["preferences"][0]["active"] = False
    new_id = "pnelly-" + __import__("hashlib").sha256(
        "customer-42|pnelly-old-001|request-change-001|style:classic".encode()
    ).hexdigest()[:32]
    after["preferences"].append({
        "preference_id": new_id, "attribute": "style:classic", "weight": 0.8,
        "active": True, "source": "pnelly_user_confirmed", "source_request_id": "request-change-001",
    })
    client = Client([consent(), Response(before), Response(after)])
    result = asyncio.run(replace_pnelly_style_preference(
        client, base="https://identity.example.test", token="internal-token", subject="customer-42",
        preference_id="pnelly-old-001", payload=mutation(attribute="style:classic"),
    ))
    assert result["status"] == "replaced"
    assert result["preference_id"] == new_id
    sent = client.calls[-1][2]["json"]["preferences"]
    assert sent[0]["active"] is False
    assert sent[-1]["source_request_id"] == "request-change-001"
    assert sent[2]["source"] == "user_declared"


def test_deactivate_rejects_profile_version_conflict_before_write():
    client = Client([consent(), Response(profile(version=4))])
    with pytest.raises(HTTPException) as error:
        asyncio.run(deactivate_pnelly_style_preference(
            client, base="https://identity.example.test", token="internal-token", subject="customer-42",
            preference_id="pnelly-old-001", payload=mutation(),
        ))
    assert error.value.status_code == 409
    assert len(client.calls) == 2


def test_management_rejects_preferences_not_owned_by_pnelly():
    client = Client([consent(), Response(profile())])
    with pytest.raises(HTTPException) as error:
        asyncio.run(deactivate_pnelly_style_preference(
            client, base="https://identity.example.test", token="internal-token", subject="customer-42",
            preference_id="user-declared-001", payload=mutation(),
        ))
    assert error.value.status_code == 404
    assert len(client.calls) == 2


def test_replace_replays_after_success_without_mutating_profile_again():
    before = profile()
    after = profile(version=4)
    after["preferences"][0]["active"] = False
    new_id = "pnelly-" + __import__("hashlib").sha256(
        "customer-42|pnelly-old-001|request-change-001|style:classic".encode()
    ).hexdigest()[:32]
    after["preferences"].append({
        "preference_id": new_id, "attribute": "style:classic", "weight": 0.8,
        "active": True, "source": "pnelly_user_confirmed", "source_request_id": "request-change-001",
    })
    first_client = Client([consent(), Response(before), Response(after)])
    first = asyncio.run(replace_pnelly_style_preference(
        first_client, base="https://identity.example.test", token="internal-token", subject="customer-42",
        preference_id="pnelly-old-001", payload=mutation(attribute="style:classic"),
    ))
    assert first["status"] == "replaced"

    replay_client = Client([consent(), Response(after)])
    replay = asyncio.run(replace_pnelly_style_preference(
        replay_client, base="https://identity.example.test", token="internal-token", subject="customer-42",
        preference_id="pnelly-old-001", payload=mutation(attribute="style:classic"),
    ))
    assert replay["status"] == "replayed"
    assert replay["preference_id"] == new_id
    assert len(replay_client.calls) == 2



def test_pnelly_allowlist_includes_independent_dimensions():
    from app.pnelly_preferences import PNELLY_STYLE_ATTRIBUTES
    expected = {
        "culture:contemporary-african-luxury",
        "culture:kitenge",
        "occasion:wedding",
        "coverage:long-sleeves",
        "market:KE",
        "style:classic",
        "color:jewel-tones",
    }
    assert expected.issubset(PNELLY_STYLE_ATTRIBUTES)



def test_bff_and_usi_pnelly_preference_allowlists_are_identical():
    from pathlib import Path
    import re
    from app.pnelly_preferences import PNELLY_STYLE_ATTRIBUTES

    repository_root = Path(__file__).resolve().parents[3]
    identity_source = (
        repository_root / "services" / "identity-learning-service" / "app" / "main.py"
    ).read_text(encoding="utf-8")
    match = re.search(
        r"PNELLY_CONFIRMED_PROFILE_ATTRIBUTES\s*=\s*\{(.*?)\n\}",
        identity_source,
        flags=re.DOTALL,
    )
    assert match is not None
    identity_attributes = set(re.findall(r'"([^"]+)"', match.group(1)))
    assert PNELLY_STYLE_ATTRIBUTES == identity_attributes


def test_replacing_regional_market_deactivates_previous_active_market():
    from app.pnelly_preferences import PnellyStylePreferenceIn, _build_preference_update

    current = profile()
    current["preferences"].append({
        "preference_id": "pnelly-market-ke", "attribute": "market:KE", "weight": 0.8,
        "active": True, "source": "pnelly_user_confirmed", "source_request_id": "request-market-ke",
    })
    payload = PnellyStylePreferenceIn(
        request_id="request-market-ng", consent_receipt_id="profile-receipt-001", attribute="market:NG",
    )
    _, updated, status = _build_preference_update(subject="customer-42", profile=current, payload=payload)
    assert status is None
    assert updated is not None
    old_market = next(item for item in updated if item["preference_id"] == "pnelly-market-ke")
    new_market = next(item for item in updated if item["attribute"] == "market:NG")
    assert old_market["active"] is False
    assert new_market["active"] is True
