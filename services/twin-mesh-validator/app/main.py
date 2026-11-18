from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
import struct
import uuid
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.responses import JSONResponse

SERVICE = "cirvanna-twin-mesh-validator"
GLB_CONTENT_TYPE = "model/gltf-binary"
MAX_GLB_BYTES = 100 * 1024 * 1024
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_VERTICES_PER_ACCESSOR = 100_000
MAX_TRIANGLES = 250_000
MAX_PRIMITIVES = 256
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
MODEL_REVISION = re.compile(r"^[0-9a-f]{40}$")
OPAQUE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{2,159}$")

bearer = HTTPBearer(auto_error=False)
app = FastAPI(title="Cirvanna Twin Mesh Validator", version="0.1.0")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PreflightRequest(StrictModel):
    subject_id: str = Field(min_length=3, max_length=128)
    twin_id: str = Field(min_length=8, max_length=128)
    consent_id: str = Field(min_length=8, max_length=160)
    consent_version: str = Field(min_length=1, max_length=80)
    artifact_asset_id: str = Field(min_length=36, max_length=36)
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_image_asset_ids: list[str] = Field(min_length=1, max_length=6)
    model_id: str = Field(min_length=2, max_length=80)
    model_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    model_release_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("subject_id", "twin_id", "consent_id", "model_id")
    @classmethod
    def validate_opaque_ids(cls, value: str) -> str:
        value = value.strip()
        if (
            not OPAQUE_ID.fullmatch(value)
            or "://" in value
            or "/" in value
            or "\\" in value
        ):
            raise ValueError("Expected an opaque internal identifier.")
        return value

    @field_validator("artifact_asset_id")
    @classmethod
    def validate_artifact_uuid(cls, value: str) -> str:
        try:
            return str(uuid.UUID(value))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("Expected an Asset Service UUID.") from exc

    @field_validator("source_image_asset_ids")
    @classmethod
    def validate_source_uuids(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            try:
                normalized.append(str(uuid.UUID(value)))
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError("Source image IDs must be Asset Service UUIDs.") from exc
        if len(normalized) != len(set(normalized)):
            raise ValueError("Source image IDs must be unique.")
        return normalized

    @field_validator("artifact_sha256", "model_release_sha256")
    @classmethod
    def validate_digests(cls, value: str) -> str:
        value = value.lower()
        if not HEX_SHA256.fullmatch(value):
            raise ValueError("Expected a lowercase SHA-256 digest.")
        return value


class MeshFormatError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _configured_pair(base_name: str, token_name: str) -> tuple[str, str]:
    base = os.getenv(base_name, "").strip().rstrip("/")
    token = os.getenv(token_name, "").strip()
    if not base or len(token.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "VALIDATOR_DEPENDENCY_NOT_CONFIGURED"})
    if not base.startswith("https://") and not (
        os.getenv("ALLOW_INSECURE_INTERNAL_HTTP", "").lower() == "true"
        and base.startswith("http://")
    ):
        raise HTTPException(503, detail={"code": "VALIDATOR_DEPENDENCY_MUST_USE_HTTPS"})
    return base, token


def require_internal_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = os.getenv("TWIN_MESH_VALIDATOR_API_TOKEN", "").strip()
    if len(expected.encode("utf-8")) < 32:
        raise HTTPException(503, detail={"code": "VALIDATOR_API_TOKEN_NOT_CONFIGURED"})
    supplied = credentials.credentials if credentials else ""
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(401, detail={"code": "UNAUTHORIZED"})


def _verify_consent_response(payload: Any, request: PreflightRequest) -> None:
    required = {"image_processing", "body_measurements", "virtual_twin_storage"}
    if not isinstance(payload, dict):
        raise HTTPException(502, detail={"code": "CONSENT_RESPONSE_INVALID"})
    granted = payload.get("granted_scopes")
    valid = (
        payload.get("verified") is True
        and payload.get("active") is True
        and payload.get("subject_id") == request.subject_id
        and payload.get("consent_id") == request.consent_id
        and payload.get("consent_version") == request.consent_version
        and payload.get("resource_id") == request.twin_id
        and isinstance(granted, list)
        and all(isinstance(scope, str) for scope in granted)
        and required.issubset(set(granted))
    )
    if not valid:
        raise HTTPException(403, detail={"code": "TWIN_RESOURCE_CONSENT_NOT_VERIFIED"})


async def verify_resource_bound_consent(request: PreflightRequest) -> None:
    base, token = _configured_pair("CONSENT_API_URL", "CONSENT_API_TOKEN")
    body = {
        "subject_id": request.subject_id,
        "consent_id": request.consent_id,
        "consent_version": request.consent_version,
        "required_scopes": ["image_processing", "body_measurements", "virtual_twin_storage"],
        "resource_id": request.twin_id,
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=4.0)) as client:
            response = await client.post(
                f"{base}/internal/v1/consents/verify",
                json=body,
                headers={"Authorization": f"Bearer {token}", "Cache-Control": "no-store"},
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(504, detail={"code": "CONSENT_PROVIDER_TIMEOUT"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "CONSENT_PROVIDER_UNAVAILABLE"}) from exc

    if response.status_code in (401, 403, 404):
        raise HTTPException(403, detail={"code": "TWIN_RESOURCE_CONSENT_NOT_VERIFIED"})
    if response.status_code >= 500:
        raise HTTPException(503, detail={"code": "CONSENT_PROVIDER_UNAVAILABLE"})
    if response.status_code != 200:
        raise HTTPException(502, detail={"code": "CONSENT_RESPONSE_INVALID"})
    try:
        _verify_consent_response(response.json(), request)
    except ValueError as exc:
        raise HTTPException(502, detail={"code": "CONSENT_RESPONSE_INVALID"}) from exc


async def load_private_mesh_asset(request: PreflightRequest) -> tuple[bytes, str]:
    base, token = _configured_pair("ASSET_SERVICE_URL", "ASSET_SERVICE_TOKEN")
    params = {
        "subject_id": request.subject_id,
        "purpose": "twin_representation",
        "parent_id": request.twin_id,
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(35.0, connect=5.0)) as client:
            async with client.stream(
                "GET",
                f"{base}/internal/v1/assets/{request.artifact_asset_id}/content",
                params=params,
                headers={"Authorization": f"Bearer {token}", "Cache-Control": "no-store"},
            ) as response:
                if response.status_code == 404:
                    raise HTTPException(404, detail={"code": "ASSET_NOT_FOUND_OR_NOT_AUTHORIZED"})
                if response.status_code >= 500:
                    raise HTTPException(503, detail={"code": "ASSET_SERVICE_UNAVAILABLE"})
                if response.status_code != 200:
                    raise HTTPException(502, detail={"code": "ASSET_READ_FAILED"})
                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                content_length = response.headers.get("content-length")
                if content_length:
                    try:
                        if int(content_length) > MAX_GLB_BYTES:
                            raise HTTPException(413, detail={"code": "GLB_SIZE_LIMIT_EXCEEDED"})
                    except ValueError as exc:
                        raise HTTPException(502, detail={"code": "ASSET_CONTENT_LENGTH_INVALID"}) from exc
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_GLB_BYTES:
                        raise HTTPException(413, detail={"code": "GLB_SIZE_LIMIT_EXCEEDED"})
                return bytes(data), content_type
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(504, detail={"code": "ASSET_SERVICE_TIMEOUT"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail={"code": "ASSET_SERVICE_UNAVAILABLE"}) from exc


def _parse_glb(data: bytes) -> tuple[dict[str, Any], bytes]:
    if not isinstance(data, bytes) or len(data) < 20 or len(data) > MAX_GLB_BYTES:
        raise MeshFormatError("GLB_SIZE_OR_HEADER_INVALID")
    magic, version, total_length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2 or total_length != len(data):
        raise MeshFormatError("GLB_HEADER_INVALID")

    cursor = 12
    chunks: list[tuple[int, bytes]] = []
    while cursor < len(data):
        if cursor + 8 > len(data):
            raise MeshFormatError("GLB_CHUNK_HEADER_TRUNCATED")
        chunk_length, chunk_type = struct.unpack_from("<II", data, cursor)
        cursor += 8
        if chunk_length % 4 != 0 or chunk_length <= 0 or cursor + chunk_length > len(data):
            raise MeshFormatError("GLB_CHUNK_BOUNDS_INVALID")
        chunks.append((chunk_type, data[cursor:cursor + chunk_length]))
        cursor += chunk_length
        if len(chunks) > 2:
            raise MeshFormatError("GLB_UNSUPPORTED_CHUNK_LAYOUT")

    if cursor != len(data) or len(chunks) != 2:
        raise MeshFormatError("GLB_JSON_AND_BINARY_CHUNKS_REQUIRED")
    if chunks[0][0] != 0x4E4F534A or chunks[1][0] != 0x004E4942:
        raise MeshFormatError("GLB_CHUNK_ORDER_INVALID")
    if len(chunks[0][1]) > MAX_JSON_BYTES:
        raise MeshFormatError("GLB_JSON_LIMIT_EXCEEDED")
    try:
        document = json.loads(chunks[0][1].rstrip(b" \t\r\n\x00").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise MeshFormatError("GLB_JSON_INVALID") from exc
    if not isinstance(document, dict) or not isinstance(document.get("asset"), dict):
        raise MeshFormatError("GLB_DOCUMENT_INVALID")
    if document["asset"].get("version") != "2.0":
        raise MeshFormatError("GLB_VERSION_UNSUPPORTED")
    binary = chunks[1][1]
    buffers = document.get("buffers")
    if not isinstance(buffers, list) or len(buffers) != 1 or not isinstance(buffers[0], dict):
        raise MeshFormatError("GLB_BUFFER_LAYOUT_UNSUPPORTED")
    buffer_declared = buffers[0].get("byteLength")
    if "uri" in buffers[0]:
        raise MeshFormatError("GLB_EXTERNAL_BUFFER_URI_FORBIDDEN")
    if (
        not isinstance(buffer_declared, int)
        or buffer_declared <= 0
        or buffer_declared > len(binary)
        or len(binary) - buffer_declared > 3
    ):
        raise MeshFormatError("GLB_BUFFER_BOUNDS_INVALID")
    return document, binary[:buffer_declared]


def _check_embedded_media_policy(document: dict[str, Any], binary: bytes) -> None:
    forbidden_keys = {"uri", "extras", "extensions", "extensionsUsed", "extensionsRequired"}
    image_keys = {"images", "textures"}

    def walk(value: Any, depth: int = 0) -> None:
        if depth > 64:
            raise MeshFormatError("GLB_JSON_DEPTH_EXCEEDED")
        if isinstance(value, dict):
            for key, child in value.items():
                if key in forbidden_keys and child not in (None, {}, []):
                    raise MeshFormatError("GLB_CUSTOM_OR_EXTERNAL_PAYLOAD_FORBIDDEN")
                if key in image_keys and child not in (None, []):
                    raise MeshFormatError("GLB_IMAGE_RESOURCE_FORBIDDEN")
                walk(child, depth + 1)
        elif isinstance(value, list):
            for child in value:
                walk(child, depth + 1)
        elif isinstance(value, str):
            if value.lower().startswith("data:"):
                raise MeshFormatError("GLB_DATA_URI_FORBIDDEN")

    walk(document)

    signatures = (
        b"\x89PNG\r\n\x1a\n",
        b"\xff\xd8\xff",
        b"GIF87a",
        b"GIF89a",
    )
    if any(signature in binary for signature in signatures):
        raise MeshFormatError("GLB_EMBEDDED_IMAGE_SIGNATURE_DETECTED")
    for offset in range(max(0, len(binary) - 11)):
        if binary[offset:offset + 4] == b"RIFF" and binary[offset + 8:offset + 12] == b"WEBP":
            raise MeshFormatError("GLB_EMBEDDED_IMAGE_SIGNATURE_DETECTED")


def _view_layout(
    document: dict[str, Any],
    binary: bytes,
    accessor: dict[str, Any],
    *,
    expected_component_type: int,
    expected_type: str,
    max_count: int,
) -> tuple[int, int, int, int, int]:
    if "sparse" in accessor:
        raise MeshFormatError("GLB_SPARSE_ACCESSORS_UNSUPPORTED")
    if accessor.get("componentType") != expected_component_type or accessor.get("type") != expected_type:
        raise MeshFormatError("GLB_ACCESSOR_FORMAT_INVALID")
    count = accessor.get("count")
    view_index = accessor.get("bufferView")
    if type(count) is not int or count <= 0 or count > max_count:
        raise MeshFormatError("GLB_ACCESSOR_COUNT_INVALID")
    views = document.get("bufferViews")
    if (
        not isinstance(views, list)
        or not isinstance(view_index, int)
        or view_index < 0
        or view_index >= len(views)
    ):
        raise MeshFormatError("GLB_BUFFER_VIEW_INVALID")
    view = views[view_index]
    if not isinstance(view, dict) or view.get("buffer", 0) != 0:
        raise MeshFormatError("GLB_BUFFER_VIEW_INVALID")
    view_offset = view.get("byteOffset", 0)
    view_length = view.get("byteLength")
    accessor_offset = accessor.get("byteOffset", 0)
    if (
        type(view_offset) is not int or type(view_length) is not int
        or type(accessor_offset) is not int or min(view_offset, view_length, accessor_offset) < 0
    ):
        raise MeshFormatError("GLB_BUFFER_VIEW_BOUNDS_INVALID")
    if view_offset + view_length > len(binary):
        raise MeshFormatError("GLB_BUFFER_VIEW_BOUNDS_INVALID")

    component_size = 4 if expected_component_type == 5126 else (
        1 if expected_component_type == 5121 else 2 if expected_component_type == 5123 else 4
    )
    element_size = component_size * (3 if expected_type == "VEC3" else 1)
    stride = view.get("byteStride", element_size)
    if (
        not isinstance(stride, int)
        or stride < element_size
        or stride > 252
        or stride % component_size != 0
        or (view_offset + accessor_offset) % component_size != 0
    ):
        raise MeshFormatError("GLB_ACCESSOR_STRIDE_INVALID")
    end = view_offset + accessor_offset + (count - 1) * stride + element_size
    if end > view_offset + view_length or end > len(binary):
        raise MeshFormatError("GLB_ACCESSOR_BOUNDS_INVALID")
    return view_offset + accessor_offset, stride, count, component_size, element_size


def _read_positions(
    document: dict[str, Any],
    binary: bytes,
    accessor_index: int,
    cache: dict[int, list[tuple[float, float, float]]],
) -> list[tuple[float, float, float]]:
    if accessor_index in cache:
        return cache[accessor_index]
    accessors = document.get("accessors")
    if (
        type(accessor_index) is not int
        or not isinstance(accessors, list)
        or accessor_index < 0
        or accessor_index >= len(accessors)
        or not isinstance(accessors[accessor_index], dict)
    ):
        raise MeshFormatError("GLB_POSITION_ACCESSOR_INVALID")
    accessor = accessors[accessor_index]
    start, stride, count, _, _ = _view_layout(
        document, binary, accessor,
        expected_component_type=5126, expected_type="VEC3",
        max_count=MAX_VERTICES_PER_ACCESSOR,
    )
    points: list[tuple[float, float, float]] = []
    minima = [math.inf, math.inf, math.inf]
    maxima = [-math.inf, -math.inf, -math.inf]
    for index in range(count):
        point = struct.unpack_from("<fff", binary, start + index * stride)
        if not all(math.isfinite(value) for value in point):
            raise MeshFormatError("GLB_NONFINITE_POSITION")
        if any(abs(value) > 10_000 for value in point):
            raise MeshFormatError("GLB_POSITION_MAGNITUDE_OUT_OF_BOUNDS")
        for axis, value in enumerate(point):
            minima[axis] = min(minima[axis], value)
            maxima[axis] = max(maxima[axis], value)
        points.append((point[0], point[1], point[2]))
    if any(maxima[axis] - minima[axis] <= 1e-8 for axis in range(3)):
        raise MeshFormatError("GLB_GEOMETRY_NOT_THREE_DIMENSIONAL")
    cache[accessor_index] = points
    return points


def _read_indices(
    document: dict[str, Any],
    binary: bytes,
    accessor_index: int,
    vertex_count: int,
) -> list[int]:
    accessors = document.get("accessors")
    if (
        type(accessor_index) is not int
        or not isinstance(accessors, list)
        or accessor_index < 0
        or accessor_index >= len(accessors)
        or not isinstance(accessors[accessor_index], dict)
    ):
        raise MeshFormatError("GLB_INDEX_ACCESSOR_INVALID")
    accessor = accessors[accessor_index]
    component_type = accessor.get("componentType")
    format_map = {5121: ("<B", 1), 5123: ("<H", 2), 5125: ("<I", 4)}
    if component_type not in format_map:
        raise MeshFormatError("GLB_INDEX_COMPONENT_TYPE_INVALID")
    fmt, size = format_map[component_type]
    start, stride, count, _, element_size = _view_layout(
        document, binary, accessor,
        expected_component_type=component_type, expected_type="SCALAR",
        max_count=MAX_TRIANGLES * 3,
    )
    if element_size != size:
        raise MeshFormatError("GLB_INDEX_FORMAT_INVALID")
    values: list[int] = []
    for index in range(count):
        value = struct.unpack_from(fmt, binary, start + index * stride)[0]
        if value >= vertex_count:
            raise MeshFormatError("GLB_INDEX_OUT_OF_RANGE")
        values.append(value)
    return values


def _validate_primitive_topology(
    points: list[tuple[float, float, float]],
    indices: list[int],
) -> tuple[int, int]:
    if len(indices) < 3 or len(indices) % 3 != 0:
        raise MeshFormatError("GLB_TRIANGLE_INDEX_COUNT_INVALID")
    edge_counts: dict[tuple[int, int], int] = {}
    degenerate = 0
    for offset in range(0, len(indices), 3):
        a, b, c = indices[offset:offset + 3]
        if a == b or b == c or a == c:
            degenerate += 1
            continue
        pa, pb, pc = points[a], points[b], points[c]
        ab = (pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2])
        ac = (pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2])
        cross = (
            ab[1] * ac[2] - ab[2] * ac[1],
            ab[2] * ac[0] - ab[0] * ac[2],
            ab[0] * ac[1] - ab[1] * ac[0],
        )
        area_squared = sum(value * value for value in cross)
        if not math.isfinite(area_squared) or area_squared <= 1e-24:
            degenerate += 1
        for left, right in ((a, b), (b, c), (c, a)):
            edge = (left, right) if left < right else (right, left)
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
    nonmanifold = sum(1 for count in edge_counts.values() if count > 2)
    boundary = sum(1 for count in edge_counts.values() if count == 1)
    if degenerate:
        raise MeshFormatError("GLB_DEGENERATE_TRIANGLES_DETECTED")
    if nonmanifold:
        raise MeshFormatError("GLB_NONMANIFOLD_EDGES_DETECTED")
    return boundary, nonmanifold


def inspect_glb(data: bytes) -> dict[str, Any]:
    document, binary = _parse_glb(data)
    _check_embedded_media_policy(document, binary)
    meshes = document.get("meshes")
    if not isinstance(meshes, list) or not meshes or len(meshes) > MAX_PRIMITIVES:
        raise MeshFormatError("GLB_MESH_LIST_INVALID")

    position_cache: dict[int, list[tuple[float, float, float]]] = {}
    vertex_count = 0
    triangle_count = 0
    boundary_edges = 0
    primitive_count = 0

    for mesh in meshes:
        if not isinstance(mesh, dict):
            raise MeshFormatError("GLB_MESH_INVALID")
        primitives = mesh.get("primitives")
        if not isinstance(primitives, list) or not primitives:
            raise MeshFormatError("GLB_PRIMITIVES_INVALID")
        for primitive in primitives:
            primitive_count += 1
            if primitive_count > MAX_PRIMITIVES or not isinstance(primitive, dict):
                raise MeshFormatError("GLB_PRIMITIVE_LIMIT_OR_SHAPE_INVALID")
            if primitive.get("mode", 4) != 4 or primitive.get("targets"):
                raise MeshFormatError("GLB_TRIANGLE_PROFILE_REQUIRED")
            attributes = primitive.get("attributes")
            if not isinstance(attributes, dict) or type(attributes.get("POSITION")) is not int:
                raise MeshFormatError("GLB_POSITION_ATTRIBUTE_REQUIRED")
            points = _read_positions(document, binary, attributes["POSITION"], position_cache)
            indices = (
                _read_indices(document, binary, primitive["indices"], len(points))
                if "indices" in primitive else list(range(len(points)))
            )
            boundary, _ = _validate_primitive_topology(points, indices)
            vertex_count += len(points)
            triangle_count += len(indices) // 3
            boundary_edges += boundary
            if triangle_count > MAX_TRIANGLES:
                raise MeshFormatError("GLB_TRIANGLE_LIMIT_EXCEEDED")

    if vertex_count == 0 or triangle_count == 0:
        raise MeshFormatError("GLB_EMPTY_GEOMETRY")
    return {
        "vertex_count": vertex_count,
        "triangle_count": triangle_count,
        "primitive_count": primitive_count,
        "boundary_edge_count": boundary_edges,
        "nonmanifold_edge_count": 0,
        "geometry_finite": True,
        "topology_valid": True,
        "glb_embedded_image_resources_absent": True,
    }


async def preflight_mesh(request: PreflightRequest) -> dict[str, Any]:
    await verify_resource_bound_consent(request)
    raw, content_type = await load_private_mesh_asset(request)
    if content_type != GLB_CONTENT_TYPE:
        raise HTTPException(415, detail={"code": "TWIN_MESH_CONTENT_TYPE_INVALID"})
    digest = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(digest, request.artifact_sha256):
        raise HTTPException(409, detail={"code": "TWIN_MESH_DIGEST_MISMATCH"})
    try:
        geometry = inspect_glb(raw)
    except MeshFormatError as exc:
        raise HTTPException(422, detail={"code": exc.code}) from exc

    return {
        "status": "structural_preflight_passed_not_registry_eligible",
        "registry_eligible": False,
        "receipt_issued": False,
        "artifact_sha256": digest,
        "model_provenance": {
            "model_id": request.model_id,
            "model_revision": request.model_revision,
            "model_release_sha256": request.model_release_sha256,
        },
        "checks": {
            "artifact_sha256_matches": True,
            "glb_container_valid": True,
            "geometry_finite": geometry["geometry_finite"],
            "topology_valid": geometry["topology_valid"],
            "glb_embedded_image_resources_absent": geometry["glb_embedded_image_resources_absent"],
            "body_coverage_valid": None,
            "scale_within_bounds": None,
            "source_photo_not_embedded": None,
            "privacy_scan_passed": None,
        },
        "geometry_summary": {
            "vertex_count": geometry["vertex_count"],
            "triangle_count": geometry["triangle_count"],
            "primitive_count": geometry["primitive_count"],
            "boundary_edge_count": geometry["boundary_edge_count"],
            "nonmanifold_edge_count": geometry["nonmanifold_edge_count"],
        },
        "unverified_gates": [
            "BODY_COVERAGE_REQUIRES_INDEPENDENT_BODY_SURFACE_EVIDENCE",
            "SCALE_REQUIRES_CAPTURE_CALIBRATION_AND_REFERENCE_MEASUREMENT",
            "SOURCE_PHOTO_NON_EMBEDDING_REQUIRES_SOURCE_ASSET_COMPARISON",
            "PRIVACY_REQUIRES_INDEPENDENT_SENSITIVE_DATA_SCAN",
        ],
        "attestation": "NOT_ISSUED",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "alive", "service": SERVICE}


@app.get("/ready")
def ready() -> dict[str, Any]:
    configured = (
        len(os.getenv("TWIN_MESH_VALIDATOR_API_TOKEN", "").encode("utf-8")) >= 32
        and len(os.getenv("CONSENT_API_TOKEN", "").encode("utf-8")) >= 32
        and bool(os.getenv("CONSENT_API_URL", "").strip())
        and len(os.getenv("ASSET_SERVICE_TOKEN", "").encode("utf-8")) >= 32
        and bool(os.getenv("ASSET_SERVICE_URL", "").strip())
    )
    if not configured:
        raise HTTPException(503, detail={"code": "VALIDATOR_DEPENDENCIES_NOT_CONFIGURED"})
    return {"status": "ready", "service": SERVICE, "registry_attestation": False}


@app.post(
    "/internal/v1/preflight",
    dependencies=[Depends(require_internal_token)],
)
async def preflight(request: PreflightRequest):
    result = await preflight_mesh(request)
    return JSONResponse(
        result,
        headers={"Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff"},
    )
