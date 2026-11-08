from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SERVICES = ROOT / "services"
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "api_route"}
PUBLIC_MEDIA_SURFACE_SEGMENTS = {
    "asset", "assets", "image", "images", "photo", "photos", "media",
    "avatar", "avatars", "thumbnail", "render", "publish", "publication",
    "restore", "share", "shared", "shared-link", "shared-links",
    "syndicate", "syndication", "community", "feed", "upload", "uploads",
    "file", "files", "gallery", "galleries", "public", "static", "cdn",
    "story", "stories", "post", "posts", "lookbook", "banner", "cover",
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
    for source_path in sorted(SERVICES.rglob("*.py")):
        relative_parts = source_path.relative_to(SERVICES).parts
        if {"tests", "migrations", "__pycache__"}.intersection(relative_parts):
            continue
        source = source_path.read_text(encoding="utf-8")
        scanned += 1
        for method, route, handler in _route_definitions(source, source_path):
            if route.startswith("/internal/") or method == "DELETE":
                # Deletion/removal endpoints reduce exposure; they do not publish an asset.
                continue
            segments = {part.casefold() for part in route.split("/") if part}
            handler_media_name = any(term in handler.name.casefold() for term in (
                "publish", "restore", "share", "syndicat", "upload",
                "serve_image", "serve_photo", "serve_media", "avatar",
                "gallery", "lookbook",
            ))
            if not segments.intersection(PUBLIC_MEDIA_SURFACE_SEGMENTS) and not handler_media_name:
                continue
            # This dependency name is the integration contract every publisher must import.
            source_relative = source_path.relative_to(ROOT).as_posix()
            private_vton_worker_response = (
                source_relative == "services/virtual-try-on/model-worker/app/main.py"
                and route == "/v1/render"
                and any(
                    isinstance(item, ast.Name) and item.id == "require_worker_auth"
                    for item in ast.walk(handler)
                )
                and '"input_persistence": False' in source
                and '"output_persistence": False' in source
                and '"Cache-Control": "no-store, private"' in source
            )
            if private_vton_worker_response:
                continue
            guarded = any(
                isinstance(item, ast.Name) and item.id == "require_publication_gate"
                for item in ast.walk(handler)
            )
            if not guarded:
                unguarded.append(f"{source_relative}:{handler.name} {method} {route}")
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



def test_private_vton_worker_image_response_is_authenticated_ephemeral_and_non_publishing():
    path = SERVICES / "virtual-try-on" / "model-worker" / "app" / "main.py"
    source = path.read_text(encoding="utf-8")
    routes = _route_definitions(source, path)
    render_routes = [item for item in routes if item[1] == "/v1/render"]
    assert len(render_routes) == 1
    _method, _route, handler = render_routes[0]
    assert any(
        isinstance(item, ast.Name) and item.id == "require_worker_auth"
        for item in ast.walk(handler)
    )
    assert '"input_persistence": False' in source
    assert '"output_persistence": False' in source
    assert '"Cache-Control": "no-store, private"' in source
