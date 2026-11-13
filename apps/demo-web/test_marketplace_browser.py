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
