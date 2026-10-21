"""A shared recording must stay faithful, bounded, and independent of its source."""

import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from battery_detective.cli import main
from battery_detective.demo import seed_demo
from battery_detective.storage.database import Store


@pytest.fixture
def recording(tmp_path):
    database = tmp_path / "private-history.sqlite"
    seed_demo(database, end=36000)
    with Store(database) as store:
        store.conn.execute("UPDATE sessions SET source='live'")
        store.conn.execute("UPDATE process_activity SET name='Outside private history' WHERE sample_id IN (SELECT id FROM samples WHERE timestamp < 19800 OR timestamp > 23400)")
        store.conn.commit()
    return database


def export(database, output, start=19800, end=23400):
    from battery_detective.sharing import export_recording
    return export_recording(database, output, start, end)


def test_share_cli_builds_a_deployment_without_changing_source(recording, tmp_path):
    output = tmp_path / "share"
    result = main(["share", "--db", str(recording), "--output", str(output),
                   "--start", "1970-01-01T05:30:00Z", "--end", "1970-01-01T06:30:00Z"])
    assert result == 0
    with Store(output / "data/recording.sqlite", readonly=True) as store:
        status = store.status()
        assert (status["samples"], status["first"], status["latest"]) == (61, 19800, 23400)
        assert status["sources"] == ["live"]
        assert store.top_processes(19800, 23400)[0]["cpu_seconds"] == 12600
        assert store.conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert store.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not store.conn.execute("PRAGMA foreign_key_check").fetchall()
        with pytest.raises(sqlite3.OperationalError):
            store.conn.execute("DELETE FROM samples")
    with Store(recording, readonly=True) as store:
        assert store.status()["samples"] == 337
    assert b"Outside private history" not in (output / "data/recording.sqlite").read_bytes()
    assert not list(output.rglob("*-wal"))
    assert not list(output.rglob("*-shm"))
    metadata = json.loads((output / "data/recording.json").read_text())
    assert (metadata["start"], metadata["end"]) == (19800, 23400)
    assert str(recording) not in json.dumps(metadata)
    assert (output / "public/index.html").is_file()
    assert (output / "public/app.js").is_file()
    assert not (output / "battery_detective/collector").exists()


@pytest.mark.parametrize("start,end", [(0, 1), (30000, 20000), (float("nan"), 23400)])
def test_invalid_or_empty_export_leaves_no_output(recording, tmp_path, start, end):
    output = tmp_path / "share"
    with pytest.raises(ValueError):
        export(recording, output, start, end)
    assert not output.exists()


def test_export_never_overwrites_an_existing_destination(recording, tmp_path):
    output = tmp_path / "share"
    output.mkdir()
    marker = output / "important.txt"
    marker.write_text("Keep this")
    with pytest.raises(FileExistsError):
        export(recording, output)
    assert marker.read_text() == "Keep this"


@pytest.fixture
def hosted(recording, tmp_path):
    from battery_detective.dashboard.hosted import create_app
    output = tmp_path / "share"
    export(recording, output)
    return create_app(output).test_client(), output


def test_hosted_results_preserve_measurements_and_recording_provenance(hosted):
    client, output = hosted
    database = output / "data/recording.sqlite"
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    status = client.get("/api/status").get_json()
    assert status["mode"] == "snapshot"
    assert status["recording"]["end"] == 23400
    assert status["sources"] == ["live"]
    assert str(output) not in json.dumps(status)
    timeline = client.get("/api/timeline?start=19800&end=23400").get_json()
    assert len(timeline["samples"]) == 61
    assert timeline["samples"][0]["battery_percent"] == 81
    assert timeline["samples"][-1]["battery_percent"] == 63
    response = client.get("/api/investigate?start=19800&end=23400")
    result = response.get_json()
    assert result["investigation"]["discharge"]["rate"] == 18
    assert result["investigation"]["contributors"][0]["name"] == "clang"
    assert result["investigation"]["baseline"]["rate"] is None
    assert "Saved recording" in result["markdown"]
    assert "Synthetic measurements" not in result["markdown"]
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    assert "noindex" in response.headers["X-Robots-Tag"]


def test_hosted_cannot_read_history_outside_the_export_or_new_samples(hosted, recording):
    client, _ = hosted
    with Store(recording) as store:
        session = store.start_session(timestamp=40000)
        store.add_sample(session, {"timestamp": 40000, "monotonic": 40000, "battery_percent": 99}, [], {})
    timeline = client.get("/api/timeline?start=10000&end=50000").get_json()
    assert len(timeline["samples"]) == 61
    assert all(19800 <= row["timestamp"] <= 23400 for row in timeline["samples"])
    assert client.get("/api/status").get_json()["latest"] == 23400


@pytest.mark.parametrize("start,first", [(19800, 19800), (19800.25, 19860)])
def test_export_discards_counters_that_cross_its_start(recording, tmp_path, start, first):
    from battery_detective.dashboard.hosted import create_app

    with Store(recording) as store:
        store.conn.execute("UPDATE process_activity SET read_bytes=1024, write_bytes=2048")
        store.conn.commit()
        original = store.samples(first, first)[0]
    output = export(recording, tmp_path / "bounded", start=start)
    client = create_app(output).test_client()
    query = f"start={first-60}&end={first}"
    result = client.get(f"/api/investigate?{query}").get_json()["investigation"]
    assert result["sample_count"] == 1
    assert result["quality"]["covered_seconds"] == 0
    assert result["processes"] == []
    sample = client.get(f"/api/timeline?{query}").get_json()["samples"][0]
    assert sample["cpu_percent"] is None
    assert sample["elapsed_seconds"] is None
    assert sample["battery_percent"] == original["battery_percent"]
    assert sample["foreground_name"] == original["foreground_name"]
    with Store(output / "data/recording.sqlite", readonly=True) as store:
        counters = store.conn.execute(
            "SELECT cpu_seconds, cpu_percent, read_bytes, write_bytes, rss FROM process_activity WHERE sample_id=?",
            (sample["id"],),
        ).fetchall()
        assert counters
        assert all(tuple(row)[:4] == (None, None, None, None) for row in counters)
        assert all(row["rss"] is not None for row in counters)
        assert store.top_processes(first, first+60)
    with Store(recording, readonly=True) as store:
        assert store.samples(first, first)[0] == original


@pytest.mark.parametrize("query", ["", "start=nan&end=23400", "start=0&end=999999999999", "start=23400&end=19800", "start=19800&end=23400&threshold=inf", "start=19800&end=23400&threshold=-1"])
def test_hosted_rejects_invalid_windows_and_thresholds(hosted, query):
    client, _ = hosted
    for route in ("timeline", "investigate"):
        response = client.get(f"/api/{route}?{query}")
        assert response.status_code == 400
        assert response.get_json()["error"]


def test_hosted_serves_only_explicit_assets_and_get_requests(hosted):
    client, _ = hosted
    for route in ("/", "/app.js", "/style.css"):
        response = client.get(route)
        assert response.status_code == 200
        assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    for route in ("/data/recording.sqlite", "/data/recording.json", "/app.py", "/battery_detective/storage/database.py", "/../data/recording.sqlite"):
        assert client.get(route).status_code == 404
    assert client.post("/api/status").status_code == 405


def test_deployment_runs_from_its_exported_files(hosted):
    _, output = hosted
    result = subprocess.run([sys.executable, "-c", "from app import app; print(app.test_client().get('/api/investigate?start=19800&end=23400').get_json()['investigation']['discharge']['rate'])"],
                            cwd=output, capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "18.0"


def test_export_retains_synthetic_source_labels(tmp_path):
    from battery_detective.dashboard.hosted import create_app
    database = tmp_path / "demo.sqlite"
    seed_demo(database, end=36000)
    output = tmp_path / "share"
    export(database, output)
    client = create_app(output).test_client()
    assert client.get("/api/status").get_json()["sources"] == ["synthetic"]
    assert "Synthetic measurements" in client.get("/api/investigate?start=19800&end=23400").get_json()["markdown"]
