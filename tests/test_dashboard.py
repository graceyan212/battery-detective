import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from battery_detective.dashboard.server import make_server
from battery_detective.demo import seed_demo
from battery_detective.storage.database import Store


@pytest.fixture
def dashboard(tmp_path):
    db = tmp_path / "demo.sqlite"
    seed_demo(db, end=36000)
    server = make_server(db, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", db
    server.shutdown()
    server.server_close()
    thread.join()


def fetch(url, **headers):
    with urlopen(Request(url, headers=headers), timeout=5) as response:
        return json.load(response)


def test_timeline_and_report_use_persisted_measurements(dashboard):
    base, db = dashboard
    result = fetch(base + "/api/timeline?start=14400&end=36000")
    assert result["samples"][0]["battery_percent"] == 90
    assert result["anomalies"]
    report = fetch(base + "/api/investigate?start=19800&end=23400")
    assert report["investigation"]["discharge"]["rate"] == 18
    assert "Synthetic" in report["markdown"]
    with Store(db, readonly=True) as store:
        assert store.status()["samples"] == 337


@pytest.mark.parametrize("query", ["start=nan&end=36000", "start=0&end=999999999999", "start=40000&end=36000", "start=a&end=5"])
def test_invalid_window_returns_clear_error(dashboard, query):
    with pytest.raises(HTTPError) as error:
        fetch(dashboard[0] + "/api/timeline?" + query)
    assert error.value.code == 400


@pytest.mark.parametrize("headers", [{"Host": "attacker.example"}, {"Origin": "https://attacker.example"}, {"Sec-Fetch-Site": "cross-site"}])
def test_remote_origins_and_dns_rebinding_blocked(dashboard, headers):
    with pytest.raises(HTTPError) as error:
        fetch(dashboard[0] + "/api/status", **headers)
    assert error.value.code == 403


def test_missing_database_produces_empty_state_without_creating_file(tmp_path):
    db = tmp_path / "missing.sqlite"
    server = make_server(db, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = fetch(f"http://127.0.0.1:{server.server_port}/api/status")
        assert result["samples"] == 0
        assert not db.exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_static_assets_and_unknown_route(dashboard):
    base, _ = dashboard
    with urlopen(base) as response:
        assert "Battery Detective" in response.read().decode()
        assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    with pytest.raises(HTTPError) as error:
        urlopen(base + "/../storage/database.py")
    assert error.value.code == 404
