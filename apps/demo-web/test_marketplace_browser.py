"""Headless browser smoke tests for the marketplace demo UI."""
from pathlib import Path
import json
from threading import Thread
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import unittest

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = ROOT / "apps" / "demo-web"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


class MarketplaceBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = lambda *args, **kwargs: QuietHandler(*args, directory=str(WEB_ROOT), **kwargs)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def setUp(self):
        self.playwright = sync_playwright().start()
        self.addCleanup(self.playwright.stop)
        self.browser = self.playwright.chromium.launch()
        self.addCleanup(self.browser.close)
        self.page = self.browser.new_page()
        self.page.goto(f"{self.base_url}/marketplace.html", wait_until="domcontentloaded")
        self.page.wait_for_function("document.querySelector('#status').textContent.includes('DEMO MODE')", timeout=5000)

    def test_demo_search_save_and_bag_are_interactive(self):
        self.assertEqual(self.page.locator(".card").count(), 6)
        self.page.locator("#query").fill("serum")
        self.page.locator("#query").press("Enter")
        self.assertEqual(self.page.locator(".card").count(), 1)
        self.page.locator('.card button[data-action="save"]').click()
        self.assertEqual(self.page.locator("#savedCount").inner_text(), "1")
        self.page.locator("#savedBtn").click()
        self.page.get_by_role("dialog").get_by_text("Radiant Skin Serum").wait_for()
        self.page.get_by_role("button", name="Close").click()
        self.page.locator('.card button[data-action="bag"]').click()
        self.assertEqual(self.page.locator("#cartCount").inner_text(), "1")
        self.page.locator("#cartBtn").click()
        self.page.get_by_role("dialog").get_by_text("Checkout unavailable").wait_for()
        self.assertIn("No stock is reserved and no order is created.", self.page.get_by_role("dialog").inner_text())

    def test_try_on_and_checkout_are_not_misrepresented_as_live(self):
        try_on = self.page.locator('.card button[data-action="tryon"]').first
        self.assertTrue(try_on.is_disabled())
        self.page.locator('.card button[data-action="bag"]').first.click()
        self.page.locator("#cartBtn").click()
        self.assertTrue(self.page.get_by_role("dialog").get_by_role("button", name="Checkout unavailable").is_disabled())


    def _open_live_marketplace(self, cart_status=503):
        page = self.browser.new_page()
        page.add_init_script("""
            localStorage.setItem("cirvanna-marketplace-saved", JSON.stringify([{product_id:"demo-saved"}]));
            localStorage.setItem("cirvanna-marketplace-bag", JSON.stringify([{product_id:"demo-bag",quantity:1}]));
            window.CIRVANNA_MARKETPLACE_CONFIG = Object.freeze({publicOffersBase:"/api/commerce"});
        """)
        cart_payload = {
            "cart_id": "test-cart",
            "version": 3,
            "items": [{
                "variant_id": "123e4567-e89b-12d3-a456-426614174000",
                "catalog_product_id": "223e4567-e89b-12d3-a456-426614174000",
                "product_name": "Live governed serum",
                "merchant_name": "Test Merchant",
                "quantity": 1,
                "price_minor": 1200,
                "currency": "KES",
                "line_total_minor": 1200,
                "available_stock": 4,
                "availability": "in_stock"
            }],
            "item_count": 1,
            "single_currency": True
        }
        product = {
            "catalog_product_id": "223e4567-e89b-12d3-a456-426614174000",
            "variant_id": "123e4567-e89b-12d3-a456-426614174000",
            "product_name": "Live governed serum",
            "merchant_name": "Test Merchant",
            "price_minor": 1200,
            "currency": "KES",
            "category": "Beauty",
            "image_urls": [],
            "available_stock": 4,
            "options": {}
        }

        def api(route):
            path = route.request.url.split("?", 1)[0]
            if path.endswith("/marketplace/offers"):
                route.fulfill(status=200, content_type="application/json", body=json.dumps({
                    "items": [product], "total": 1, "display_authority": "CaTaCaCi/CAL",
                    "withheld_candidate_count": 0
                }))
            elif path.endswith("/saved-products"):
                route.fulfill(status=200, content_type="application/json", body='{"items":[],"total":0}')
            elif path.endswith("/cart"):
                if cart_status == 200:
                    route.fulfill(status=200, content_type="application/json", body=json.dumps(cart_payload))
                else:
                    route.fulfill(status=cart_status, content_type="application/json", body=json.dumps({
                        "detail": {"code": "CAL_CANDIDATE_PURCHASE_REAUTH_REQUIRED"}
                    }))
            else:
                route.fulfill(status=404, content_type="application/json", body='{"detail":"not found"}')

        page.route("**/api/commerce/**", api)
        page.goto(f"{self.base_url}/marketplace.html", wait_until="domcontentloaded")
        page.wait_for_function("document.querySelector('#status').textContent.includes('Sign in')")
        page.locator("#settingsBtn").click()
        page.locator("#commerceToken").fill("signed-user-session-token")
        page.get_by_role("button", name="Connect account-backed marketplace").click()
        page.wait_for_function("document.querySelector('#status').textContent.includes('CAL-GOVERNED LIVE COMMERCE')")
        return page

    def test_live_bff_cart_gate_off_keeps_purchase_controls_locked_and_demo_state_out(self):
        page = self._open_live_marketplace(cart_status=503)
        try:
            self.assertEqual(page.locator("#cartCount").inner_text(), "0")
            self.assertEqual(page.locator("#savedCount").inner_text(), "0")
            bag_button = page.locator('.card button:has-text("Bag — paused")')
            self.assertEqual(bag_button.count(), 1)
            self.assertTrue(bag_button.is_disabled())
            page.locator("#cartBtn").click()
            dialog = page.get_by_role("dialog")
            self.assertEqual(dialog.get_by_role("button", name="Continue to secure checkout").count(), 0)
            self.assertEqual(dialog.get_by_role("button", name="Checkout paused — CAL authorization unavailable").count(), 0)
            self.assertIn("operator gate", dialog.inner_text())
        finally:
            page.close()

    def test_live_bff_cart_success_loads_account_cart_and_unlocks_controls(self):
        page = self._open_live_marketplace(cart_status=200)
        try:
            self.assertEqual(page.locator("#cartCount").inner_text(), "1")
            self.assertEqual(page.locator("#savedCount").inner_text(), "0")
            bag_button = page.locator('.card button[data-action="bag"]')
            self.assertEqual(bag_button.count(), 1)
            self.assertFalse(bag_button.is_disabled())
            page.locator("#cartBtn").click()
            dialog = page.get_by_role("dialog")
            self.assertTrue(dialog.get_by_role("button", name="Continue to secure checkout").is_enabled())
            self.assertIn("Every cart view, change and checkout is reauthorized by CAL.", dialog.inner_text())
        finally:
            page.close()

    def test_account_connection_never_asks_for_direct_service_urls(self):
        self.page.locator("#settingsBtn").click()
        self.assertEqual(self.page.locator("#commerceBase").count(), 0)
        self.assertEqual(self.page.locator("#apiBase").count(), 0)
        self.assertEqual(self.page.locator("#apiToken").count(), 0)
        self.assertEqual(self.page.locator("#commerceToken").count(), 1)
        self.assertIn("same-origin Cirvanna Marketplace BFF", self.page.get_by_role("dialog").inner_text())


if __name__ == "__main__":
    unittest.main()
