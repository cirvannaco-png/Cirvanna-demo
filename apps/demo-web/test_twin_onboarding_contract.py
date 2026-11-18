from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
HTML = (ROOT / "twin-onboarding.html").read_text(encoding="utf-8")
CSS = (ROOT / "assets" / "cirvanna-twin-onboarding.css").read_text(encoding="utf-8")
BASE_CSS = (ROOT / "assets" / "cirvanna-sanctuary.css").read_text(encoding="utf-8")
JS = (ROOT / "assets" / "cirvanna-twin-onboarding.js").read_text(encoding="utf-8")
SANCTUARY = (ROOT / "sanctuary.html").read_text(encoding="utf-8")


class TwinOnboardingContractTests(unittest.TestCase):
    def test_brand_direction_and_blue_flame_are_preserved(self):
        self.assertIn("--cv-obsidian", BASE_CSS)
        self.assertIn("--cv-gold", BASE_CSS)
        self.assertIn("--cv-purple", BASE_CSS)
        self.assertIn("--cv-blue", BASE_CSS)
        self.assertIn("var(--cv-gold)", CSS)
        self.assertIn("From blue flame", HTML)
        self.assertIn("Your Twin", HTML)

    def test_capability_check_uses_the_authenticated_same_origin_bff(self):
        self.assertIn('"/api/virtual-twin/capabilities"', JS)
        self.assertIn('Authorization: "Bearer " + token', JS)
        self.assertIn('cache: "no-store"', JS)
        self.assertIn('credentials: "same-origin"', JS)
        self.assertIn("persistent_twin_generation", JS)
        self.assertIn("persistent_twin_preview", JS)
        self.assertIn("full_surface_mesh", JS)
        self.assertIn("image_persistence", JS)

    def test_capture_is_fail_closed_until_full_persistent_pipeline_exists(self):
        self.assertIn('id="startCapture" type="button" disabled', HTML)
        self.assertIn("Capture is currently locked", HTML)
        self.assertIn("does not persist a Twin", HTML)
        self.assertIn("It rejects video", HTML)
        self.assertIn("No image, video or biometric data", HTML)
        self.assertNotIn('type="file"', HTML)
        self.assertNotIn("getUserMedia", HTML)
        self.assertNotIn("FormData", JS)
        self.assertNotIn('fetch("/twin"', JS)

    def test_saved_twin_lookup_uses_owner_scoped_bff_and_never_reads_private_assets(self):
        self.assertIn('"/api/virtual-twin/me"', JS)
        self.assertIn('Authorization: "Bearer " + token', JS)
        self.assertIn('id="savedTwinPanel"', HTML)
        self.assertIn('id="savedTwinStatus"', HTML)
        self.assertIn("Registry metadata only", JS)
        self.assertNotIn("mesh_asset_id", JS)
        self.assertNotIn("source_image_asset_ids", JS)
        self.assertNotIn("/internal/v1/twins", JS)

    def test_purpose_specific_consent_is_explained_but_not_granted(self):
        for scope in ("Image processing", "Body measurements", "Virtual Twin storage"):
            with self.subTest(scope=scope):
                self.assertIn(scope, HTML)
        self.assertIn("No consent is being recorded on this page", HTML)
        self.assertNotIn('"/api/appearance/consents"', JS)
        self.assertNotIn("virtual_twin_storage", JS)

    def test_session_token_is_never_persisted(self):
        self.assertIn('type="password"', HTML)
        self.assertIn("page's memory", HTML)
        self.assertNotIn("localStorage", JS)
        self.assertNotIn("sessionStorage", JS)
        self.assertNotIn("document.cookie", JS)

    def test_navigation_reaches_onboarding_from_the_sanctuary(self):
        self.assertIn('href="/twin-onboarding.html"', SANCTUARY)
        self.assertIn('href="sanctuary.html"', HTML)
        self.assertIn('href="wardrobe.html"', HTML)

    def test_reduced_motion_and_mobile_layout_support(self):
        self.assertIn("prefers-reduced-motion:reduce", CSS)
        self.assertIn("@media(max-width:540px)", CSS)
        self.assertIn("@media(max-width:820px)", CSS)


if __name__ == "__main__":
    unittest.main()
