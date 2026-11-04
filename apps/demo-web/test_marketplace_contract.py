"""Static contract checks for the standalone Cirvanna marketplace page.

These checks guard integration boundaries; they are not a substitute for browser E2E
or a live authenticated API smoke test.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "apps/demo-web" / "marketplace.html").read_text(encoding="utf-8")
CATALOG = (ROOT / "services/catalog-service" / "app" / "main.py").read_text(encoding="utf-8")


class MarketplaceContractTests(unittest.TestCase):
    def test_page_has_search_and_pagination_controls(self):
        self.assertIn("CIRVANNA_MARKETPLACE_CONFIG", HTML)
        self.assertIn("bootstrap.publicOffersBase", HTML)
        self.assertIn("LIVE MARKETPLACE", HTML)
        for element_id in ("query", "category", "products", "prevBtn", "nextBtn", "settingsBtn"):
            with self.subTest(element_id=element_id):
                self.assertIn(f'id="{element_id}"', HTML)

    def test_live_api_uses_catalog_contract_and_bearer_auth(self):
        self.assertIn('url.searchParams.set("limit","20")', HTML)
        self.assertIn('url.searchParams.set("offset",String(page*20))', HTML)
        self.assertIn('Authorization:"Bearer "+config.token', HTML)
        self.assertIn('Demo data is not substituted after a live API error.', HTML)

    def test_bearer_token_requires_tls_except_local_development(self):
        self.assertIn("bearer tokens may only be sent to HTTPS endpoints", HTML)
        self.assertIn('u.protocol!=="https:"', HTML)

    def test_price_formatting_respects_currency_fraction_digits(self):
        self.assertIn("formatter.resolvedOptions().maximumFractionDigits", HTML)
        self.assertIn("Math.pow(10,digits)", HTML)

    def test_unimplemented_commerce_features_are_not_faked(self):
        self.assertIn('disabled title="Virtual try-on adapter is not connected"', HTML)
        self.assertIn('disabled>Checkout unavailable</button>', HTML)
        self.assertIn("No stock is reserved and no order is created.", HTML)
    def test_tari_is_the_marketplace_assistant_and_complementer_is_advisory(self):
        self.assertIn("Tari · Describe it", HTML)
        self.assertIn("Search marketplace with Tari", HTML)
        self.assertIn("Complementer is designed as optional styling advice", HTML)
        self.assertIn("price comparisons must use current Commerce offers", HTML)
        self.assertNotIn("Xari · Describe it", HTML)
        self.assertNotIn("with Xari", HTML)
        self.assertNotIn("search with Xari", HTML)

    def test_try_on_remains_visible_but_disabled_until_real_adapters_exist(self):
        self.assertIn("Try on — unavailable", HTML)
        self.assertIn("Virtual try-on adapter is not connected", HTML)

    def test_cors_is_explicitly_allowlisted(self):
        self.assertIn("CATALOG_CORS_ORIGINS", CATALOG)
        self.assertIn("allow_credentials=False", CATALOG)
        self.assertIn('allow_methods=["GET", "OPTIONS"]', CATALOG)
        self.assertNotIn('allow_origins=["*"]', CATALOG)


if __name__ == "__main__":
    unittest.main()
