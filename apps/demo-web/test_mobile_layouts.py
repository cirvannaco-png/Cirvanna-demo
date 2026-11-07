from __future__ import annotations

from pathlib import Path

import pytest


PAGE_CANDIDATES = (
    Path("apps/demo-web/living-filters.html"),
    Path("apps/demo-web/marketplace.html"),
    Path("apps/demo-web/wardrobe.html"),
)
PAGES = tuple(path for path in PAGE_CANDIDATES if path.is_file())
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
            assert PAGES, "no eligible demo HTML pages found for mobile layout QA"
            for page_path in PAGES:
                assert page_path.is_file(), f"missing demo page: {page_path}"
                page = browser.new_page()
                page_errors: list[str] = []
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.goto(page_path.resolve().as_uri(), wait_until="domcontentloaded")
                if page_path.name == "wardrobe.html":
                    assert page.locator("#dailyLooksPanel").count() == 1
                    assert page.locator("#dailyLooksForm").count() == 1
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
                assert not page_errors, f"{page_path} raised JavaScript errors: {page_errors}"
                page.close()
        finally:
            browser.close()
