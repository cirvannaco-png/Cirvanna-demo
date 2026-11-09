import json
from datetime import datetime, timezone

import pytest

from app import learning


class FakeResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code
        self.content = json.dumps(data).encode()

    def json(self):
        return self._data


class FakeClient:
    def __init__(self, **kwargs):
        self.requests = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def request(self, method, url, *, headers=None, params=None, json=None):
        self.requests.append((method, url, params, json))
        if method == "GET" and url.endswith("/v1/tal/consents/user-1"):
            return FakeResponse([{
                "receipt_id": "receipt-style-001",
                "scope": "style_learning",
                "granted": True,
                "revoked_at": None,
            }])
        if method == "POST" and url.endswith("/v1/tal/events"):
            return FakeResponse({"event_id": json["event_id"], "status": "recorded"})
        if method == "GET" and url.endswith("/v1/preferences"):
            return FakeResponse({"preferences": []})
        if method == "POST" and url.endswith("/v1/preferences"):
            return FakeResponse({"preference": json})
        if method == "POST" and url.endswith("/v1/preferences/wardrobe-test/rejections"):
            return FakeResponse({"rejection_count": 1, "hard_veto": False})
        if method == "POST" and url.endswith("/rejections"):
            return FakeResponse({"rejection_count": 1, "hard_veto": False})
        raise AssertionError(f"Unexpected upstream request: {method} {url}")


def configure_learning(monkeypatch, fake_client):
    monkeypatch.setenv("IDENTITY_SERVICE_URL", "https://identity.example.test")
    monkeypatch.setenv("IDENTITY_SERVICE_TOKEN", "i" * 40)
    monkeypatch.setenv("NPL_SERVICE_URL", "https://npl.example.test")
    monkeypatch.setenv("NPL_SERVICE_TOKEN", "n" * 40)
    monkeypatch.setattr(learning.httpx, "Client", fake_client)


def deliver(signal, **overrides):
    payload = {
        "owner_user_id": "user-1",
        "item_id": "wardrobe-item-1",
        "item_version": 2,
        "display_name": "Blue cotton shirt",
        "category": "tops",
        "attributes": ["blue", "cotton"],
        "event_id": "feedback-event-1",
        "signal": signal,
        "target_type": "attribute" if signal in {"dislike", "avoid"} else None,
        "target_value": "blue" if signal in {"dislike", "avoid"} else None,
        "consent_receipt_id": "receipt-style-001",
        "observed_at": datetime.now(timezone.utc),
    }
    payload.update(overrides)
    return learning.deliver_learning_event(**payload)


def test_dislike_is_recorded_in_tal_and_npl_as_a_thresholded_rejection(monkeypatch):
    clients = []
    def factory(**kwargs):
        client = FakeClient(**kwargs)
        clients.append(client)
        return client
    configure_learning(monkeypatch, factory)
    result = deliver("dislike")
    requests = clients[0].requests
    preference_create = next(req for req in requests if req[0] == "POST" and req[1].endswith("/v1/preferences"))
    rejection = next(req for req in requests if req[0] == "POST" and req[1].endswith("/rejections"))
    assert preference_create[3]["source"] == "learned_rejection"
    assert preference_create[3]["rejection_threshold"] == 3
    assert rejection[3]["rejection_event_id"] == "feedback-event-1"
    assert result["tal_status"] == "recorded"
    assert result["npl"]["hard_veto"] is False


def test_user_declared_avoid_becomes_an_immediate_npl_hard_veto(monkeypatch):
    clients = []
    def factory(**kwargs):
        client = FakeClient(**kwargs)
        clients.append(client)
        return client
    configure_learning(monkeypatch, factory)
    result = deliver("avoid")
    requests = clients[0].requests
    preference_create = next(req for req in requests if req[0] == "POST" and req[1].endswith("/v1/preferences"))
    assert preference_create[3]["source"] == "user_declared"
    assert not any(req[1].endswith("/rejections") for req in requests)
    assert result["npl"]["hard_veto"] is True
    assert result["npl"]["source"] == "user_declared"


def test_positive_like_requires_active_consent_but_does_not_create_npl_preference(monkeypatch):
    clients = []
    def factory(**kwargs):
        client = FakeClient(**kwargs)
        clients.append(client)
        return client
    configure_learning(monkeypatch, factory)
    result = deliver("like", target_type=None, target_value=None)
    requests = clients[0].requests
    assert any(req[1].endswith("/v1/tal/events") for req in requests)
    assert not any("/v1/preferences" in req[1] for req in requests)
    assert result["positive_feedback_is_advisory"] is True
    assert result["npl"] is None


def test_missing_consent_blocks_tal_and_npl_writes(monkeypatch):
    class NoConsentClient(FakeClient):
        def request(self, method, url, *, headers=None, params=None, json=None):
            self.requests.append((method, url, params, json))
            if method == "GET" and url.endswith("/v1/tal/consents/user-1"):
                return FakeResponse([])
            raise AssertionError("No writes are allowed without active consent")
    clients = []
    def factory(**kwargs):
        client = NoConsentClient(**kwargs)
        clients.append(client)
        return client
    configure_learning(monkeypatch, factory)
    with pytest.raises(learning.LearningIntegrationError) as exc:
        deliver("dislike")
    assert exc.value.code == "ACTIVE_STYLE_LEARNING_CONSENT_REQUIRED"
    assert len(clients[0].requests) == 1
