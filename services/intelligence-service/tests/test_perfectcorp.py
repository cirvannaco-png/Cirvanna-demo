from __future__ import annotations

import json

import pytest

from app import perfectcorp


class FakeResponse:
    def __init__(self, payload=None, status_code=200, headers=None):
        self.payload = payload or {}
        self.status_code = status_code
        self.headers = headers or {"content-type": "application/json"}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, *args, **kwargs):
        self.calls = []
        self.upload_url = "https://yce-us.s3-accelerate.amazonaws.com/private/one-time-signed"
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return None
    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if url.endswith("/s2s/v2.0/file"):
            return FakeResponse({"status": 200, "data": {"files": [{
                "file_id": "opaque-file-id",
                "requests": [{"method": "PUT", "url": self.upload_url,
                              "headers": {"Content-Type": "image/jpeg", "Content-Length": "10"}}],
            }]}})
        if url.endswith("/s2s/v2.1/task/skin-analysis"):
            return FakeResponse({"status": 200, "data": {"task_id": "task/with+reserved"}})
        if url.endswith("/s2s/v2.1/task/skin-analysis/task%2Fwith%2Breserved"):
            return FakeResponse({"status": 200, "data": {
                "task_status": "success",
                "results": {"output": [
                    {"type": "pore", "ui_score": 72, "raw_score": 65.5, "mask_urls": ["https://private/image.png"]},
                    {"type": "texture", "ui_score": 66, "raw_score": 62.0, "mask_urls": ["https://private/mask.png"]},
                ]},
            }})
        if url.endswith("/s2s/v2.0/task/delete"):
            return FakeResponse({"status": 200})
        raise AssertionError(f"unexpected API request {method} {url}")
    def put(self, url, **kwargs):
        self.calls.append(("PUT", url, kwargs))
        return FakeResponse({}, headers={"content-type": "application/xml"})


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("CIL_PERFECTCORP_ENABLED", "true")
    monkeypatch.setenv("CIL_PERFECTCORP_DPA_APPROVED", "true")
    monkeypatch.setenv("CIL_PERFECTCORP_RETENTION_POLICY_REF", "DPA-RETENTION-SCHEDULE-001")
    monkeypatch.setenv("CIL_PERFECTCORP_API_TOKEN", "perfectcorp-test-token")
    monkeypatch.setenv("CIL_PERFECTCORP_LICENCE_ID", "partner-licence-001")
    monkeypatch.setenv("CIL_PERFECTCORP_TERMS_URL", "https://partner.example/terms")
    monkeypatch.setenv("CIL_PERFECTCORP_API_BASE_URL", "https://yce-api-01.makeupar.com")


def test_perfectcorp_is_disabled_without_explicit_operator_approval(monkeypatch):
    for key in (
        "CIL_PERFECTCORP_ENABLED", "CIL_PERFECTCORP_DPA_APPROVED",
        "CIL_PERFECTCORP_RETENTION_POLICY_REF", "CIL_PERFECTCORP_API_TOKEN",
        "CIL_PERFECTCORP_LICENCE_ID", "CIL_PERFECTCORP_TERMS_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(perfectcorp.PerfectCorpNotConfigured):
        perfectcorp._settings()


def test_perfectcorp_uploads_then_creates_async_task_with_no_api_secret_on_presigned_put(monkeypatch, configured):
    client = FakeClient()
    monkeypatch.setattr(perfectcorp.httpx, "Client", lambda *a, **k: client)
    result = perfectcorp.start_skin_analysis(
        image=b"jpeg-bytes",
        file_name="photo.jpg",
        content_type="image/jpeg",
        actions=["hd_pore", "hd_texture", "hd_age_spot", "hd_skin_type"],
        mode="hd",
    )
    assert result["task_id"] == "task/with+reserved"
    assert result["status"] == "running"
    file_call = next(c for c in client.calls if c[1].endswith("/s2s/v2.0/file"))
    assert file_call[2]["json"]["files"][0]["file_size"] == len(b"jpeg-bytes")
    upload_call = next(c for c in client.calls if c[0] == "PUT")
    assert "Authorization" not in upload_call[2]["headers"]
    task_call = next(c for c in client.calls if c[1].endswith("/s2s/v2.1/task/skin-analysis"))
    assert task_call[2]["json"] == {
        "src_file_id": "opaque-file-id",
        "dst_actions": ["hd_pore", "hd_texture", "hd_age_spot", "hd_skin_type"],
        "format": "json",
    }


def test_perfectcorp_rejects_unapproved_presigned_upload_host(monkeypatch, configured):
    client = FakeClient()
    client.upload_url = "https://attacker.example/steal"
    monkeypatch.setattr(perfectcorp.httpx, "Client", lambda *a, **k: client)
    with pytest.raises(perfectcorp.PerfectCorpRequestError):
        perfectcorp.start_skin_analysis(
            image=b"jpeg-bytes", file_name="photo.jpg", content_type="image/jpeg",
            actions=["pore"], mode="sd",
        )
    assert not any(method == "PUT" for method, _, _ in client.calls)


def test_perfectcorp_mode_actions_are_not_mixed(monkeypatch, configured):
    with pytest.raises(ValueError):
        perfectcorp.start_skin_analysis(
            image=b"jpeg-bytes", file_name="photo.jpg", content_type="image/jpeg",
            actions=["pore", "hd_pore"], mode="sd",
        )


def test_perfectcorp_poll_strips_masks_and_only_returns_score_fields(monkeypatch, configured):
    client = FakeClient()
    monkeypatch.setattr(perfectcorp.httpx, "Client", lambda *a, **k: client)
    result = perfectcorp.get_skin_analysis_status(task_id="task/with+reserved")
    assert result["status"] == "success"
    assert result["metrics"] == [
        {"type": "pore", "ui_score": 72, "raw_score": 65.5},
        {"type": "texture", "ui_score": 66, "raw_score": 62.0},
    ]
    assert "mask_urls" not in json.dumps(result)
    assert "private/image" not in json.dumps(result)


def test_perfectcorp_delete_endpoint_calls_documented_task_delete(monkeypatch, configured):
    client = FakeClient()
    monkeypatch.setattr(perfectcorp.httpx, "Client", lambda *a, **k: client)
    assert perfectcorp.delete_task(task_id="task-1") is True
    assert any(
        method == "POST" and url.endswith("/s2s/v2.0/task/delete")
        and kwargs["json"] == {"task_id": "task-1"}
        for method, url, kwargs in client.calls
    )


def test_perfectcorp_hd_age_spot_and_skin_type_use_documented_action_names(configured):
    assert "hd_age_spot" in perfectcorp.ALLOWED_ACTIONS["hd"]
    assert "hd_skin_type" in perfectcorp.ALLOWED_ACTIONS["hd"]
    assert "hd_spot" not in perfectcorp.ALLOWED_ACTIONS["hd"]
