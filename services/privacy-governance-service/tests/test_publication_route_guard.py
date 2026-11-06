from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SERVICES = ROOT / "services"
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "api_route"}
PUBLIC_MEDIA_SURFACE_SEGMENTS = {
    "asset", "assets", "image", "images", "photo", "photos", "media",
    "avatar", "avatars", "publish", "publication", "restore", "share",
    "shared", "shared-link", "shared-links", "syndicate", "syndication",
    "community", "feed",
}


def _route_path(call: ast.Call) -> str | None:
    if not call.args or not isinstance(call.args[0], ast.Constant):
        return None
    value = call.args[0].value
    return value if isinstance(value, str) else None


def _route_definitions(source: str, path: Path) -> list[tuple[str, str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    tree = ast.parse(source, filename=str(path))
    routes = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            if decorator.func.attr not in HTTP_METHODS:
                continue
            route = _route_path(decorator)
            if route is not None:
                routes.append((decorator.func.attr.upper(), route, node))
    return routes


def test_no_public_media_publication_or_restore_route_bypasses_privacy_gate():
    """Any future public media surface must explicitly wire the masking attestation gate."""
    unguarded = []
    scanned = 0
    for source_path in sorted(SERVICES.glob("*/app/*.py")):
        source = source_path.read_text(encoding="utf-8")
        scanned += 1
        for method, route, handler in _route_definitions(source, source_path):
            if route.startswith("/internal/"):
                continue
            segments = {part.casefold() for part in route.split("/") if part}
            if not segments.intersection(PUBLIC_MEDIA_SURFACE_SEGMENTS):
                continue
            # This dependency name is the integration contract every publisher must import.
            guarded = any(
                isinstance(item, ast.Name) and item.id == "require_publication_gate"
                for item in ast.walk(handler)
            )
            if not guarded:
                unguarded.append(f"{source_path.relative_to(ROOT)}:{handler.name} {method} {route}")
    assert scanned > 0
    assert not unguarded, (
        "Public media routes must call require_publication_gate before returning or "
        "making an asset public. Unguarded routes: " + ", ".join(unguarded)
    )


def test_privacy_governance_publication_gate_is_present_and_asset_bound():
    path = SERVICES / "privacy-governance-service" / "app" / "main.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    gate_functions = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "evaluate_asset_publication"
    ]
    assert len(gate_functions) == 1
    gate_source = ast.get_source_segment(source, gate_functions[0]) or ""
    assert '"/internal/v1/privacy/assets/publication/evaluate"' in source
    assert "VISION_PRIVACY_ATTESTATION" in gate_source
    assert "all_detected_faces_masked" in gate_source
    assert "unmasked_face_count" in gate_source
    assert "masking_applied_before_publication" in gate_source
    assert "face_recognition_performed" in gate_source
    assert "face_embeddings_created" in gate_source
    assert "age_estimation_performed" in gate_source
    assert "masking_model_sha256" in gate_source
