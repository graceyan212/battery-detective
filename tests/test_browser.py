"""Optional real-browser checks. Install .[ui]; uses installed Brave on macOS."""

from datetime import datetime
import os
from pathlib import Path
import threading
import json

import pytest

playwright = pytest.importorskip("playwright.sync_api")
from battery_detective.dashboard.server import make_server
from battery_detective.demo import seed_demo
from battery_detective.storage.database import Store

BRAVE = Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser")
pytestmark = pytest.mark.skipif(not BRAVE.exists(), reason="Brave Browser is required for these optional UI checks")


@pytest.fixture
def browser_page():
    with playwright.sync_playwright() as driver:
        browser = driver.chromium.launch(executable_path=str(BRAVE), headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100}, timezone_id="America/Los_Angeles")
        errors = []
        page.on("pageerror", lambda exception: errors.append(str(exception)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        yield page
        browser.close()
        assert errors == []


@pytest.fixture
def browser_server(tmp_path):
    db = tmp_path / "demo.sqlite"
    start, end = seed_demo(db)
    server = make_server(db, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", start, end
    server.shutdown()
    server.server_close()
    thread.join()


def test_selection_report_download_and_mobile_layout(browser_page, browser_server, tmp_path):
    page = browser_page
    base, start, _ = browser_server
    requests = []
    page.on("request", lambda request: requests.append(request.url))
    page.goto(base)
    playwright.expect(page.get_by_role("button", name="Save report")).to_be_enabled()
    playwright.expect(page.locator("#demo-notice")).to_be_visible()
    playwright.expect(page.locator("#process-table")).to_contain_text("clang")
    assert page.locator("#timeline-chart path.battery-line").get_attribute("d")
    if os.environ.get("BATTERY_DETECTIVE_SCREENSHOTS"):
        page.screenshot(path=".context/dashboard-desktop.png", full_page=True)
    with page.expect_download() as download:
        page.get_by_role("button", name="Save report").click()
    target = tmp_path / "report.md"
    download.value.save_as(target)
    assert "Synthetic measurements" in target.read_text()
    assert "Potential explanations" in target.read_text()
    # A manually selected, hand-known hour of synthetic high drain is 18 pp/h.
    for name, value in [("selection-start", start+90*60), ("selection-end", start+150*60)]:
        local = datetime.fromtimestamp(value).strftime("%Y-%m-%dT%H:%M")
        page.locator("#"+name).fill(local)
    page.get_by_role("button", name="Investigate", exact=True).click()
    playwright.expect(page.locator("#evidence")).to_contain_text("18.0 percentage points/hour")
    page.get_by_role("button", name="Last hour", exact=True).click()
    playwright.expect(page.locator("#anomaly-list")).to_contain_text("No sustained")
    page.get_by_role("button", name="Last 6 hours", exact=True).click()
    playwright.expect(page.locator(".anomaly-button").first).to_be_visible()
    page.locator(".anomaly-button").first.click()
    playwright.expect(page.locator("#selection-label")).to_contain_text("samples")
    page.set_viewport_size({"width": 390, "height": 844})
    page.evaluate("window.scrollTo(0, 0)")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    playwright.expect(page.get_by_role("button", name="Investigate", exact=True)).to_be_visible()
    if os.environ.get("BATTERY_DETECTIVE_SCREENSHOTS"):
        page.screenshot(path=".context/dashboard-mobile.png", full_page=True)
    assert all(url.startswith(base) for url in requests)


def test_empty_database_gives_startup_instructions(browser_page, tmp_path):
    server = make_server(tmp_path / "missing.sqlite", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        browser_page.goto(f"http://127.0.0.1:{server.server_port}")
        playwright.expect(browser_page.locator("#empty-state")).to_be_visible()
        playwright.expect(browser_page.locator("#collect-command")).to_contain_text("collect --db")
        playwright.expect(browser_page.locator("#investigation")).to_be_hidden()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_unchanged_selection_keeps_fractional_sample_boundaries(browser_page, tmp_path):
    db = tmp_path / "seconds.sqlite"
    with Store(db) as store:
        session = store.start_session(60, "synthetic", 1792454437.25)
        for i in range(11):
            store.add_sample(session, {"timestamp": 1792454437.25+i*60, "monotonic": i*60,
                                      "elapsed_seconds": 60 if i else None, "battery_percent": 80-i*.2,
                                      "plugged": False}, [], {})
    server = make_server(db, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        browser_page.goto(f"http://127.0.0.1:{server.server_port}")
        playwright.expect(browser_page.locator("#evidence")).to_contain_text("12.0 percentage points/hour")
        with browser_page.expect_response("**/api/investigate?*") as response:
            browser_page.get_by_role("button", name="Investigate", exact=True).click()
        result = response.value.json()["investigation"]
        assert result["sample_count"] == 11
        assert result["discharge"]["rate"] == 12
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_failed_refresh_does_not_hide_errors_or_retain_old_evidence(browser_page, browser_server):
    page = browser_page
    page.goto(browser_server[0])
    playwright.expect(page.get_by_role("button", name="Save report")).to_be_enabled()
    count = 0

    def fail_selected_request(route):
        nonlocal count
        count += 1
        if count == 1:  # Let the whole-window summary succeed.
            route.continue_()
        else:
            route.fulfill(status=200, content_type="application/json", body=json.dumps({"error": "Selected-window analysis unavailable"}))

    page.route("**/api/investigate?*", fail_selected_request)
    page.get_by_role("button", name="Refresh", exact=True).click()
    playwright.expect(page.locator("#refresh")).to_be_enabled()
    playwright.expect(page.locator("#error")).to_be_visible()
    playwright.expect(page.get_by_role("button", name="Save report")).to_be_disabled()
    playwright.expect(page.locator("#evidence")).not_to_contain_text("may have contributed")
