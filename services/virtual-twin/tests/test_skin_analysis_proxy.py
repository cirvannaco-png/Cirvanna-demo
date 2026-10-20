from __future__ import annotations

from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient

import app.main as twin_main

client = TestClient(twin_main.app)


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeAsyncClient:
    post_response = FakeResponse(200, {
        "status": "completed",
        "service": "cirvanna-dermalsight",
        "contract_version": "1",
        "model_version": "fixture-model",
        "score_semantics": "uncalibrated_model_score_not_a_probability_or_diagnosis",
        "attributes": [{"name": "texture_variation", "score": 0.6}],
        "disclaimer": "Not a medical diagnosis.",
    })
    get_response = FakeResponse(200, {"ready": True})
    post_error = None
    posted = None

    def __init__(self, *args, **kwargs):
        self.options = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, **kwargs):
        return self.get_response

    async def post(self, url, **kwargs):
        if self.post_error:
            raise self.post_error
        self.posted = {"url": url, **kwargs}
        type(self).posted = self.posted
        return self.post_response


def patch_http_client(monkeypatch, fake=FakeAsyncClient):
    monkeypatch.setattr(
        twin_main,
        "httpx",
        SimpleNamespace(
            AsyncClient=fake,
            Timeout=httpx.Timeout,
            HTTPError=httpx.HTTPError,
            TimeoutException=httpx.TimeoutException,
        ),
    )


def test_skin_analysis_requires_virtual_twin_authentication():
    response = client.post(
        "/skin-analysis",
        data={"consent": "true"},
        files={"image": ("capture.png", b"image", "image/png")},
    )
    assert response.status_code == 401


def test_skin_analysis_requires_explicit_consent(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", "test-only-token")
    response = client.post(
        "/skin-analysis",
        headers={"Authorization": "Bearer test-only-token"},
        data={"consent": "false"},
        files={"image": ("capture.png", b"image", "image/png")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "EXPLICIT_CONSENT_REQUIRED"


def test_skin_analysis_fails_closed_when_dermalsight_missing(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", "test-only-token")
    monkeypatch.delenv("DERMALSIGHT_API_URL", raising=False)
    monkeypatch.delenv("DERMALSIGHT_API_TOKEN", raising=False)
    response = client.post(
        "/skin-analysis",
        headers={"Authorization": "Bearer test-only-token"},
        data={"consent": "true"},
        files={"image": ("capture.png", b"image", "image/png")},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "DERMALSIGHT_NOT_CONFIGURED"


def test_skin_analysis_forwards_request_to_dermalsight(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", "virtual-twin-token")
    monkeypatch.setenv("DERMALSIGHT_API_URL", "https://dermalsight.internal")
    monkeypatch.setenv("DERMALSIGHT_API_TOKEN", "service-token")
    FakeAsyncClient.post_response = FakeResponse(200, {
        "status": "completed",
        "service": "cirvanna-dermalsight",
        "contract_version": "1",
        "model_version": "fixture-model",
        "score_semantics": "uncalibrated_model_score_not_a_probability_or_diagnosis",
        "attributes": [{"name": "texture_variation", "score": 0.6}],
        "disclaimer": "Not a medical diagnosis.",
    })
    FakeAsyncClient.post_error = None
    patch_http_client(monkeypatch)
    response = client.post(
        "/skin-analysis",
        headers={"Authorization": "Bearer virtual-twin-token"},
        data={"consent": "true"},
        files={"image": ("capture.png", b"image", "image/png")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["service"] == "cirvanna-dermalsight"
    assert response.headers["cache-control"] == "no-store"
    sent = FakeAsyncClient.posted
    assert sent["url"] == "https://dermalsight.internal/api/v1/analyze"
    assert sent["headers"]["Authorization"] == "Bearer service-token"
    assert sent["data"] == {"consent": "true"}
    assert sent["files"]["image"][1] == b"image"


def test_skin_analysis_sanitizes_upstream_unavailability(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", "virtual-twin-token")
    monkeypatch.setenv("DERMALSIGHT_API_URL", "https://dermalsight.internal")
    monkeypatch.setenv("DERMALSIGHT_API_TOKEN", "service-token")
    FakeAsyncClient.post_response = FakeResponse(503, {"detail": "sensitive internal failure"})
    FakeAsyncClient.post_error = None
    patch_http_client(monkeypatch)
    response = client.post(
        "/skin-analysis",
        headers={"Authorization": "Bearer virtual-twin-token"},
        data={"consent": "true"},
        files={"image": ("capture.png", b"image", "image/png")},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "DERMALSIGHT_UNAVAILABLE"
    assert "sensitive internal failure" not in response.text


def test_skin_analysis_translates_upstream_timeout(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", "virtual-twin-token")
    monkeypatch.setenv("DERMALSIGHT_API_URL", "https://dermalsight.internal")
    monkeypatch.setenv("DERMALSIGHT_API_TOKEN", "service-token")
    FakeAsyncClient.post_error = httpx.TimeoutException("internal timeout detail")
    patch_http_client(monkeypatch)
    response = client.post(
        "/skin-analysis",
        headers={"Authorization": "Bearer virtual-twin-token"},
        data={"consent": "true"},
        files={"image": ("capture.png", b"image", "image/png")},
    )
    FakeAsyncClient.post_error = None
    assert response.status_code == 504
    assert response.json()["detail"]["code"] == "DERMALSIGHT_TIMEOUT"


def test_capabilities_only_reports_skin_analysis_when_dermalsight_ready(monkeypatch):
    monkeypatch.setenv("DERMALSIGHT_API_URL", "http://dermalsight:8000")
    monkeypatch.setenv("DERMALSIGHT_API_TOKEN", "service-token")
    FakeAsyncClient.get_response = FakeResponse(200, {"ready": True})
    patch_http_client(monkeypatch)
    response = client.get("/capabilities")
    assert response.status_code == 200
    assert response.json()["skin_analysis"] is True

    FakeAsyncClient.get_response = FakeResponse(503, {"ready": False})
    response = client.get("/capabilities")
    assert response.json()["skin_analysis"] is False


def test_skin_analysis_rejects_unsupported_upload_type(monkeypatch):
    monkeypatch.setenv("VIRTUAL_TWIN_API_TOKEN", "test-only-token")
    response = client.post(
        "/skin-analysis",
        headers={"Authorization": "Bearer test-only-token"},
        data={"consent": "true"},
        files={"image": ("capture.bin", b"data", "application/octet-stream")},
    )
    assert response.status_code == 415
