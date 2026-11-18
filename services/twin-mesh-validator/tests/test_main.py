from __future__ import annotations

import hashlib
import json
import struct

import pytest
from fastapi.testclient import TestClient

from app import main

TOKEN = "twin-mesh-validator-test-token-at-least-32-bytes"
SUBJECT = "subject-0001"
TWIN = "twin-00001"
CONSENT = "consent-00001"
MESH_ID = "00000000-0000-4000-8000-000000000001"
SOURCE_ID = "00000000-0000-4000-8000-000000000002"
MODEL_ID = "cirvanna-body-model"
MODEL_REVISION = "a" * 40
MODEL_RELEASE = "b" * 64


def tetrahedron_glb(document_override=None, positions_override=None, indices_override=None):
    positions = positions_override or [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    ]
    indices = indices_override or [0, 2, 1, 0, 1, 3, 1, 2, 3, 2, 0, 3]
    binary = b"".join(struct.pack("<fff", *point) for point in positions)
    position_bytes = len(binary)
    binary += struct.pack("<" + "H" * len(indices), *indices)
    document = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": position_bytes},
            {"buffer": 0, "byteOffset": position_bytes, "byteLength": len(indices) * 2},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": len(positions), "type": "VEC3"},
            {"bufferView": 1, "componentType": 5123, "count": len(indices), "type": "SCALAR"},
        ],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "mode": 4}]}],
    }
    if document_override:
        document.update(document_override)
    json_chunk = json.dumps(document, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * ((4 - len(json_chunk) % 4) % 4)
    binary += b"\x00" * ((4 - len(binary) % 4) % 4)
    total = 12 + 8 + len(json_chunk) + 8 + len(binary)
    return (
        struct.pack("<4sII", b"glTF", 2, total)
        + struct.pack("<II", len(json_chunk), 0x4E4F534A) + json_chunk
        + struct.pack("<II", len(binary), 0x004E4942) + binary
    )


def request_body(mesh_bytes=None):
    data = tetrahedron_glb() if mesh_bytes is None else mesh_bytes
    return {
        "subject_id": SUBJECT,
        "twin_id": TWIN,
        "consent_id": CONSENT,
        "consent_version": "consent-v1",
        "artifact_asset_id": MESH_ID,
        "artifact_sha256": hashlib.sha256(data).hexdigest(),
        "source_image_asset_ids": [SOURCE_ID],
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "model_release_sha256": MODEL_RELEASE,
    }


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("TWIN_MESH_VALIDATOR_API_TOKEN", TOKEN)

    async def consent_ok(request):
        assert request.subject_id == SUBJECT
        assert request.consent_id == CONSENT
        assert request.twin_id == TWIN

    async def asset_ok(request):
        return tetrahedron_glb(), main.GLB_CONTENT_TYPE

    monkeypatch.setattr(main, "verify_resource_bound_consent", consent_ok)
    monkeypatch.setattr(main, "load_private_mesh_asset", asset_ok)
    return TestClient(main.app)


def test_glb_preflight_reads_geometry_but_never_attests(client):
    response = client.post(
        "/internal/v1/preflight",
        json=request_body(),
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["registry_eligible"] is False
    assert body["receipt_issued"] is False
    assert body["checks"]["artifact_sha256_matches"] is True
    assert body["checks"]["geometry_finite"] is True
    assert body["checks"]["topology_valid"] is True
    assert body["checks"]["body_coverage_valid"] is None
    assert body["checks"]["scale_within_bounds"] is None
    assert body["checks"]["source_photo_not_embedded"] is None
    assert body["attestation"] == "NOT_ISSUED"
    assert body["geometry_summary"]["vertex_count"] == 4
    assert body["geometry_summary"]["triangle_count"] == 4
    assert "BODY_COVERAGE_REQUIRES_INDEPENDENT_BODY_SURFACE_EVIDENCE" in body["unverified_gates"]



def test_consent_receipt_requires_exact_subject_resource_version_and_scopes():
    request = main.PreflightRequest.model_validate(request_body())
    valid = {
        "verified": True,
        "active": True,
        "subject_id": SUBJECT,
        "consent_id": CONSENT,
        "resource_id": TWIN,
        "consent_version": "consent-v1",
        "granted_scopes": ["image_processing", "body_measurements", "virtual_twin_storage"],
    }
    main._verify_consent_response(valid, request)

    for field, bad_value in (
        ("subject_id", "another-subject"),
        ("resource_id", "another-twin"),
        ("consent_version", "old-version"),
        ("active", False),
        ("verified", False),
        ("granted_scopes", ["image_processing", "body_measurements"]),
        ("granted_scopes", ["image_processing", "body_measurements", 7]),
    ):
        candidate = {**valid, field: bad_value}
        with pytest.raises(main.HTTPException):
            main._verify_consent_response(candidate, request)

def test_internal_endpoint_requires_service_authentication(client):
    response = client.post("/internal/v1/preflight", json=request_body())
    assert response.status_code == 401


def test_digest_mismatch_fails_before_mesh_parsing(client, monkeypatch):
    async def asset_ok(request):
        return b"not a GLB", main.GLB_CONTENT_TYPE

    monkeypatch.setattr(main, "load_private_mesh_asset", asset_ok)
    payload = request_body()
    response = client.post(
        "/internal/v1/preflight",
        json=payload,
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "TWIN_MESH_DIGEST_MISMATCH"


def test_source_and_mesh_ids_must_be_asset_service_uuids():
    payload = request_body()
    payload["source_image_asset_ids"] = ["provider://image/123"]
    with pytest.raises(ValueError):
        main.PreflightRequest.model_validate(payload)


def test_rejects_nonfinite_positions():
    points = [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, float("inf")),
    ]
    with pytest.raises(main.MeshFormatError, match="GLB_NONFINITE_POSITION"):
        main.inspect_glb(tetrahedron_glb(positions_override=points))


def test_rejects_degenerate_triangles():
    indices = [0, 0, 1, 0, 1, 3, 1, 2, 3, 2, 0, 3]
    with pytest.raises(main.MeshFormatError, match="GLB_DEGENERATE_TRIANGLES_DETECTED"):
        main.inspect_glb(tetrahedron_glb(indices_override=indices))


def test_rejects_out_of_range_indices():
    indices = [0, 2, 9, 0, 1, 3, 1, 2, 3, 2, 0, 3]
    with pytest.raises(main.MeshFormatError, match="GLB_INDEX_OUT_OF_RANGE"):
        main.inspect_glb(tetrahedron_glb(indices_override=indices))


def test_rejects_glb_embedded_images_and_custom_extras():
    with pytest.raises(main.MeshFormatError, match="GLB_IMAGE_RESOURCE_FORBIDDEN"):
        main.inspect_glb(tetrahedron_glb({"images": [{"bufferView": 0}]}))
    with pytest.raises(main.MeshFormatError, match="GLB_CUSTOM_OR_EXTERNAL_PAYLOAD_FORBIDDEN"):
        main.inspect_glb(tetrahedron_glb({"extras": {"source_photo": "hidden"}}))


def test_rejects_external_buffer_and_invalid_container():
    with pytest.raises(main.MeshFormatError):
        main.inspect_glb(b"not a glb")
    with pytest.raises(main.MeshFormatError, match="GLB_EXTERNAL_BUFFER_URI_FORBIDDEN"):
        main.inspect_glb(tetrahedron_glb({"buffers": [{"byteLength": 1, "uri": "https://example.invalid/mesh.bin"}]}))


def test_request_rejects_duplicate_source_asset_ids():
    payload = request_body()
    payload["source_image_asset_ids"] = [SOURCE_ID, SOURCE_ID]
    with pytest.raises(ValueError):
        main.PreflightRequest.model_validate(payload)
