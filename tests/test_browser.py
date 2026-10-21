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
    # The fixture records 640,000,000 bytes; the visible MB label means 640 MB.
    playwright.expect(page.locator("#process-table tr").filter(has_text="clang")).to_contain_text("640 MB")
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
    playwright.expect(page.locator("#selection-label")).to_contain_text("readings")
    page.set_viewport_size({"width": 390, "height": 844})
    page.evaluate("window.scrollTo(0, 0)")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    playwright.expect(page.get_by_role("button", name="Investigate", exact=True)).to_be_visible()
    if os.environ.get("BATTERY_DETECTIVE_SCREENSHOTS"):
        page.screenshot(path=".context/dashboard-mobile.png", full_page=True)
    assert all(url.startswith(base) for url in requests)


def test_saved_recording_stays_explorable_after_its_recording_date(browser_page, tmp_path):
    from werkzeug.serving import make_server as make_hosted_server
    from battery_detective.dashboard.hosted import create_app
    from battery_detective.sharing import export_recording

    database = tmp_path / "history.sqlite"
    seed_demo(database, end=36000)
    with Store(database) as store:
        store.conn.execute("UPDATE sessions SET source='live'")
        store.conn.commit()
    exported = export_recording(database, tmp_path / "share", 14400, 36000)
    server = make_hosted_server("127.0.0.1", 0, create_app(exported), threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        page = browser_page
        page.goto(f"http://127.0.0.1:{server.server_port}")
        playwright.expect(page.get_by_role("button", name="Save report")).to_be_enabled()
        playwright.expect(page.locator("#collector-state")).to_contain_text("Saved recording")
        playwright.expect(page.locator("#demo-notice")).to_be_hidden()
        playwright.expect(page.locator("footer")).not_to_contain_text("No uploads")
        playwright.expect(page.locator("footer")).to_contain_text("does not monitor your device")
        assert not page.locator("#collector-state.fresh").count()
        playwright.expect(page.locator("#process-table")).to_contain_text("clang")
        assert "337 readings" in page.locator("#sample-reading").inner_text()
        original_window = page.locator("#window-label").inner_text()
        page.get_by_role("button", name="Last hour", exact=True).click()
        playwright.expect(page.locator("#anomaly-list")).to_contain_text("No sustained")
        page.get_by_role("button", name="Reset view", exact=True).click()
        playwright.expect(page.locator("#window-label")).to_have_text(original_window)
        playwright.expect(page.locator(".anomaly-button").first).to_be_visible()
        page.locator(".anomaly-button").first.click()
        playwright.expect(page.locator("#evidence")).to_contain_text("percentage points/hour")
        with page.expect_download() as download:
            page.get_by_role("button", name="Save report").click()
        saved = tmp_path / "saved-report.md"
        download.value.save_as(saved)
        assert "Saved recording" in saved.read_text()
        assert "Synthetic measurements" not in saved.read_text()
        page.get_by_role("button", name="Custom", exact=True).click()
        page.locator("#window-start").fill("2026-01-01T01:00")
        page.locator("#window-end").fill("2026-01-01T02:00")
        page.get_by_role("button", name="Apply", exact=True).click()
        playwright.expect(page.locator("#empty-state")).to_be_visible()
        playwright.expect(page.locator("#collect-command")).to_be_hidden()
        page.get_by_role("button", name="Reset view", exact=True).click()
        playwright.expect(page.get_by_role("button", name="Save report")).to_be_enabled()
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert str(database) not in page.locator("body").inner_text()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


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


def test_contextual_measurement_help_restores_keyboard_focus(browser_page, browser_server):
    page = browser_page
    page.goto(browser_server[0])
    trigger = page.get_by_role("button", name="About battery drain", exact=True)
    trigger.focus()
    page.keyboard.press("Enter")
    dialog = page.get_by_role("dialog", name="Understand the readings")
    playwright.expect(dialog).to_be_visible()
    playwright.expect(dialog.locator("#guide-drain")).to_be_focused()
    playwright.expect(dialog.locator("#guide-drain")).to_contain_text("80% to 79%")
    page.keyboard.press("Escape")
    playwright.expect(dialog).not_to_be_visible()
    playwright.expect(trigger).to_be_focused()
    page.get_by_role("button", name="About processor use", exact=True).click()
    playwright.expect(dialog.locator("#guide-cpu")).to_be_focused()
    playwright.expect(dialog.locator("#guide-cpu")).to_contain_text("psutil")
    page.get_by_role("button", name="Close measurement guide", exact=True).click()
    playwright.expect(dialog).not_to_be_visible()


def test_process_list_expands_and_resets_for_a_new_window(browser_page, tmp_path):
    db = tmp_path / "many-processes.sqlite"
    start, _ = seed_demo(db)
    with Store(db) as store:
        sample_ids = [row[0] for row in store.conn.execute("SELECT id FROM samples")]
        for sample_id in sample_ids:
            for index in range(6):
                store.conn.execute(
                    "INSERT INTO process_activity (sample_id, pid, started, name, cpu_seconds, cpu_percent, rss) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (sample_id, 1000 + index, start - 60, f"Helper {index}", 1, 100 / 60, 1024),
                )
        store.conn.commit()
    server = make_server(db, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        page = browser_page
        page.goto(f"http://127.0.0.1:{server.server_port}")
        playwright.expect(page.get_by_role("button", name="Save report")).to_be_enabled()
        playwright.expect(page.locator("#process-table tr")).to_have_count(5)
        page.get_by_role("button", name="Show top 9", exact=True).click()
        playwright.expect(page.locator("#process-table tr")).to_have_count(9)
        page.get_by_role("button", name="Last hour", exact=True).click()
        playwright.expect(page.get_by_role("button", name="Save report")).to_be_enabled()
        playwright.expect(page.locator("#process-table tr")).to_have_count(5)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("width", [1440, 390])
def test_chart_drag_selects_rendered_time_bounds(browser_page, browser_server, width):
    page = browser_page
    base, start, end = browser_server
    page.set_viewport_size({"width": width, "height": 1000})
    page.goto(base)
    playwright.expect(page.get_by_role("button", name="Save report")).to_be_enabled()
    # The SVG container survives responsive redraws; individual grid lines do not.
    page.locator("#timeline-chart").scroll_into_view_if_needed()
    bounds = page.locator("#timeline-chart .chart-grid").first.bounding_box()
    page.mouse.move(bounds["x"] + 0.1, bounds["y"] + 3)
    page.mouse.down()
    page.mouse.move(bounds["x"] + bounds["width"] - 0.1, bounds["y"] + 3, steps=8)
    with page.expect_response("**/api/investigate?*") as response:
        page.mouse.up()
    selected = response.value.json()["investigation"]
    assert selected["start"] == start
    assert selected["end"] == end


def test_narrow_measurement_guide_keeps_scrollable_content_inside_dialog(browser_page, browser_server):
    page = browser_page
    page.set_viewport_size({"width": 320, "height": 568})
    page.goto(browser_server[0])
    page.get_by_role("button", name="What we measure", exact=True).click()
    dialog = page.get_by_role("dialog", name="Understand the readings")
    playwright.expect(dialog).to_be_visible()
    shell = dialog.bounding_box()
    content = dialog.locator(".guide-content").bounding_box()
    assert content["y"] + content["height"] <= shell["y"] + shell["height"] + 1
    page.locator("#guide-sensors").scroll_into_view_if_needed()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


@pytest.mark.parametrize("ending", ["return_to_start", "cancel"])
def test_aborted_drag_restores_the_analyzed_selection(browser_page, browser_server, ending):
    page = browser_page
    page.goto(browser_server[0])
    playwright.expect(page.get_by_role("button", name="Save report")).to_be_enabled()
    original_start = page.locator("#selection-start").input_value()
    original_end = page.locator("#selection-end").input_value()
    original_label = page.locator("#selection-label").inner_text()
    original_evidence = page.locator("#evidence").inner_text()
    chart = page.locator("#timeline-chart")
    chart.scroll_into_view_if_needed()
    bounds = page.locator("#timeline-chart .chart-grid").first.bounding_box()
    x, y = bounds["x"] + bounds["width"] * 0.4, bounds["y"] + 3
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + bounds["width"] * 0.2, y, steps=4)
    if ending == "return_to_start":
        page.mouse.move(x, y, steps=4)
    else:
        chart.dispatch_event("pointercancel", {"pointerId": 1})
    page.mouse.up()
    playwright.expect(page.locator("#selection-start")).to_have_value(original_start)
    playwright.expect(page.locator("#selection-end")).to_have_value(original_end)
    playwright.expect(page.locator("#selection-label")).to_have_text(original_label)
    playwright.expect(page.locator("#evidence")).to_have_text(original_evidence, use_inner_text=True)
    playwright.expect(page.get_by_role("button", name="Save report")).to_be_enabled()


@pytest.mark.parametrize("width", [820, 1100])
def test_unknown_battery_reading_stays_inside_measurement_panel(browser_page, browser_server, width):
    page = browser_page
    page.set_viewport_size({"width": width, "height": 1000})

    def missing_latest_battery(route):
        response = route.fetch()
        payload = response.json()
        payload["samples"][-1]["battery_percent"] = None
        route.fulfill(response=response, body=json.dumps(payload))

    page.route("**/api/timeline?*", missing_latest_battery)
    page.goto(browser_server[0])
    reading = page.locator("#battery-reading")
    playwright.expect(reading).to_have_text("Unavailable")
    bounds = reading.evaluate("""node => {
        const range = document.createRange();
        range.selectNodeContents(node);
        const text = range.getBoundingClientRect();
        const panel = node.closest('.readings').getBoundingClientRect();
        return {textLeft: text.left, textRight: text.right, panelLeft: panel.left, panelRight: panel.right};
    }""")
    assert bounds["textLeft"] >= bounds["panelLeft"]
    assert bounds["textRight"] <= bounds["panelRight"]
