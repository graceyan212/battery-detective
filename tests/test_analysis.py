import pytest

from battery_detective.analysis.discharge import discharge_segments
from battery_detective.analysis.anomalies import detect_anomalies


def series(minutes=60, rate=10, **overrides):
    return [{"timestamp": i*60, "monotonic": i*60, "battery_percent": 90-rate*i/60,
             "plugged": False, "charging": False, "session_id": "a", "interval_seconds": 60,
             "elapsed_seconds": 60 if i else None, "gap_reason": None if i else "first_sample",
             "cpu_percent": 20, **overrides} for i in range(minutes+1)]


def test_percentage_points_per_hour():
    result = discharge_segments(series())[0]
    assert result["loss"] == 10
    assert result["duration_seconds"] == 3600
    assert result["rate"] == 10


def test_charging_and_unplugging_are_boundaries():
    rows = series()
    for row in rows[20:41]:
        row["plugged"] = True
    result = discharge_segments(rows)
    assert [(s["start"], s["end"]) for s in result] == [(0, 1140), (2460, 3600)]


@pytest.mark.parametrize("change", [{"gap_reason": "sleep_or_clock_change"}, {"battery_percent": None},
                                    {"elapsed_seconds": None}, {"plugged": None}])
def test_unknown_or_sleep_interval_never_bridged(change):
    rows = series()
    rows[30].update(change)
    assert all(not (s["start"] < 1800 < s["end"]) for s in discharge_segments(rows))


def test_missing_samples_are_not_bridged():
    rows = series()
    del rows[15:35]
    assert [(s["start"], s["end"]) for s in discharge_segments(rows)] == [(0, 840), (2100, 3600)]


def test_session_boundary_is_not_bridged():
    rows = series()
    for row in rows[30:]:
        row["session_id"] = "b"
    assert len(discharge_segments(rows)) == 2


def test_battery_increase_breaks_discharge():
    rows = series()
    rows[30]["battery_percent"] = 99
    assert all(not (s["start"] < 1800 < s["end"]) for s in discharge_segments(rows))


def test_tiny_or_short_observations_do_not_report_rates():
    assert discharge_segments(series(1, 60))[0]["rate"] is None
    assert discharge_segments(series(60, 1))[0]["rate"] is None


def test_ordinary_quantized_drain_is_not_anomalous():
    rows = series(rate=4)
    for row in rows:
        row["battery_percent"] = round(row["battery_percent"])
    assert detect_anomalies(rows) == []


def test_sustained_fast_drain_merges_overlapping_windows():
    result = detect_anomalies(series(rate=20))
    assert len(result) == 1
    assert result[0]["start"] == 0
    assert result[0]["end"] == 3600
    assert result[0]["rate"] == pytest.approx(20)


def test_threshold_and_minimum_duration_apply():
    assert detect_anomalies(series(10, 30)) == []
    assert detect_anomalies(series(rate=20), threshold=25) == []
    assert detect_anomalies(series(60, 30, plugged=True)) == []


def test_quantized_plateau_still_has_valid_zero_loss_segment():
    assert discharge_segments(series(rate=0))[0]["loss"] == 0
