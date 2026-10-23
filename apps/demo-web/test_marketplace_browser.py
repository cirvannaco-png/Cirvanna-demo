"""Headless browser tests for the CAL-only marketplace display boundary."""
import json
from pathlib import Path
from threading import Thread
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import unittest

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = ROOT / "apps" / "demo-web"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def offer_payload(candidate, *, display_authorized):
    return {
        "status": "complete",
        "items": [candidate],
        "candidates": [candidate] if display_authorized else [],
        "candidate_count": 1 if display_authorized else 0,
        "display_authorized": display_authorized,
        "decision_status": "SHOW" if display_authorized else "NO_SHOW",
        "governance_status": "CAL_ENFORCED" if display_authorized else "CAL_PARTIAL_FAIL_CLOSED",
        "total": 1,
        "offset": 0,
        "limit": 20,
    }


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
        self.payload = offer_payload(
            {
                "variant_id": "blocked-variant-1",
                "product_name": "SHOULD NEVER APPEAR — BLOCKED SAMPLE",
                "merchant_name": "Unapproved Sample",
                "display_authorized": True,
                "decision_status": "SHOW",
                "cal_decision": {"verdict": "SHOW", "may_display": True},
                "options": {"color": "blue"},
                "image_urls": [],
            },
            display_authorized=False,
        )

        def mock_offer_gateway(route):
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(self.payload),
            )

        self.page.add_init_script(
            'window.CIRVANNA_MARKETPLACE_CONFIG = Object.freeze({publicOffersBase:"/api/commerce"});'
        )
        self.page.route("**/api/commerce/marketplace/offers*", mock_offer_gateway)
        self.page.goto(f"{self.base_url}/marketplace.html", wait_until="domcontentloaded")
        self.page.wait_for_function(
            "document.querySelector('#status').textContent.includes('No candidates on this page')",
            timeout=5000,
        )

    def test_blocked_candidate_is_never_rendered_even_if_upstream_claims_show(self):
        self.assertEqual(self.page.locator(".card").count(), 0)
        self.assertNotIn("SHOULD NEVER APPEAR", self.page.locator("#products").inner_text())
        self.assertTrue(self.page.locator("#savedBtn").is_disabled())
        self.assertTrue(self.page.locator("#cartBtn").is_disabled())
        self.assertIn("BLOCK, REVIEW", self.page.locator("#status").inner_text())

    def test_only_exact_candidate_bound_cal_show_renders_a_product(self):
        self.payload = offer_payload(
            {
                "variant_id": "verified-variant-1",
                "product_id": "canonical-product-1",
                "product_name": "Verified Linen Shirt",
                "merchant_name": "Verified Merchant",
                "display_authorized": True,
                "decision_status": "SHOW",
                "cal_decision": {
                    "verdict": "SHOW",
                    "may_display": True,
                    "request_id": "fresh-request-id",
                    "policy_version": "test-policy",
                },
                "options": {"color": "natural"},
                "image_urls": [],
                "price_minor": 250000,
                "currency": "KES",
            },
            display_authorized=True,
        )
        self.page.reload(wait_until="domcontentloaded")
        self.page.get_by_text("Verified Linen Shirt").wait_for(timeout=5000)
        self.assertEqual(self.page.locator(".card").count(), 1)
        self.assertIn("CAL-GOVERNED MARKETPLACE", self.page.locator("#status").inner_text())
        self.assertTrue(self.page.locator('.card button[data-action="save"]').is_disabled())
        self.assertTrue(self.page.locator('.card button[data-action="bag"]').is_disabled())
        self.assertTrue(self.page.locator('.card button[data-action="tryon"]').is_disabled())

    def test_candidate_with_missing_cal_decision_is_hidden(self):
        self.payload = offer_payload(
            {
                "variant_id": "unverified-variant",
                "product_name": "MISSING CAL APPROVAL PRODUCT",
                "display_authorized": True,
                "decision_status": "SHOW",
                # Deliberately omit cal_decision.
            },
            display_authorized=True,
        )
        self.page.reload(wait_until="domcontentloaded")
        self.page.wait_for_function(
            "document.querySelector('#status').textContent.includes('No candidates on this page')",
            timeout=5000,
        )
        self.assertEqual(self.page.locator(".card").count(), 0)
        self.assertNotIn("MISSING CAL APPROVAL PRODUCT", self.page.locator("#products").inner_text())

    def test_browser_exposes_no_direct_catalog_or_commerce_account_connection(self):
        self.page.locator("#settingsBtn").click()
        self.page.locator("#commerceToken").wait_for()
        self.assertEqual(self.page.locator("#apiBase").count(), 0)
        self.assertEqual(self.page.get_by_role("button", name="Connect catalog only").count(), 0)
        self.assertTrue(self.page.locator("#savedBtn").is_disabled())
        self.assertTrue(self.page.locator("#cartBtn").is_disabled())
        self.assertIn("Direct Catalog and Commerce API connections are disabled", self.page.get_by_role("dialog").inner_text())


if __name__ == "__main__":
    unittest.main()
