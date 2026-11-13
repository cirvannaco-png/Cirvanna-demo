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
        self.assertIn("CAL-GOVERNED LIVE COMMERCE", HTML)
        self.assertIn('new URL(config.commerceBase+"/marketplace/offers",window.location.origin)', HTML)
        self.assertIn('Authorization:"Bearer "+config.userToken', HTML)
        self.assertIn('data.display_authority!=="CaTaCaCi/CAL"', HTML)
        self.assertIn("Sign in with a verified Cirvanna account", HTML)
        for element_id in ("query", "category", "products", "prevBtn", "nextBtn", "settingsBtn"):
            with self.subTest(element_id=element_id):
                self.assertIn(f'id="{element_id}"', HTML)

    def test_live_marketplace_uses_authenticated_bff_and_never_bypasses_cal(self):
        self.assertIn('const url=new URL(config.commerceBase+"/marketplace/offers",window.location.origin)', HTML)
        self.assertIn('Authorization:"Bearer "+config.userToken', HTML)
        self.assertIn("config.commerceBase=bootstrap.publicOffersBase.replace", HTML)
        self.assertIn('data.display_authority!=="CaTaCaCi/CAL"', HTML)
        self.assertIn("Direct Commerce browsing is disabled", HTML)
        self.assertIn("Direct Catalog product display is disabled", HTML)
        self.assertIn('fetch(config.commerceBase+"/cart",{headers})', HTML)
        self.assertIn("purchaseEnabled=true", HTML)
        self.assertIn("purchaseEnabled=false", HTML)
        self.assertIn('mode="commerce";purchaseEnabled=false;saved=[];cart=[];cartVersion=0;updateCounts();', HTML)
        self.assertIn("Candidate-bound CAL purchase authorization is not ready", HTML)
        self.assertIn("Checkout paused — CAL authorization unavailable", HTML)
        self.assertNotIn('new URL(config.base+"/products")', HTML)
        self.assertIn('new URL(config.commerceBase+"/marketplace/offers",window.location.origin)', HTML)
        self.assertIn('url.searchParams.set("offset",String(page*20))', HTML)
        self.assertIn("No demo fallback was used.", HTML)

    def test_account_connection_uses_same_origin_bff_without_upstream_urls(self):
        self.assertIn("same-origin Cirvanna Marketplace BFF", HTML)
        self.assertIn("bootstrap.publicOffersBase", HTML)
        self.assertIn("bootstrap.allowDeveloperTokenInput===true", HTML)
        self.assertIn("Account sign-in is unavailable until the approved Cirvanna OIDC browser session is configured", HTML)
        self.assertIn("Signed customer test token", HTML)
        self.assertNotIn('id="commerceBase"', HTML)
        self.assertNotIn('id="apiBase"', HTML)
        self.assertNotIn('id="apiToken"', HTML)
        self.assertNotIn("validateApiBase", HTML)

    def test_price_formatting_respects_currency_fraction_digits(self):
        self.assertIn("formatter.resolvedOptions().maximumFractionDigits", HTML)
        self.assertIn("Math.pow(10,digits)", HTML)

    def test_unimplemented_commerce_features_are_not_faked(self):
        self.assertIn('disabled title="Virtual try-on adapter is not connected"', HTML)
        self.assertIn('disabled>Checkout unavailable</button>', HTML)
        self.assertIn("No stock is reserved and no order is created.", HTML)
    def test_pnelly_is_the_marketplace_assistant_and_complementer_is_advisory(self):
        self.assertIn("PNELLY · Describe it", HTML)
        self.assertIn("Search marketplace with PNELLY", HTML)
        self.assertIn("Complementer is designed as optional styling advice", HTML)
        self.assertIn("price comparisons must use current Commerce offers", HTML)
        self.assertNotIn("Xari · Describe it", HTML)
        self.assertNotIn("Search marketplace with Xari", HTML)
        self.assertNotIn("with Tari", HTML)
        self.assertNotIn("search with Tari", HTML)

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
