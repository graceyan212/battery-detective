import pytest

from battery_detective.cli import build_parser, parse_time


def test_default_interval_and_custom_database():
    args = build_parser().parse_args(["collect", "--db", "/tmp/test.db"])
    assert args.interval == 60
    assert str(args.db) == "/tmp/test.db"


@pytest.mark.parametrize("args", [["collect", "--interval", "0"], ["collect", "--interval", "nan"],
                                  ["collect", "--count", "0"], ["prune", "--days", "-1"],
                                  ["dashboard", "--port", "70000"]])
def test_invalid_cli_values_rejected(args):
    with pytest.raises(SystemExit):
        build_parser().parse_args(args)


def test_time_requires_explicit_timezone():
    assert parse_time("2026-10-19T16:00:00Z") == 1792425600
    with pytest.raises(ValueError):
        parse_time("2026-10-19T16:00:00")
