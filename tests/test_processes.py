import pytest

from battery_detective.collector.processes import Observation, ProcessTracker


def obs(pid=7, started=10, cpu=20, read=100):
    return Observation(pid, started, "worker", cpu, 1024, read, 200)


def test_first_sample_unknown_then_one_core_percentage():
    tracker = ProcessTracker()
    assert tracker.update([obs()], None)[0]["cpu_percent"] is None
    row = tracker.update([obs(cpu=50, read=300)], 60)[0]
    assert row["cpu_percent"] == 50
    assert row["cpu_seconds"] == 30
    assert row["read_bytes"] == 200


def test_reused_pid_has_no_inherited_cpu():
    tracker = ProcessTracker()
    tracker.update([obs()], None)
    assert tracker.update([obs(started=50, cpu=500)], 60)[0]["cpu_seconds"] is None


def test_disappearing_or_inaccessible_process_loses_baseline():
    tracker = ProcessTracker()
    tracker.update([obs()], None)
    assert tracker.update([], 60) == []
    assert tracker.update([obs(cpu=80)], 60)[0]["cpu_seconds"] is None


def test_negative_counter_delta_is_unknown_then_recovers():
    tracker = ProcessTracker()
    tracker.update([obs()], None)
    row = tracker.update([obs(cpu=10, read=20)], 60)[0]
    assert row["cpu_seconds"] is None
    assert row["read_bytes"] is None
    assert tracker.update([obs(cpu=40, read=40)], 60)[0]["cpu_seconds"] == 30


@pytest.mark.parametrize("elapsed", [None, 0, -1])
def test_gap_resets_all_deltas(elapsed):
    tracker = ProcessTracker()
    tracker.update([obs()], None)
    assert tracker.update([obs(cpu=600)], elapsed)[0]["cpu_percent"] is None


def test_multicore_process_may_exceed_100_percent():
    tracker = ProcessTracker()
    tracker.update([obs()], None)
    assert tracker.update([obs(cpu=140)], 60)[0]["cpu_percent"] == 200
