import sqlite3
import stat

import pytest

from battery_detective.storage.database import Store


def sample(timestamp, **kwargs):
    return {"timestamp": timestamp, "monotonic": timestamp, "battery_percent": 80,
            "plugged": False, "elapsed_seconds": 60, **kwargs}


def process(**kwargs):
    return {"pid": 7, "started": 1, "name": "worker", "rss": 1024,
            "cpu_seconds": 30, "cpu_percent": 50, **kwargs}


def test_persists_batched_sample_and_foreground(tmp_path):
    db = tmp_path / "data.sqlite"
    with Store(db) as store:
        session = store.start_session(60, "live", 100)
        store.add_sample(session, sample(100), [process()], {"name": "Editor", "bundle_id": "org.editor"})
    with Store(db, readonly=True) as store:
        rows = store.samples(100, 100)
        assert len(rows) == 1
        assert rows[0]["foreground_name"] == "Editor"
        assert rows[0]["source"] == "live"
        assert store.top_processes(40, 100)[0]["cpu_seconds"] == 30
    assert stat.S_IMODE(db.stat().st_mode) == 0o600


def test_batch_failure_rolls_back_sample_and_processes(tmp_path):
    with Store(tmp_path / "db") as store:
        session = store.start_session(60, "live", 0)
        with pytest.raises(sqlite3.IntegrityError):
            store.add_sample(session, sample(60), [process(), process(pid=None)], {})
        assert store.samples(0, 100) == []


def test_window_never_includes_partial_cpu_interval(tmp_path):
    with Store(tmp_path / "db") as store:
        session = store.start_session(60, "live", 0)
        store.add_sample(session, sample(60), [process()], {})
        store.add_sample(session, sample(120), [process(cpu_seconds=60)], {})
        assert store.top_processes(30, 120)[0]["cpu_seconds"] == 60


def test_prune_cascades_processes_and_foreground(tmp_path):
    with Store(tmp_path / "db") as store:
        session = store.start_session(60, "live", 0)
        store.add_sample(session, sample(60), [process()], {"name": "Editor"})
        store.add_sample(session, sample(120), [process()], {})
        assert store.prune(90) == 1
        assert len(store.samples(0, 200)) == 1
        assert store.conn.execute("SELECT COUNT(*) FROM process_activity").fetchone()[0] == 1
        assert store.conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_read_only_connection_cannot_modify(tmp_path):
    db = tmp_path / "db"
    with Store(db):
        pass
    with Store(db, readonly=True) as store:
        with pytest.raises(sqlite3.OperationalError):
            store.start_session(60, "live", 0)
