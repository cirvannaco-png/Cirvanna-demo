"""Static security and contract checks for Cirvanna's Commerce-backed portals."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
MERCHANT = (ROOT / "apps/demo-web/merchant-portal.html").read_text(encoding="utf-8")
FOUNDER = (ROOT / "apps/demo-web/founder-console.html").read_text(encoding="utf-8")


class PortalContractTests(unittest.TestCase):
    def test_merchant_portal_uses_existing_commerce_contracts(self):
        for route in ("/me", "/merchants/me", "/merchants/applications",
                      "/merchant/listings", "/merchant/orders",
                      "/merchant/variants/"):
            self.assertIn(route, MERCHANT)
        self.assertIn("catalog_product_id", MERCHANT)
        self.assertIn("price_minor", MERCHANT)
        self.assertIn("quantity_delta", MERCHANT)
        self.assertIn("brand_home_country_code", MERCHANT)
        self.assertIn("legal_country_code", MERCHANT)
        self.assertIn("operating_markets", MERCHANT)
        self.assertIn('"/merchant/markets"', MERCHANT)
        self.assertIn("source_price_minor", MERCHANT)
        self.assertIn("source_currency", MERCHANT)
        self.assertIn('source_price_minor:$("sourcePriceMinor")', MERCHANT)
        self.assertIn('source_currency:$("sourceCurrency")', MERCHANT)
        self.assertIn('operating_markets:$("operatingMarkets")', MERCHANT)
        self.assertIn('api("/merchant/markets"', MERCHANT)
        self.assertIn("offer / transaction currency", MERCHANT.lower())

    def test_merchant_portal_never_persists_access_token(self):
        self.assertIn('type="password"', MERCHANT)
        self.assertIn('page memory', MERCHANT.lower())
        self.assertNotIn("localStorage", MERCHANT)
        self.assertNotIn("sessionStorage", MERCHANT)
        self.assertIn('u.protocol!=="https:"', MERCHANT)
        self.assertIn("provider-sourced FX quotes", MERCHANT)

    def test_founder_console_uses_server_side_admin_authorization(self):
        self.assertIn('actor.role!=="admin"', FOUNDER)
        self.assertIn('"/admin/merchants?state="', FOUNDER)
        self.assertIn('"/admin/merchants/"+encodeURIComponent(id)+"/decision"', FOUNDER)
        self.assertIn("verification_reference", FOUNDER)
        self.assertIn('"/ready"', FOUNDER)

    def test_founder_console_does_not_claim_unimplemented_controls(self):
        for forbidden in ("PAMASMMA online", "autonomyLevel", "circuitBreakers",
                          "MOCK_BRANDS", "MOCK_ALERTS", "MALI"):
            self.assertNotIn(forbidden, FOUNDER)


if __name__ == "__main__":
    unittest.main()
