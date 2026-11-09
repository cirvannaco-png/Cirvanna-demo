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

# These routes are media-adjacent but do not publish or deliver user photographs:
# private, consent-bound Look It ingestion is transient; Click It is hard-disabled;
# skincare routine sharing is a strict text-only resource. Exact route/function
# tuples are allowlisted here and separately covered by invariant tests below.
NON_PUBLICATION_ROUTE_EXCEPTIONS = {
    ("services/marketplace-bff/app/main.py", "POST", "/api/vision/look-it", "marketplace_look_it"),
    ("services/marketplace-bff/app/main.py", "POST", "/api/vision/click-it", "marketplace_click_it"),
    ("services/vision-intelligence/app/main.py", "POST", "/v1/search/image", "look_it_image_search"),
    ("services/vision-intelligence/app/main.py", "POST", "/v1/click-it/scan", "click_it_scan"),
    ("services/xari/app/main.py", "POST", "/v1/marketplace/search/image", "look_it_image_search"),
    ("services/skincare-routine-service/app/main.py", "POST", "/v1/routines/{routine_id}/share", "create_share"),
    ("services/skincare-routine-service/app/main.py", "GET", "/public/routines/{token}", "get_shared_routine"),
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
            # Inbound private processing and text-only share routes are not public
            # binary-media publication. Their exact implementations are guarded below.
            source_relative = source_path.relative_to(ROOT).as_posix()
            route_key = (source_relative, method, route, handler.name)
            if route_key in NON_PUBLICATION_ROUTE_EXCEPTIONS:
                continue
            # This dependency name is the integration contract every publisher must import.
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

def test_public_static_media_mount_is_fixed_to_repository_owned_portal_assets():
    """Static mounts are binary-delivery surfaces, not exempt from the privacy inventory."""
    bff_path = SERVICES / "marketplace-bff" / "app" / "main.py"
    source = bff_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(bff_path))

    # Inventory every StaticFiles mount in every service, not only the BFF
    # currently known to expose public portal assets.
    mounts = []
    for source_path in sorted(SERVICES.rglob("*.py")):
        relative_parts = source_path.relative_to(SERVICES).parts
        if {"tests", "migrations", "__pycache__"}.intersection(relative_parts):
            continue
        module = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(module):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "mount" or len(node.args) < 2:
                continue
            app_expression = node.args[1]
            uses_static_files = any(
                isinstance(item, ast.Name) and item.id == "StaticFiles"
                for item in ast.walk(app_expression)
            )
            if not uses_static_files:
                continue
            route = _route_path(node)
            uses_fixed_portal_directory = any(
                isinstance(item, ast.Name) and item.id == "PORTAL_ASSETS_DIR"
                for item in ast.walk(app_expression)
            )
            mounts.append((source_path.relative_to(ROOT).as_posix(), route, uses_fixed_portal_directory))

    assert mounts == [("services/marketplace-bff/app/main.py", "/assets", True)], (
        "Every public StaticFiles mount must be explicitly inventoried and limited "
        "to the one repository-owned portal assets directory."
    )

    assignments = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "PORTAL_ASSETS_DIR" for target in node.targets)
    ]
    assert len(assignments) == 1
    assert isinstance(assignments[0].value, ast.Name)
    assert assignments[0].value.id == "DEFAULT_PORTAL_ASSETS"
    assert "MARKETPLACE_ASSETS_DIR" not in source, (
        "A deployment variable must not redirect public static delivery to an upload, "
        "private-media, temporary or object-storage directory."
    )

    public_root = ROOT / "apps" / "demo-web" / "assets"
    assert public_root.is_dir()
    assert not public_root.is_symlink(), "The public static root itself must not be a symlink."
    assert public_root.resolve() == (ROOT / "apps" / "demo-web" / "assets").resolve()
    symlinks = [str(path.relative_to(ROOT)) for path in public_root.rglob("*") if path.is_symlink()]
    assert not symlinks, "Public static assets must not contain symlinks: " + ", ".join(symlinks)

    # Customer pages must not load arbitrary third-party image origins. Public media
    # can only be added later through an explicitly governed same-origin delivery path.
    assert "img-src 'self' data:" in source
    assert "img-src 'self' https:" not in source

def test_nonpublication_media_adjacent_routes_remain_narrow_and_explicit():
    """Allow only known private ingest or text-only sharing routes, never arbitrary routes."""
    expected = NON_PUBLICATION_ROUTE_EXCEPTIONS
    observed = set()
    route_handlers = {}

    for source_path in sorted(SERVICES.rglob("*.py")):
        relative_parts = source_path.relative_to(SERVICES).parts
        if {"tests", "migrations", "__pycache__"}.intersection(relative_parts):
            continue
        source = source_path.read_text(encoding="utf-8")
        source_relative = source_path.relative_to(ROOT).as_posix()
        for method, route, handler in _route_definitions(source, source_path):
            key = (source_relative, method, route, handler.name)
            if key in expected:
                observed.add(key)
                route_handlers[key] = (source, handler)

    assert observed == expected, (
        "Non-publication exceptions must remain exact and present. "
        f"Missing={sorted(expected - observed)} unexpected={sorted(observed - expected)}"
    )

    # BFF Look It is authenticated, purpose-bound, short-lived and cleans up both
    # the upload and consent. It returns no-store metadata, not a user image.
    look_it_key = ("services/marketplace-bff/app/main.py", "POST", "/api/vision/look-it", "marketplace_look_it")
    look_it_source, look_it_handler = route_handlers[look_it_key]
    look_it_body = ast.get_source_segment(look_it_source, look_it_handler) or ""
    for token in ("_verified_commerce_subject", "_record_look_it_consent", "_verify_look_it_bundle", "reference_image.read", "reference_image.close", "revoke"):
        assert token in look_it_body
    assert "_private_json_response({" in look_it_body
    assert '"Cache-Control": "no-store, private"' in look_it_source

    # Click It has no multipart parameters and rejects before parsing request bytes.
    click_it_key = ("services/marketplace-bff/app/main.py", "POST", "/api/vision/click-it", "marketplace_click_it")
    click_it_source, click_it_handler = route_handlers[click_it_key]
    click_it_body = ast.get_source_segment(click_it_source, click_it_handler) or ""
    assert "CLICK_IT_PRIVACY_PIPELINE_NOT_RELEASED" in click_it_body
    assert len(click_it_handler.args.args) == 1
    assert click_it_handler.args.args[0].arg == "request"
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "request"
        and node.func.attr in {"form", "body", "stream"}
        for node in ast.walk(click_it_handler)
    ), "Click It must not parse or read the incoming upload before privacy release."
    assert "503" in click_it_body

    # Internal Vision and PNELLY Look It routes remain transient and never return
    # product/offer candidate records; the user-facing wrapper emits counts only.
    vision_key = ("services/vision-intelligence/app/main.py", "POST", "/v1/search/image", "look_it_image_search")
    vision_source, vision_handler = route_handlers[vision_key]
    vision_body = ast.get_source_segment(vision_source, vision_handler) or ""
    assert "require_worker_auth" in vision_source
    assert "await image.close()" in vision_body
    assert '"image_persisted": False' in vision_body
    assert '"merchant_comparison"' in vision_body
    assert '"status": "pending_cal"' in vision_body
    assert '"results":' not in vision_body

    xari_key = ("services/xari/app/main.py", "POST", "/v1/marketplace/search/image", "look_it_image_search")
    xari_source, xari_handler = route_handlers[xari_key]
    xari_body = ast.get_source_segment(xari_source, xari_handler) or ""
    assert "_verify_look_it_consent" in xari_body
    assert "await image.close()" in xari_body
    assert '"display_authorized": False' in xari_body
    assert '"decision_status": "PENDING_CAL"' in xari_body
    assert '"Cache-Control": "no-store, private"' in xari_body

    # Public skincare sharing is a text-only routine token, not media delivery.
    # Strict request models and the fixed serializer prevent arbitrary image/asset fields.
    skin_key = ("services/skincare-routine-service/app/main.py", "GET", "/public/routines/{token}", "get_shared_routine")
    skin_source, skin_handler = route_handlers[skin_key]
    skin_tree = ast.parse(skin_source)
    routine_json = next(
        node for node in ast.walk(skin_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "routine_json"
    )
    serialized_keys = {
        node.value for node in ast.walk(routine_json)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    forbidden_media_terms = {"image", "images", "photo", "photos", "media", "asset", "asset_id", "image_url", "thumbnail"}
    assert not any(any(term in key.casefold() for term in forbidden_media_terms) for key in serialized_keys)
    shared_body = ast.get_source_segment(skin_source, skin_handler) or ""
    assert "routine_json(row, include_owner=False)" in shared_body
    assert '"shared_view": True' in shared_body

def test_binary_image_response_routes_are_private_owner_or_worker_scoped_and_no_store():
    """The only raw-image HTTP responses must be private service-to-service paths."""
    cases = [
        (
            "services/asset-service/app/main.py",
            "GET",
            "/internal/v1/assets/{asset_id}/content",
            "read_asset_content",
            "require_internal_token",
        ),
        (
            "services/virtual-try-on/model-worker/app/main.py",
            "POST",
            "/v1/render",
            "render",
            "require_worker_auth",
        ),
    ]

    for relative, method, route_path, handler_name, required_dependency in cases:
        source_path = ROOT / relative
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative)
        handler = next(
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == handler_name
        )
        route_decorator = None
        for decorator in handler.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            if decorator.func.attr != method.lower() or not decorator.args:
                continue
            if isinstance(decorator.args[0], ast.Constant) and decorator.args[0].value == route_path:
                route_decorator = decorator
                break
        assert route_decorator is not None, f"{relative} {method} {route_path} must remain explicitly inventoried"

        dependencies = next(
            (keyword.value for keyword in route_decorator.keywords if keyword.arg == "dependencies"),
            None,
        )
        assert isinstance(dependencies, ast.List)
        assert any(
            isinstance(item, ast.Call)
            and isinstance(item.func, ast.Name)
            and item.func.id == "Depends"
            and item.args
            and isinstance(item.args[0], ast.Name)
            and item.args[0].id == required_dependency
            for item in dependencies.elts
        ), f"{relative} must require {required_dependency}"

        body = ast.get_source_segment(source, handler) or ""
        assert '"Cache-Control": "no-store, private"' in source
        if handler_name == "read_asset_content":
            assert "_owned_asset(db, asset_id, subject_id, purpose, parent_id)" in body
            assert "hashlib.sha256(data).hexdigest() != row.sha256" in body
            assert '"X-Content-Type-Options": "nosniff"' in body
        else:
            assert "person_image.read" in body and "garment_image.read" in body
            assert 'media_type="image/png"' in body
            assert "put_object" not in body and "generate_presigned_url" not in body
