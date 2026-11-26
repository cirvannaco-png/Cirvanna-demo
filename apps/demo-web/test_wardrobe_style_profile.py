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
    scripts = re.findall(r"<script(?:\\s[^>]*)?>(.*?)</script>", HTML, flags=re.IGNORECASE | re.DOTALL)
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
