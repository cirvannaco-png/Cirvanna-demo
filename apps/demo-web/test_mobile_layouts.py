from __future__ import annotations

from pathlib import Path

import pytest


PAGES = (
    Path("apps/demo-web/marketplace.html"),
    Path("apps/demo-web/wardrobe.html"),
)
VIEWPORTS = (
    (320, 640),
    (360, 800),
    (393, 873),
    (412, 915),
    (844, 390),
)


def test_demo_pages_have_no_horizontal_overflow_on_mobile_and_landscape():
    playwright_sync = pytest.importorskip("playwright.sync_api")
    with playwright_sync.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for page_path in PAGES:
                assert page_path.is_file(), f"missing demo page: {page_path}"
                page = browser.new_page()
                page.goto(page_path.resolve().as_uri(), wait_until="domcontentloaded")
                for width, height in VIEWPORTS:
                    page.set_viewport_size({"width": width, "height": height})
                    page.wait_for_timeout(100)
                    geometry = page.evaluate("""() => ({
                      viewport: window.innerWidth,
                      document: document.documentElement.scrollWidth,
                      body: document.body ? document.body.scrollWidth : 0
                    })""")
                    assert geometry["document"] <= width + 1, (
                        f"{page_path} overflows horizontally at {width}x{height}: {geometry}"
                    )
                    assert geometry["body"] <= width + 1, (
                        f"{page_path} body overflows horizontally at {width}x{height}: {geometry}"
                    )
                page.close()
        finally:
            browser.close()
