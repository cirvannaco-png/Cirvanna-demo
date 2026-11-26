from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HTML = (ROOT / "wardrobe.html").read_text(encoding="utf-8")


def test_style_profile_builder_exposes_independent_axes():
    for element_id in ("styleCulture", "styleAesthetic", "styleOccasion", "stylePersonal", "styleMarket"):
        assert f'id="{element_id}"' in HTML
    for value in (
        "culture:contemporary-african-luxury",
        "style:classic",
        "occasion:wedding",
        "coverage:long-sleeves",
        "market:KE",
    ):
        assert value in HTML
    assert 'id="saveStyleProfile"' in HTML
    assert "pnelly_user_confirmed" not in HTML  # the browser delegates provenance to the BFF/USI contract
    assert "api(\"/api/wardrobe/pnelly/preferences\"" in HTML


def test_wardrobe_inline_javascript_parses_with_node():
    scripts = re.findall(r"<script(?:[ \t][^>]*)?>(.*?)</script>", HTML, flags=re.IGNORECASE | re.DOTALL)
    nonempty = [script for script in scripts if script.strip()]
    assert nonempty, "expected inline Wardrobe application script"
    for script in nonempty:
        result = subprocess.run(
            ["node", "--check", "-"],
            input=script,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr


def test_wardrobe_uses_sanctuary_visual_tokens():
    for token in ("--ink:#09080d", "--gold:#d7b36a", "--radius:18px"):
        assert token in HTML
    assert "border-radius:var(--radius)" in HTML

def test_all_builder_values_are_manageable_and_allowlisted_in_the_ui():
    options_match = re.search(
        r"const PNELLY_PREFERENCE_OPTIONS = \\[(.*?)\\n  \\];",
        HTML,
        flags=re.DOTALL,
    )
    builder_match = re.search(
        r'<div class="style-profile-builder".*?</div>\\s*</div>',
        HTML,
        flags=re.DOTALL,
    )
    assert options_match is not None
    assert builder_match is not None
    managed = set(re.findall(r'\\["((?:style|color|silhouette|material|pattern|culture|occasion|coverage|market):[^"]+)"', options_match.group(1)))
    builder_values = set(re.findall(r'value="((?:style|color|silhouette|material|pattern|culture|occasion|coverage|market):[^"]+)"', builder_match.group(0)))
    assert builder_values.issubset(managed)
