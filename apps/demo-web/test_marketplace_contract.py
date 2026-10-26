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
        self.assertIn("CAL-GOVERNED MARKETPLACE", HTML)
        for element_id in ("query", "category", "products", "prevBtn", "nextBtn", "settingsBtn"):
            with self.subTest(element_id=element_id):
                self.assertIn(f'id="{element_id}"', HTML)

    def test_product_listing_uses_only_same_origin_cal_gateway(self):
        self.assertIn('url.searchParams.set("limit","20")', HTML)
        self.assertIn('url.searchParams.set("offset",String(page*20))', HTML)
        self.assertIn('fetch(url,{headers})', HTML)
        self.assertIn('cal_decision.verdict==="SHOW"', HTML)
        self.assertIn('cal_decision.may_display===true', HTML)
        self.assertIn('No demo, catalog-direct or ungoverned fallback was used.', HTML)
        self.assertNotIn('new URL(config.base+"/products")', HTML)
        self.assertNotIn('config.commerceBase', HTML)
        self.assertNotIn('Authorization:"Bearer "+config.token', HTML)

    def test_browser_token_is_only_forwarded_to_same_origin_bff(self):
        self.assertIn('headers.Authorization="Bearer "+config.userToken', HTML)
        self.assertIn('fetch("/api/vision/marketplace-search"', HTML)
        self.assertIn('fetch("/api/vision/click-it"', HTML)
        self.assertNotIn("validateApiBase", HTML)

    def test_price_formatting_respects_currency_fraction_digits(self):
        self.assertIn("formatter.resolvedOptions().maximumFractionDigits", HTML)
        self.assertIn("Math.pow(10,digits)", HTML)

    def test_unimplemented_commerce_features_are_fail_closed(self):
        self.assertIn('disabled title="Virtual try-on adapter is not connected"', HTML)
        self.assertIn('id="savedBtn" disabled', HTML)
        self.assertIn('id="cartBtn" disabled', HTML)
        self.assertIn("atomic CAL revalidation", HTML)
        self.assertNotIn('fetch(config.commerceBase+"/checkout"', HTML)
        self.assertNotIn('fetch(config.commerceBase+"/cart/items"', HTML)
        self.assertNotIn('fetch(config.commerceBase+"/saved-products/"', HTML)
        self.assertNotIn("DEMO MODE", HTML)

    def test_cors_is_explicitly_allowlisted(self):
        self.assertIn("CATALOG_CORS_ORIGINS", CATALOG)
        self.assertIn("allow_credentials=False", CATALOG)
        self.assertIn('allow_methods=["GET", "OPTIONS"]', CATALOG)
        self.assertNotIn('allow_origins=["*"]', CATALOG)


if __name__ == "__main__":
    unittest.main()
