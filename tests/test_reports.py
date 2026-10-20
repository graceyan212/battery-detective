from battery_detective.analysis.investigation import investigate
from battery_detective.reports.generator import render_report
from battery_detective.storage.database import Store


def test_investigation_uses_measured_activity_and_labels_hypotheses(tmp_path):
    with Store(tmp_path / "db") as store:
        session = store.start_session(60, "synthetic", 0)
        for i in range(61):
            store.add_sample(session, {
                "timestamp": i*60, "monotonic": i*60, "elapsed_seconds": 60 if i else None,
                "battery_percent": 80-i/3, "plugged": False, "cpu_percent": 60 if i else None,
                "gap_reason": None if i else "first_sample", "inaccessible_processes": 3,
            }, [{"pid": 7, "started": 1, "name": "compiler", "rss": 1024,
                 "cpu_seconds": 30 if i else None, "cpu_percent": 50 if i else None}],
               {"pid": 8, "name": "Editor", "bundle_id": "test.editor"})
        report = investigate(store, 0, 3600)
    assert report["discharge"]["rate"] == 20
    assert report["processes"][0]["cpu_seconds"] == 1800
    assert report["baseline"]["rate"] is None
    assert report["hypotheses"][0]["evidence"]
    assert report["foreground"][0]["name"] == "Editor"
    text = render_report(report)
    for phrase in ["What happened", "What changed", "Potential explanations", "Limitations", "Suggested next experiments", "Synthetic", "compiler", "correlation"]:
        assert phrase in text
    assert "watts" not in text


def test_no_data_report_does_not_invent_measurements(tmp_path):
    with Store(tmp_path / "db") as store:
        report = investigate(store, 0, 3600)
    assert report["discharge"]["rate"] is None
    assert report["hypotheses"] == []
    assert "No measurements" in render_report(report)


def test_no_rate_with_only_charging_data(tmp_path):
    with Store(tmp_path / "db") as store:
        session = store.start_session(60, "live", 0)
        for i in range(20):
            store.add_sample(session, {"timestamp": i*60, "monotonic": i*60,
                                      "battery_percent": 50+i, "plugged": True}, [], {})
        assert investigate(store, 0, 1200)["discharge"]["rate"] is None


def test_plugged_only_cpu_cannot_rank_as_a_discharge_contributor(tmp_path):
    with Store(tmp_path / "db") as store:
        session = store.start_session(60, "live", 0)
        for i in range(61):
            plugged = i > 30
            store.add_sample(session, {
                "timestamp": i*60, "monotonic": i*60, "elapsed_seconds": 60 if i else None,
                "battery_percent": 80-i/3 if not plugged else 70,
                "plugged": plugged,
            }, [
                {"pid": 1, "started": 1, "name": "unplugged-worker", "cpu_seconds": 12 if not plugged and i else 0, "cpu_percent": 20},
                {"pid": 2, "started": 1, "name": "plugged-worker", "cpu_seconds": 300 if plugged else 0, "cpu_percent": 500 if plugged else 0},
            ], {})
        report = investigate(store, 0, 3600)
    assert report["processes"][0]["name"] == "plugged-worker"  # Whole-window activity remains visible.
    assert report["contributors"][0]["name"] == "unplugged-worker"
    assert report["contributors"][0]["cpu_seconds"] == 360
    assert all("plugged-worker" not in item["text"].replace("unplugged-worker", "") for item in report["hypotheses"])
    assert "unplugged-worker" in report["experiments"][0]


def test_unknown_process_cpu_is_not_used_as_evidence(tmp_path):
    with Store(tmp_path / "db") as store:
        session = store.start_session(60, "live", 0)
        for i in range(31):
            store.add_sample(session, {"timestamp": i*60, "monotonic": i*60,
                                      "elapsed_seconds": 60 if i else None,
                                      "battery_percent": 80-i/3, "plugged": False},
                             [{"pid": 1,"started": 1,"name": "unknown","cpu_seconds": None}], {})
        report = investigate(store, 0, 1800)
    assert report["hypotheses"] == []
