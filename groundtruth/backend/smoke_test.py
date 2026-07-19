"""Browser smoke test: sign up, run an extraction, verify grounded highlighting.

Usage:  python smoke_test.py   (server must be running on BASE)
"""
import glob, os, time
from playwright.sync_api import sync_playwright

BASE = os.environ.get("GT_BASE", "http://localhost:8011")
EMAIL = f"browser{int(time.time())}@test.app"

# Auto-detect the pre-installed Chromium (version-independent).
_candidates = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
CHROMIUM = _candidates[-1] if _candidates else ""

INVOICE = open("../sample_docs/invoice-sample.txt").read()

with sync_playwright() as p:
    launch = {"headless": True, "args": ["--no-sandbox"]}
    if os.path.exists(CHROMIUM):
        launch["executable_path"] = CHROMIUM
    browser = p.chromium.launch(**launch)
    page = browser.new_page()

    # 1. Landing loads + interactive demo present
    page.goto(BASE, wait_until="networkidle")
    assert "Groundtruth" in page.title(), "landing title missing"
    assert page.locator("#demoDoc .mark").count() >= 5, "demo highlights missing"
    print("[1/5] landing page + grounding demo render OK")

    # 2. Sign up
    page.goto(BASE + "/login.html?mode=signup", wait_until="networkidle")
    page.fill("#email", EMAIL)
    page.fill("#password", "supersecret1")
    page.click("#submitBtn")
    page.wait_for_url("**/app.html", timeout=10000)
    print("[2/5] signup -> redirected into app OK")

    # 3. Select invoice template, paste text, extract
    page.wait_for_selector(".tpl")
    page.click('.tpl[data-key="invoice"]')
    page.fill("#pasteText", INVOICE)
    page.click("#runBtn")
    page.wait_for_selector("#results:not(.hidden)", timeout=15000)
    page.wait_for_selector("#fieldsView .field-row", timeout=15000)
    n_fields = page.locator("#fieldsView .field-row").count()
    n_marks = page.locator("#docView mark").count()
    assert n_fields >= 4, f"expected fields, got {n_fields}"
    assert n_marks >= 4, f"expected highlights, got {n_marks}"
    print(f"[3/5] extraction rendered: {n_fields} fields, {n_marks} grounded highlights")

    # 4. Click a field -> its source mark becomes active (the core UX)
    page.locator("#fieldsView .field-row").first.click()
    page.wait_for_selector("#docView mark.active", timeout=5000)
    active = page.locator("#docView mark.active").count()
    assert active == 1, f"expected 1 active highlight, got {active}"
    print("[4/5] click field -> source highlighted (grounding interaction) OK")

    # 5. Usage meter updated
    usage = page.locator("#usageText").inner_text()
    assert "/ 25" in usage, f"usage not shown: {usage}"
    print(f"[5/5] usage meter shows: {usage.strip()}")

    browser.close()
    print("\nSMOKE TEST PASSED ✅")
