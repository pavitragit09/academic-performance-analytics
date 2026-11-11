"""Accessibility and responsiveness audit for the web UI (APAS-NF-004, TC-UX-01).

Runs axe-core with the WCAG 2.1 A and AA rules on every page (login, student, faculty,
administrator) at a desktop (1280 px) and a mobile (375 px) width, and checks that the page
never scrolls sideways.

Usage (from the repository root, with the demo data loaded and the server running):
    pip install playwright
    playwright install chromium
    python -m scripts.seed_demo            # only once, on an empty database
    uvicorn src.app.main:app --port 8000
    python -m scripts.a11y_audit

Exit code 0 means no violations. axe-core is downloaded once from cdnjs and cached next to
this script.
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

AXE_VERSION = "4.10.2"
AXE_URL = f"https://cdnjs.cloudflare.com/ajax/libs/axe-core/{AXE_VERSION}/axe.min.js"
AXE_CACHE = Path(__file__).with_name(f".axe-{AXE_VERSION}.min.js")

# Demo accounts from scripts/seed_demo.py (sample data only).
PAGES = [
    ("login", None, None),
    ("student", "student1", "DemoStudent1!"),
    ("faculty", "faculty1", "DemoFaculty1!"),
    ("admin", "admin1", "DemoAdmin1!"),
]
SIZES = {"desktop": {"width": 1280, "height": 800}, "mobile": {"width": 375, "height": 740}}
WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]


def load_axe() -> str:
    if not AXE_CACHE.exists():
        with urllib.request.urlopen(AXE_URL, timeout=30) as response:  # noqa: S310 (fixed URL)
            AXE_CACHE.write_bytes(response.read())
    return AXE_CACHE.read_text(encoding="utf-8")


def audit(base_url: str, screenshots: Path | None) -> dict:
    from playwright.sync_api import sync_playwright

    axe = load_axe()
    results = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for size, viewport in SIZES.items():
            for name, username, password in PAGES:
                # bypass_csp only lets the audit inject axe-core; the app's own CSP is unchanged.
                context = browser.new_context(viewport=viewport, bypass_csp=True)
                page = context.new_page()
                page.goto(f"{base_url}/app/")
                page.wait_for_selector("#page-title")
                if username:
                    page.fill("#username", username)
                    page.fill("#password", password)
                    page.click("button[type=submit]")
                    page.wait_for_function(
                        "document.querySelector('#page-title').textContent !== 'Log in'"
                    )
                    page.wait_for_load_state("networkidle")
                page.evaluate(axe + "; 0")
                report = page.evaluate(
                    "tags => axe.run(document, {runOnly: {type: 'tag', values: tags}})", WCAG_TAGS
                )
                sideways = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
                if screenshots:
                    screenshots.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=screenshots / f"{size}-{name}.png", full_page=True)
                results[f"{size}/{name}"] = {
                    "rulesPassed": len(report["passes"]),
                    "violations": [
                        {"rule": v["id"], "impact": v["impact"], "elements": len(v["nodes"])}
                        for v in report["violations"]
                    ],
                    "scrollsSideways": sideways,
                }
                context.close()
        browser.close()
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--screenshots", type=Path, help="folder to save full-page screenshots")
    args = parser.parse_args()

    results = audit(args.base_url.rstrip("/"), args.screenshots)
    failed = False
    print(f"{'Page':<18}{'Rules passed':>14}{'Violations':>12}{'Sideways scroll':>17}")
    for page, result in results.items():
        bad = bool(result["violations"]) or result["scrollsSideways"]
        failed |= bad
        print(f"{page:<18}{result['rulesPassed']:>14}{len(result['violations']):>12}"
              f"{'yes' if result['scrollsSideways'] else 'no':>17}")
        for violation in result["violations"]:
            print("    ", json.dumps(violation))
    print("TC-UX-01:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
