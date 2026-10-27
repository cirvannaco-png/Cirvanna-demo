"""Headless browser smoke tests for the marketplace demo UI."""
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

    def test_advanced_metadata_filters_apply_and_clear_in_demo_mode(self):
        self.page.locator("#filterDetails summary").click()
        self.page.locator("#filterMaterial").fill("linen")
        self.page.locator("#applyFiltersBtn").click()
        self.assertEqual(self.page.locator(".card").count(), 1)
        self.assertIn("Relaxed Linen Shirt", self.page.locator(".card").inner_text())
        self.assertIn("1 active filter", self.page.locator("#activeFilterCount").inner_text())

        self.page.locator("#clearFiltersBtn").click()
        self.assertEqual(self.page.locator(".card").count(), 6)
        self.assertIn("0 active filters", self.page.locator("#activeFilterCount").inner_text())

    def test_domain_characteristic_filter_matches_metadata_in_demo_mode(self):
        self.page.locator("#filterDetails summary").click()
        self.page.locator("#filterAttributeKey").select_option("texture")
        self.page.locator("#filterAttributeValue").fill("lightweight")
        self.page.locator("#applyFiltersBtn").click()
        self.assertEqual(self.page.locator(".card").count(), 1)
        self.assertIn("Radiant Skin Serum", self.page.locator(".card").inner_text())

        self.page.locator("#clearFiltersBtn").click()
        self.assertEqual(self.page.locator(".card").count(), 6)


    def test_price_filters_require_a_currency_and_use_price_bounds(self):
        self.page.locator("#filterDetails summary").click()
        self.page.locator("#filterMinPrice").fill("2000")
        self.page.locator("#applyFiltersBtn").click()
        self.assertIn("Select a currency", self.page.locator("#status").inner_text())
        self.assertEqual(self.page.locator(".card").count(), 0)

        self.page.locator("#filterCurrency").select_option("KES")
        self.page.locator("#filterMaxPrice").fill("3000")
        self.page.locator("#applyFiltersBtn").click()
        self.assertEqual(self.page.locator(".card").count(), 1)
        self.assertIn("Relaxed Linen Shirt", self.page.locator(".card").inner_text())


    def test_price_precision_matches_selected_currency_minor_units(self):
        self.page.locator("#filterDetails summary").click()
        self.page.locator("#filterCurrency").select_option("JPY")
        self.page.locator("#filterMinPrice").fill("1.5")
        self.page.locator("#applyFiltersBtn").click()
        self.assertIn("more decimal places than JPY supports", self.page.locator("#status").inner_text())
        self.assertEqual(self.page.locator(".card").count(), 0)

        self.page.locator("#filterMinPrice").fill("1")
        self.page.locator("#applyFiltersBtn").click()
        self.assertIn("DEMO MODE", self.page.locator("#status").inner_text())

    def test_try_on_and_checkout_are_not_misrepresented_as_live(self):
        try_on = self.page.locator('.card button[data-action="tryon"]').first
        self.assertTrue(try_on.is_disabled())
        self.page.locator('.card button[data-action="bag"]').first.click()
        self.page.locator("#cartBtn").click()
        self.assertTrue(self.page.get_by_role("dialog").get_by_role("button", name="Checkout unavailable").is_disabled())

    def test_non_https_remote_catalog_url_is_rejected_before_fetch(self):
        self.page.locator("#settingsBtn").click()
        self.page.locator("#apiBase").fill("http://catalog.example.com")
        self.page.locator("#apiToken").fill("test-token-not-a-secret")
        messages = []

        def accept_dialog(dialog):
            messages.append(dialog.message)
            dialog.accept()

        self.page.once("dialog", accept_dialog)
        self.page.get_by_role("button", name="Connect catalog only").click()
        self.assertTrue(messages, "Expected the insecure URL warning dialog")
        self.assertIn("only be sent to HTTPS", messages[0])


if __name__ == "__main__":
    unittest.main()
