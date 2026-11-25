"""Static contract checks for the standalone Cirvanna marketplace page.

These checks guard integration boundaries; they are not a substitute for browser E2E
or a live authenticated API smoke test.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "apps/demo-web" / "marketplace.html").read_text(encoding="utf-8")
WARDROBE_HTML = (ROOT / "apps/demo-web" / "wardrobe.html").read_text(encoding="utf-8")
CATALOG = (ROOT / "services/catalog-service" / "app" / "main.py").read_text(encoding="utf-8")


class MarketplaceContractTests(unittest.TestCase):
    def test_marketplace_uses_obsidian_gold_and_white_brand_palette(self):
        self.assertIn("--ink:#080808", HTML)
        self.assertIn("--gold:#d6ae62", HTML)
        self.assertIn("--cream:#ffffff", HTML)
        self.assertIn('name="theme-color" content="#080808"', HTML)
        self.assertIn('class="skip-link" href="#mainContent"', HTML)
        self.assertIn("--cv-white: #ffffff", (ROOT / "apps/demo-web/assets/cirvanna-sanctuary.css").read_text(encoding="utf-8"))
        self.assertIn("--cv-white-warm: #f7f3ed", (ROOT / "apps/demo-web/assets/cirvanna-sanctuary.css").read_text(encoding="utf-8"))

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
        self.assertIn('fetch(config.commerceBase+"/cart",{headers,cache:"no-store"})', HTML)
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
        self.assertIn('data-auth-provider="google"', HTML)
        self.assertIn('data-auth-provider="apple"', HTML)
        self.assertIn('data-auth-provider="microsoft"', HTML)
        self.assertIn('id="emailOtpForm"', HTML)
        self.assertNotIn("bootstrap.allowDeveloperTokenInput", HTML)
        self.assertNotIn('id="commerceToken"', HTML)
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
        self.assertIn("Search my wardrobe-aware marketplace", HTML)
        self.assertIn("candidate-bound CAL SHOW products", HTML)
        self.assertIn("CIL rights and evidence review", HTML)
        self.assertIn("Complementer is advisory only", HTML)
        self.assertIn('fetch("/api/wardrobe/recommendations"', HTML)
        self.assertIn('data.display_authority!=="CaTaCaCi/CAL"', HTML)
        self.assertNotIn("Search marketplace with Xari", HTML)
        self.assertNotIn("Xari · Describe it", HTML)
        self.assertNotIn("Search marketplace with Xari", HTML)
        self.assertNotIn("with Tari", HTML)
        self.assertNotIn("search with Tari", HTML)

    def test_complementer_feedback_is_opt_in_and_writes_to_tal(self):
        self.assertIn('id="complementerLearningConsent"', HTML)
        self.assertIn('id="complementerApproveBtn"', HTML)
        self.assertIn('id="complementerRejectBtn"', HTML)
        self.assertIn('scope:"personalization"', HTML)
        self.assertIn('/api/vision/complementer/feedback', HTML)
        self.assertIn('outcome', HTML)
        self.assertIn("private TAL learning timeline", HTML)
        self.assertNotIn('localStorage.setItem("complementer', HTML)

    def test_daily_looks_offer_identity_bound_stateless_complementer_advice(self):
        self.assertIn("Ask Complementer", WARDROBE_HTML)
        self.assertIn('api("/api/vision/complementer"', WARDROBE_HTML)
        self.assertIn('data.mode !== "advisory_only"', WARDROBE_HTML)
        self.assertIn("data.display_authorized !== false", WARDROBE_HTML)
        self.assertIn("data.durable_personal_memory !== false", WARDROBE_HTML)
        self.assertIn("One-session advice only", WARDROBE_HTML)
        self.assertNotIn("Refine with Complementer", WARDROBE_HTML)

    def test_daily_look_complementer_reactions_are_explicit_and_tal_confirmed(self):
        self.assertIn('api("/api/vision/complementer/feedback"', WARDROBE_HTML)
        self.assertIn('consent_receipt_id: styleReceipt', WARDROBE_HTML)
        self.assertIn('outcome', WARDROBE_HTML)
        self.assertIn('result.durable_persistence !== true', WARDROBE_HTML)
        self.assertIn("private TAL learning timeline", WARDROBE_HTML)
        self.assertIn("not yet used as an independent ranking signal", WARDROBE_HTML)
        self.assertIn('/api/wardrobe/pnelly/preferences', WARDROBE_HTML)
        self.assertIn('consent_receipt_id: profileReceipt', WARDROBE_HTML)
        self.assertIn('Only the preference you choose here is saved to your USI profile.', WARDROBE_HTML)


    def test_pnelly_describe_it_uses_verified_wardrobe_and_cal_discovery(self):
        self.assertIn('fetch("/api/wardrobe/recommendations"', HTML)
        self.assertIn('Authorization:"Bearer "+config.userToken', HTML)
        self.assertIn("Three ways to wear what you own", WARDROBE_HTML)
        self.assertIn("builds three distinct combinations", WARDROBE_HTML)
        self.assertIn("active Wardrobe", HTML)
        self.assertIn("consent-aware feedback", HTML)
        self.assertIn('data.display_authority!=="CaTaCaCi/CAL"', HTML)
        self.assertIn('decision.verdict!=="show"', HTML)
        self.assertIn('image_urls:[]', HTML)

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


def test_pnelly_saved_preferences_are_manageable_and_consent_gated():
    from pathlib import Path

    root = Path(__file__).resolve().parent
    wardrobe = (root / "wardrobe.html").read_text()
    assert 'id="pnellyPreferencesPanel"' in wardrobe
    assert '/api/wardrobe/pnelly/preferences?consent_receipt_id=' in wardrobe
    assert '/replace' in wardrobe
    assert '/deactivate' in wardrobe
    assert 'deactivated preferences stop guiding later daily looks.' in wardrobe
    assert 'profileReceipt = null' in wardrobe


def test_pnelly_daily_looks_ui_surfaces_eepl_review_and_block_without_claiming_pass():
    from pathlib import Path

    root = Path(__file__).resolve().parent
    wardrobe = (root / "wardrobe.html").read_text()
    assert 'id="pnellyLocation"' in wardrobe
    assert 'eligibility.verdict !== "PASS"' in wardrobe
    assert 'EEPL " + verdict' in wardrobe
    assert 'No looks were composed and wardrobe rotation was not changed.' in wardrobe
    assert 'context:' in wardrobe
