from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import main


@pytest.fixture(autouse=True)
def reset_worker_state():
    main._ESTIMATOR = None
    main._LOAD_ERROR = None
    main._configured.cache_clear()
    yield
    main._ESTIMATOR = None
    main._LOAD_ERROR = None
    main._configured.cache_clear()


def _manifested_artifacts(tmp_path: Path, monkeypatch) -> tuple[str, str]:
    model_id = main.DEFAULT_MODEL_ID
    revision = "a" * 40
    files = {
        "model.ckpt": b"checkpoint-fixture",
        "model_config.yaml": b"MODEL: {}\n",
        "assets/mhr_model.pt": b"mhr-fixture",
    }
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    hashes = {relative: hashlib.sha256(content).hexdigest() for relative, content in files.items()}
    release = main._release_digest(model_id, revision, main.PINNED_SAM3D_BODY_SOURCE_COMMIT, hashes)
    manifest = {
        "schema_version": 1,
        "model_id": model_id,
        "model_revision": revision,
        "source_commit": main.PINNED_SAM3D_BODY_SOURCE_COMMIT,
        "files": hashes,
        "model_release_sha256": release,
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv("TWIN_GENERATION_WORKER_TOKEN", "t" * 48)
    monkeypatch.setenv("SAM3D_BODY_SOURCE_REF", main.PINNED_SAM3D_BODY_SOURCE_COMMIT)
    monkeypatch.setenv("SAM3D_BODY_LICENSE_ACCEPTED", "true")
    monkeypatch.setenv("SAM3D_BODY_LICENSE_EVIDENCE_ID", "LEGAL-APPROVAL-TEST-001")
    monkeypatch.setenv("SAM3D_BODY_MODEL_ID", model_id)
    monkeypatch.setenv("SAM3D_BODY_MODEL_REVISION", revision)
    monkeypatch.setenv("SAM3D_BODY_MODEL_RELEASE_SHA256", release)
    monkeypatch.setenv("SAM3D_BODY_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setattr(main, "_gpu_status", lambda: (True, "ready"))
    main._configured.cache_clear()
    return revision, release


def _png_bytes(size: tuple[int, int] = (640, 960)) -> bytes:
    image = Image.new("RGB", size, (128, 128, 128))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_health_is_liveness_only():
    response = TestClient(main.app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_fails_closed_without_license_evidence(monkeypatch):
    monkeypatch.setenv("TWIN_GENERATION_WORKER_TOKEN", "t" * 48)
    monkeypatch.setenv("SAM3D_BODY_SOURCE_REF", main.PINNED_SAM3D_BODY_SOURCE_COMMIT)
    monkeypatch.setenv("SAM3D_BODY_LICENSE_ACCEPTED", "true")
    monkeypatch.delenv("SAM3D_BODY_LICENSE_EVIDENCE_ID", raising=False)
    main._configured.cache_clear()
    ready, reason = main._configured()
    assert ready is False
    assert reason == "model_license_evidence_missing"


def test_artifact_manifest_and_release_digest_are_verified(tmp_path, monkeypatch):
    _manifested_artifacts(tmp_path, monkeypatch)
    assert main._configured() == (True, "ready")


def test_artifact_manifest_rejects_modified_model_file(tmp_path, monkeypatch):
    _manifested_artifacts(tmp_path, monkeypatch)
    (tmp_path / "model.ckpt").write_bytes(b"tampered-checkpoint")
    main._configured.cache_clear()
    ready, reason = main._configured()
    assert ready is False
    assert reason == "artifact_file_digest_mismatch"


def test_glb_serializer_exports_geometry_without_texture(tmp_path):
    size = 40
    vertices = []
    for y in range(size):
        for x in range(size):
            z = 0.1 * np.sin(x / 5) * np.cos(y / 5)
            vertices.append([x / size, y / size, z])
    faces = []
    for y in range(size - 1):
        for x in range(size - 1):
            a = y * size + x
            b = a + 1
            c = a + size
            d = c + 1
            faces.extend([[a, b, c], [b, d, c]])
    glb, vertex_count, face_count = main._build_glb(
        vertices, faces, [0.0, 0.0, 0.0]
    )
    assert glb.startswith(b"glTF")
    assert vertex_count == size * size
    assert face_count == 2 * (size - 1) * (size - 1)


def test_glb_serializer_rejects_non_finite_vertices():
    vertices = np.zeros((1100, 3), dtype=np.float32)
    vertices[0, 0] = np.nan
    faces = np.tile(np.array([[0, 1, 2]]), (1100, 1))
    with pytest.raises(ValueError, match="non-finite"):
        main._build_glb(vertices, faces, [0, 0, 0])


def test_reconstruct_requires_internal_auth():
    client = TestClient(main.app)
    response = client.post(
        "/internal/v1/reconstruct",
        data={
            "source_asset_id": "asset-001",
            "consent_id": "consent-001",
            "single_person_confirmed": "true",
        },
        files={"image": ("person.png", _png_bytes(), "image/png")},
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "INTERNAL_AUTH_REQUIRED"


def test_reconstruct_requires_single_person_confirmation(monkeypatch):
    monkeypatch.setenv("TWIN_GENERATION_WORKER_TOKEN", "t" * 48)
    client = TestClient(main.app)
    response = client.post(
        "/internal/v1/reconstruct",
        headers={"Authorization": f"Bearer {'t' * 48}"},
        data={
            "source_asset_id": "asset-001",
            "consent_id": "consent-001",
            "single_person_confirmed": "false",
        },
        files={"image": ("person.png", _png_bytes(), "image/png")},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "SINGLE_PERSON_CONFIRMATION_REQUIRED"


def test_reconstruction_response_is_never_claimed_calibrated_or_registry_eligible(
    tmp_path, monkeypatch
):
    revision, release = _manifested_artifacts(tmp_path, monkeypatch)
    monkeypatch.setattr(main, "_configured", lambda: (True, "ready"))
    monkeypatch.setattr(main, "_load_estimator", lambda: object())
    monkeypatch.setattr(
        main,
        "_reconstruct",
        lambda _image: (b"glTF-fixture", 12000, 22000),
    )
    monkeypatch.setenv("TWIN_GENERATION_WORKER_TOKEN", "t" * 48)
    monkeypatch.setattr(main, "_ESTIMATOR", None)
    client = TestClient(main.app)
    response = client.post(
        "/internal/v1/reconstruct",
        headers={"Authorization": f"Bearer {'t' * 48}"},
        data={
            "source_asset_id": "asset-001",
            "consent_id": "consent-001",
            "single_person_confirmed": "true",
        },
        files={"image": ("person.png", _png_bytes(), "image/png")},
    )
    assert response.status_code == 200
    assert response.content == b"glTF-fixture"
    assert response.headers["x-twin-model-revision"] == revision
    assert response.headers["x-twin-model-release-sha256"] == release
    assert response.headers["x-twin-measurement-status"] == "not_calibrated"
    assert response.headers["x-twin-registry-eligible"] == "false"
    assert response.headers["cache-control"] == "no-store, private"
