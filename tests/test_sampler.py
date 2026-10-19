import pytest

from battery_detective.collector.sampler import interval_quality, system_cpu_percent
from battery_detective.collector.battery import parse_power


@pytest.mark.parametrize("previous,current,expected", [
    (None, (100, 100), "first_sample"),
    ((100, 100), (160, 160), None),
    ((100, 100), (500, 500), "missing_samples"),
    ((100, 100), (160, 120), "sleep_or_clock_change"),
    ((100, 100), (90, 160), "clock_change"),
])
def test_interval_continuity(previous, current, expected):
    elapsed, reason = interval_quality(previous, current, 60)
    assert reason == expected
    assert elapsed == (60 if expected is None else None)


def test_system_cpu_uses_deltas_and_handles_reset():
    assert system_cpu_percent((100, 50), (200, 75)) == 75
    assert system_cpu_percent((100, 50), (90, 70)) is None
    assert system_cpu_percent(None, (100, 50)) is None


def test_native_battery_fields_do_not_confuse_power_with_charging():
    result = parse_power({"ExternalConnected": True, "IsCharging": False,
                          "Voltage": 12000, "Amperage": 2**64-1000, "CycleCount": 12})
    assert result == {"charging": False, "voltage_mv": 12000, "current_ma": -1000, "cycle_count": 12}
    assert parse_power({}) == {"charging": None, "voltage_mv": None, "current_ma": None, "cycle_count": None}
