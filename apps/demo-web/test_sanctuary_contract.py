from __future__ import annotations

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent
HTML = (ROOT / "sanctuary.html").read_text(encoding="utf-8")
CSS = (ROOT / "assets" / "cirvanna-sanctuary.css").read_text(encoding="utf-8")
JS = (ROOT / "assets" / "cirvanna-sanctuary.js").read_text(encoding="utf-8")


class SanctuaryContractTests(unittest.TestCase):
    def test_brand_palette_and_blue_flame_are_explicit(self):
        for token in ("--cv-obsidian", "--cv-white", "--cv-gold", "--cv-purple", "--cv-blue"):
            with self.subTest(token=token):
                self.assertIn(token, CSS)
        self.assertIn("The Blue Flame", HTML)
        self.assertIn("not a generated Twin", HTML)

    def test_only_real_demo_surfaces_are_linked_as_available(self):
        self.assertIn('href="/wardrobe.html"', HTML)
        self.assertIn('href="/marketplace.html"', HTML)
        self.assertIn('href="/marketplace.html#lookItTitle"', HTML)
        self.assertIn('href="/marketplace.html#descriptionSearchTitle"', HTML)
        for unavailable in ("Click It", "DermalSight", "Experience Lab"):
            with self.subTest(unavailable=unavailable):
                self.assertIn(unavailable, HTML)
        self.assertIn("NOT AVAILABLE IN THIS WEB DEMO", HTML)
        self.assertIn('aria-disabled="true"', HTML)

    def test_twin_transition_has_truthful_readiness_boundary(self):
        self.assertIn("consented capture, reconstruction and persistence", HTML)
        self.assertIn("persistent, validated Twin is ready", HTML)
        self.assertNotIn("Your Virtual Twin is ready!", HTML)

    def test_accessibility_and_motion_preferences(self):
        self.assertIn('href="#main"', HTML)
        self.assertIn('aria-controls="primaryNav"', HTML)
        self.assertIn('aria-expanded="false"', HTML)
        self.assertIn("prefers-reduced-motion: reduce", CSS)
        self.assertIn('event.key === "Escape"', JS)

    def test_local_asset_references_resolve(self):
        self.assertTrue((ROOT / "assets" / "cirvanna-sanctuary.css").is_file())
        self.assertTrue((ROOT / "assets" / "cirvanna-sanctuary.js").is_file())
        self.assertRegex(HTML, r'<link rel="stylesheet" href="assets/cirvanna-sanctuary\.css">')
        self.assertRegex(HTML, r'<script src="assets/cirvanna-sanctuary\.js" defer></script>')


if __name__ == "__main__":
    unittest.main()



def test_sanctuary_explains_independent_identity_dimensions():
    for label in (
        "CULTURAL EXPRESSION",
        "PERSONAL AESTHETIC",
        "OCCASION",
        "PERSONAL PREFERENCES",
        "REGIONAL CONTEXT",
    ):
        assert label in HTML
    assert "Many influences. One unmistakably yours." in HTML
    assert 'href="/wardrobe.html">Shape your personal atelier' in HTML
    assert "Nothing is inferred from your appearance." in HTML
    for token in (".cv-identity-grid", ".cv-identity-card", "@media (max-width: 440px)"):
        assert token in CSS
