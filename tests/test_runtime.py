import plistlib
import sqlite3

import pytest

from battery_detective.collector.runtime import CollectorLock, CollectorAlreadyRunning
from battery_detective.collector.runtime import run_collector
from battery_detective.collector.processes import Observation
from battery_detective.agent import agent_definition
from battery_detective.demo import seed_demo
from battery_detective.storage.database import Store
from battery_detective.analysis.investigation import investigate


def test_duplicate_collector_rejected_and_lock_released(tmp_path):
    db = tmp_path / "db"
    with CollectorLock(db):
        with pytest.raises(CollectorAlreadyRunning):
            with CollectorLock(db):
                pass
    with CollectorLock(db):
        pass


def test_symlink_database_has_same_lock(tmp_path):
    db = tmp_path / "real"
    db.touch()
    alias = tmp_path / "alias"
    alias.symlink_to(db)
    with CollectorLock(db):
        with pytest.raises(CollectorAlreadyRunning):
            with CollectorLock(alias):
                pass


def test_plist_preserves_spaces_without_shell_and_restarts_on_crash(tmp_path):
    definition = agent_definition(tmp_path / "with spaces/python", tmp_path / "db with spaces.sqlite", tmp_path / "project folder", tmp_path / "logs")
    decoded = plistlib.loads(plistlib.dumps(definition))
    assert decoded["ProgramArguments"][0] == str(tmp_path / "with spaces/python")
    assert str(tmp_path / "db with spaces.sqlite") in decoded["ProgramArguments"]
    assert decoded["KeepAlive"] == {"SuccessfulExit": False}
    assert decoded["RunAtLoad"] is True
    assert decoded["Umask"] == 0o077
    assert "StartInterval" not in decoded


def test_demo_refuses_existing_database_and_marks_synthetic(tmp_path):
    db = tmp_path / "demo.sqlite"
    seed_demo(db, end=36000)
    with Store(db, readonly=True) as store:
        status = store.status()
        result = investigate(store, 14400, 36000)
        assert status["sources"] == ["synthetic"]
        assert result["anomalies"]
        assert result["quality"]["issues"]["missing_samples"] == 1
        original = status["samples"]
    with pytest.raises(FileExistsError):
        seed_demo(db, end=72000)
    with Store(db, readonly=True) as store:
        assert store.status()["samples"] == original


def fake_sensors(monkeypatch):
    import battery_detective.collector.sampler as sampler
    count = 0

    def observations(apps):
        nonlocal count
        count += 1
        return [Observation(7, 1, "worker", count, 1024)], 0

    monkeypatch.setattr(sampler, "read_processes", observations)
    monkeypatch.setattr(sampler, "read_battery", lambda: ({"battery_percent": 80, "plugged": False}, []))
    monkeypatch.setattr(sampler, "read_applications", lambda: ({}, {}, []))


def test_maintenance_failure_does_not_erase_committed_baselines(tmp_path, monkeypatch):
    fake_sensors(monkeypatch)
    def failed_prune(self, before):
        raise sqlite3.OperationalError("injected maintenance failure")
    monkeypatch.setattr(Store, "prune", failed_prune)
    db = tmp_path / "db"
    run_collector(db, interval=0.1, count=3)
    with Store(db, readonly=True) as store:
        gaps = [row[0] for row in store.conn.execute("SELECT gap_reason FROM samples ORDER BY id")]
        assert gaps == ["first_sample", None, None]
        assert store.conn.execute("SELECT SUM(cpu_seconds) FROM process_activity").fetchone()[0] == 2


def test_repeated_sample_failure_exits_closes_session_and_releases_lock(tmp_path, monkeypatch):
    fake_sensors(monkeypatch)
    attempts = 0
    def failed_write(self, *args):
        nonlocal attempts
        attempts += 1
        raise sqlite3.OperationalError("injected write failure")
    monkeypatch.setattr(Store, "add_sample", failed_write)
    db = tmp_path / "db"
    with pytest.raises(sqlite3.OperationalError):
        run_collector(db, interval=0.1, count=3)
    assert attempts == 3
    with CollectorLock(db), Store(db, readonly=True) as store:
        assert store.conn.execute("SELECT ended FROM sessions").fetchone()[0] is not None
