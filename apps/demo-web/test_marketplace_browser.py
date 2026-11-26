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


    def test_mobile_and_tablet_layouts_have_no_horizontal_overflow(self):
        for width in (320, 360, 393, 430, 768, 1024):
            with self.subTest(width=width):
                self.page.set_viewport_size({"width": width, "height": 900})
                self.page.wait_for_timeout(50)
                metrics = self.page.evaluate("""() => ({
                    viewport: document.documentElement.clientWidth,
                    document: document.documentElement.scrollWidth,
                    body: document.body.scrollWidth,
                    buttonMinHeight: Math.min(...Array.from(document.querySelectorAll('.btn')).map(
                        node => node.getBoundingClientRect().height
                    ))
                })""")
                self.assertLessEqual(metrics["document"], width)
                self.assertLessEqual(metrics["body"], width)
                self.assertGreaterEqual(metrics["buttonMinHeight"], 44)

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

    def test_complementer_feedback_is_disabled_until_advice_and_explicit_consent(self):
        self.assertFalse(self.page.locator("#complementerLearningConsent").is_checked())
        self.assertTrue(self.page.locator("#complementerApproveBtn").is_disabled())
        self.assertTrue(self.page.locator("#complementerRejectBtn").is_disabled())
        self.assertIn("withdraw this consent in Wardrobe", self.page.locator("body").inner_text())
        self.assertIn("raw look description is not stored", self.page.locator("body").inner_text())

    def test_try_on_and_checkout_are_not_misrepresented_as_live(self):
        try_on = self.page.locator('.card button[data-action="tryon"]').first
        self.assertTrue(try_on.is_disabled())
        self.page.locator('.card button[data-action="bag"]').first.click()
        self.page.locator("#cartBtn").click()
        self.assertTrue(self.page.get_by_role("dialog").get_by_role("button", name="Checkout unavailable").is_disabled())


    def _open_live_marketplace(self, cart_status=503, image_urls=None):
        page = self.browser.new_page()
        page.add_init_script("""
            // Set bootstrap first: this script may run for the initial opaque about:blank document.
            window.CIRVANNA_MARKETPLACE_CONFIG = Object.freeze({publicOffersBase:"/api/commerce"});
            window.__marketplaceSessionReady = null;
            window.addEventListener("cirvanna:session-ready", event => {
                window.__marketplaceSessionReady = event.detail || null;
            });
            try {
                localStorage.setItem("cirvanna-marketplace-saved", JSON.stringify([{product_id:"demo-saved"}]));
                localStorage.setItem("cirvanna-marketplace-bag", JSON.stringify([{product_id:"demo-bag",quantity:1}]));
            } catch (_) {}
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
            "image_urls": image_urls if image_urls is not None else [],
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
        page.route("**/auth/session", lambda route: route.fulfill(
            status=200, content_type="application/json",
            body='{"authenticated":true,"user":{"id":"browser-test-customer"}}',
            headers={"Cache-Control":"no-store"}
        ))
        page.route("**/auth/logout", lambda route: route.fulfill(
            status=204, headers={"Cache-Control":"no-store"}
        ))
        page.goto(f"{self.base_url}/marketplace.html", wait_until="domcontentloaded")
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


    def test_logout_invalidates_inflight_marketplace_response(self):
        page = self._open_live_marketplace(cart_status=200)
        try:
            self.assertEqual(page.locator(".card").count(), 1)
            self.assertEqual(page.locator("#cartCount").inner_text(), "1")
            page.evaluate("""() => {
                const originalFetch = window.fetch.bind(window);
                window.__resolveOldMarketplaceRequest = null;
                window.fetch = (input, init = {}) => {
                    const headers = new Headers(init.headers || {});
                    const url = String(input);
                    if (headers.get("Authorization") === "Bearer server-cookie-session" && url.includes("/marketplace/offers")) {
                        return new Promise(resolve => { window.__resolveOldMarketplaceRequest = () => resolve(new Response(JSON.stringify({
                            items: [{catalog_product_id:"old-account-product",variant_id:"old-account-variant",product_name:"Stale old-account product",merchant_name:"Old Merchant",price_minor:999,currency:"KES"}],
                            total:1,display_authority:"CaTaCaCi/CAL",withheld_candidate_count:0
                        }), {status:200,headers:{"Content-Type":"application/json"}})); });
                    }
                    return originalFetch(input, init);
                };
            }""")
            page.locator("#query").fill("old account refresh")
            page.locator("#query").press("Enter")
            page.wait_for_function("typeof window.__resolveOldMarketplaceRequest === 'function'")
            page.locator("#settingsBtn").click()
            page.locator("[data-auth-logout]").click()
            page.wait_for_function("document.querySelector('#status').textContent.includes('signed out')")
            self.assertEqual(page.locator("#cartCount").inner_text(), "0")
            self.assertEqual(page.locator("#savedCount").inner_text(), "0")
            page.evaluate("window.__resolveOldMarketplaceRequest()")
            page.wait_for_timeout(100)
            self.assertEqual(page.locator(".card").count(), 0)
            self.assertNotIn("Stale old-account product", page.locator("body").inner_text())
        finally:
            page.close()


    def test_live_marketplace_never_renders_unapproved_external_media_urls(self):
        page = self._open_live_marketplace(
            cart_status=503,
            image_urls=["https://cdn.example.test/unapproved-person-photo.jpg"],
        )
        try:
            self.assertEqual(page.locator(".card").count(), 1)
            self.assertEqual(page.locator(".card img").count(), 0)
            self.assertEqual(page.locator(".card .placeholder").count(), 1)
            rendered_media = page.locator(".card").evaluate(
                "(node) => node.querySelector('img, video, source')?.outerHTML || null"
            )
            self.assertIsNone(rendered_media)
        finally:
            page.close()

    def test_account_connection_never_asks_for_direct_service_urls_or_pasted_tokens_by_default(self):
        self.page.locator("#settingsBtn").click()
        self.assertEqual(self.page.locator("#commerceBase").count(), 0)
        self.assertEqual(self.page.locator("#apiBase").count(), 0)
        self.assertEqual(self.page.locator("#apiToken").count(), 0)
        self.assertEqual(self.page.locator("#commerceToken").count(), 0)
        dialog = self.page.get_by_role("dialog")
        self.assertIn("Sign in securely", dialog.inner_text())
        self.assertIn("Continue with Google", dialog.inner_text())
        self.assertIn("Continue with Apple", dialog.inner_text())
        self.assertIn("Continue with Microsoft", dialog.inner_text())
        self.assertIn("Email me a sign-in link", dialog.inner_text())
        self.assertNotIn("pasted access tokens", dialog.inner_text())


if __name__ == "__main__":
    unittest.main()
