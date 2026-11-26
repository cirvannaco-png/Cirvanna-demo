from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Any route matching these patterns is a shopper-facing product/discovery or
# purchase surface and must be explicitly classified below. This is a route
# inventory guard, not proof of deployed provider/CDN behavior.
BFF_SURFACES = {
    "/marketplace.html",
    "/api/vision/marketplace-search",
    "/api/vision/look-it",
    "/api/vision/click-it",
    "/api/vision/conversational-discovery",
    "/api/commerce/marketplace/offers",
    "/api/commerce/marketplace/compare",
    "/api/commerce/{path:path}",
    "/api/wardrobe/recommendations",
    "/api/wardrobe/daily-looks",
    "/api/wardrobe/pnelly/daily-looks",
}
COMMERCE_SURFACES = {
    "/marketplace/offers",
    "/marketplace/compare",
    "/saved-products",
    "/saved-products/{catalog_product_id}",
    "/cart",
    "/cart/items",
    "/cart/items/{variant_id}",
    "/checkout",
}
GATEWAY_SURFACES = {"/v1/discover"}

BFF_MARKER = re.compile(
    r"marketplace|marketplace-search|conversational-discovery|look-it|click-it|"
    r"recommendations|daily-looks",
    re.IGNORECASE,
)
COMMERCE_MARKER = re.compile(
    r"marketplace|saved-products|cart|checkout",
    re.IGNORECASE,
)
GATEWAY_MARKER = re.compile(r"/v1/discover", re.IGNORECASE)


def _route_functions(path: str) -> dict[str, str]:
    source = (ROOT / path).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=path)
    routes: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            if decorator.func.attr not in {"get", "post", "put", "patch", "delete", "api_route"}:
                continue
            if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
                continue
            route = decorator.args[0].value
            if isinstance(route, str):
                routes[route] = node.name
    return routes


def _function_source(path: str, function_name: str) -> str:
    source = (ROOT / path).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=path)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"Missing route handler {function_name} in {path}")


class CalShopperSurfaceInventoryTests(unittest.TestCase):
    def test_bff_product_and_purchase_surface_inventory_is_exhaustive(self):
        routes = _route_functions("services/marketplace-bff/app/main.py")
        observed = {path for path in routes if BFF_MARKER.search(path) or path == "/api/commerce/{path:path}"}
        self.assertEqual(observed, BFF_SURFACES, "A new or removed BFF shopper surface needs explicit CAL disposition.")

    def test_commerce_product_and_purchase_surface_inventory_is_exhaustive(self):
        routes = _route_functions("services/commerce-service/app/main.py")
        observed = {path for path in routes if COMMERCE_MARKER.search(path)}
        self.assertEqual(observed, COMMERCE_SURFACES, "A new or removed Commerce surface needs explicit CAL disposition.")

    def test_gateway_has_one_canonical_discovery_surface(self):
        routes = _route_functions("services/api-gateway/app/main.py")
        observed = {path for path in routes if GATEWAY_MARKER.search(path)}
        self.assertEqual(observed, GATEWAY_SURFACES)

    def test_marketplace_display_requires_candidate_bound_cal_show(self):
        source = _function_source("services/marketplace-bff/app/main.py", "public_offers")
        for required in (
            "_validate_cal_discovery_envelope",
            'decision.get("verdict") != "show"',
            'decision.get("may_display") is not True',
            'decision.get("product_id") != product_id',
            'decision.get("catalog_version") != catalog_version',
            'decision.get("cil_serving_status") != "eligible"',
            'Cache-Control": "no-store, private"',
        ):
            self.assertIn(required, source)

    def test_wardrobe_recommendations_require_candidate_bound_cal_show(self):
        source = _function_source("services/marketplace-bff/app/main.py", "wardrobe_recommendations")
        for required in (
            "_validate_cal_discovery_envelope",
            'decision.get("verdict") != "show"',
            'decision.get("may_display") is not True',
            'decision.get("product_id") != product_id',
            'decision.get("catalog_version") != catalog_version',
        ):
            self.assertIn(required, source)

    def test_pnelly_retrieval_is_not_a_display_authority(self):
        source = _function_source("services/marketplace-bff/app/main.py", "marketplace_description_search")
        self.assertIn('"display_authorized": False', source)
        self.assertIn('"decision_status": "PENDING_CAL"', source)
        self.assertNotIn('"displayable_products"', source)

    def test_click_it_and_unbound_comparison_remain_fail_closed(self):
        bff = (ROOT / "services/marketplace-bff/app/main.py").read_text(encoding="utf-8")
        click_it = _function_source("services/marketplace-bff/app/main.py", "marketplace_click_it")
        compare = _function_source("services/marketplace-bff/app/main.py", "compare_public_offers")
        self.assertIn("CLICK_IT_PRIVACY_PIPELINE_NOT_RELEASED", click_it)
        self.assertIn("CAL_AUTHORIZATION_REQUIRED", compare)
        click_tree = ast.parse(click_it)
        called_methods = {
            node.func.attr
            for node in ast.walk(click_tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        self.assertTrue({"form", "body", "stream"}.isdisjoint(called_methods))

    def test_purchase_proxy_requires_fresh_purchase_authorization(self):
        source = _function_source("services/marketplace-bff/app/main.py", "commerce_proxy")
        self.assertIn("_commerce_purchase_authorization_ready", source)
        self.assertIn("CAL_CANDIDATE_PURCHASE_REAUTH_REQUIRED", source)
        self.assertIn("is_purchase_path", source)

    def test_saved_product_mutations_and_listing_disclose_identifiers_only(self):
        source = (ROOT / "services/commerce-service/app/main.py").read_text(encoding="utf-8")
        save = _function_source("services/commerce-service/app/main.py", "save_product")
        listing = _function_source("services/commerce-service/app/main.py", "get_saved_products")
        self.assertIn('return {"catalog_product_id": pid, "saved": True}', save)
        self.assertIn('"catalog_product_id": r.catalog_product_id', listing)
        self.assertIn('"saved_at": r.created_at', listing)
        self.assertNotIn('"product_name"', save)
        self.assertNotIn('"product_name"', listing)


if __name__ == "__main__":
    unittest.main()
