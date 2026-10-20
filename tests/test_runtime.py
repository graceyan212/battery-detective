import plistlib

import pytest

from battery_detective.collector.runtime import CollectorLock, CollectorAlreadyRunning
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
