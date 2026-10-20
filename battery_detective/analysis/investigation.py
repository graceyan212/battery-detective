"""Evidence first: measured facts and uncertain explanations are separate fields."""

from collections import Counter
import json
import math

from .anomalies import detect_anomalies
from .discharge import continuity_issue, discharge_summary


def validate_window(start, end):
    if not all(math.isfinite(value) for value in (start, end)) or end <= start:
        raise ValueError("Choose a valid end time after the start time.")
    if end - start > 31 * 86400:
        raise ValueError("Choose a window of 31 days or less.")


def mean_cpu(samples):
    numerator, duration = 0, 0
    for left, right in zip(samples, samples[1:]):
        if not continuity_issue(left, right) and right.get("cpu_percent") is not None:
            dt = right["timestamp"] - left["timestamp"]
            numerator += right["cpu_percent"] * dt
            duration += dt
    return numerator / duration if duration else None


def discharge_contributors(store, segments):
    combined = {}
    for segment in segments:
        if segment["rate"] is None:
            continue
        for row in store.top_processes(segment["start"], segment["end"], limit=-1):
            key = (row["session_id"], row["pid"], row["started"], row["name"], row["bundle_id"])
            if key not in combined:
                combined[key] = row
                continue
            prior = combined[key]
            for field in ("cpu_seconds", "observed_seconds", "observations", "background_observations"):
                prior[field] += row[field]
    ranked = sorted(combined.values(), key=lambda row: -row["cpu_seconds"])
    for row in ranked:
        row["cpu_percent"] = 100 * row["cpu_seconds"] / row["observed_seconds"]
    return [row for row in ranked if row["cpu_seconds"] > 0][:5]


def investigate(store, start, end, threshold=12):
    validate_window(start, end)
    rows = store.samples(start, end)
    previous = store.samples(start - (end-start), start)
    discharge = discharge_summary(rows)
    baseline = discharge_summary(previous)
    current_cpu, previous_cpu = mean_cpu(rows), mean_cpu(previous)
    processes = store.top_processes(start, end)
    contributors = discharge_contributors(store, discharge["segments"])
    issues = Counter()
    covered = 0
    for left, right in zip(rows, rows[1:]):
        issue = continuity_issue(left, right)
        if issue:
            issues[issue] += 1
        else:
            covered += right["timestamp"] - left["timestamp"]
    foreground = {}
    sensor_errors = set()
    for row in rows:
        name, bundle = row.get("foreground_name"), row.get("foreground_bundle_id")
        if name:
            entry = foreground.setdefault((name, bundle), {"name": name, "bundle_id": bundle, "observations": 0})
            entry["observations"] += 1
        if row.get("sensor_errors"):
            sensor_errors.update(json.loads(row["sensor_errors"]))
    facts, hypotheses, experiments = [], [], []
    if discharge["rate"] is not None:
        facts.append({"id": "B1", "text": f"Lost {discharge['loss']:.1f} percentage points across {discharge['duration_seconds']/60:.0f} minutes of qualifying discharge: {discharge['rate']:.1f} percentage points/hour."})
    elif rows:
        facts.append({"id": "B1", "text": "Insufficient continuous discharge for a rate: at least 10 minutes and 2 percentage points are required."})
    if current_cpu is not None:
        facts.append({"id": "C1", "text": f"Mean system CPU utilization was {current_cpu:.1f}% of total CPU capacity."})
    for index, process in enumerate(processes[:5], 1):
        evidence_id = f"P{index}"
        facts.append({"id": evidence_id, "text": f"{process['name']} (PID {process['pid']}) recorded {process['cpu_seconds']:.1f} CPU seconds; {process['cpu_percent']:.1f}% mean CPU on a one-core scale during observed intervals."})
    for index, process in enumerate(contributors, 1):
        evidence_id = f"D{index}"
        facts.append({"id": evidence_id, "text": f"During qualifying unplugged intervals, {process['name']} (PID {process['pid']}) recorded {process['cpu_seconds']:.1f} CPU seconds; {process['cpu_percent']:.1f}% mean CPU on a one-core scale."})
        hypotheses.append({"rank": index,
                           "text": f"CPU work by {process['name']} may have contributed to drain during the qualifying unplugged intervals. This is a correlation, not an attribution of battery energy.",
                           "evidence": ["B1", evidence_id], "confidence": "Unconfirmed"})
    if hypotheses:
        experiments.append(f"Repeat a comparable unplugged workload with {contributors[0]['name']} idle, keeping screen brightness and network conditions similar, then compare at least 15 minutes of discharge.")
    experiments.append("Collect a longer uninterrupted unplugged window and compare similar workloads before drawing conclusions.")
    limits = [
        "Battery percentage is rounded; discharge rates are estimates of percentage points per hour, not instantaneous power.",
        "CPU activity is correlation, not proof of battery use. Display, GPU, network, thermal conditions, and other hardware are not attributed to applications.",
        "Foreground identity is sampled at each observation; app switches and processes that start and exit between samples can be missed.",
        "Brief power transitions between samples and clock changes indistinguishable from sleep cannot be reconstructed.",
        "Process CPU percentages use one logical core (and may exceed 100%); system CPU uses total machine capacity.",
        "The process table covers the whole selected window; contributor evidence uses only complete process intervals within qualifying unplugged discharge segments.",
    ]
    if not rows:
        limits.insert(0, "No measurements in this window. Run the collector or choose a recorded time range.")
    if baseline["rate"] is None:
        limits.append("No qualifying prior-window discharge baseline is available.")
    else:
        limits.append("The baseline is the preceding equal-length window, not a workload-matched or causal comparison.")
    if issues or covered < end-start-1:
        limits.append(f"{max(0, end-start-covered)/60:.1f} minutes of the selected window lack continuous observations. Gaps and session boundaries are excluded.")
    denied = max((row.get("inaccessible_processes") or 0 for row in rows), default=0)
    if denied:
        limits.append(f"Up to {denied} processes per sample could not be read with this user's permissions.")
    if sensor_errors:
        limits.append("Unavailable sensors: " + ", ".join(sorted(sensor_errors)).replace("_", " ") + ".")
    return {"start": start, "end": end, "sample_count": len(rows),
            "sources": sorted({row["source"] for row in rows}),
            "discharge": discharge, "baseline": {"rate": baseline["rate"], "start": start-(end-start), "end": start},
            "system_cpu": current_cpu, "previous_system_cpu": previous_cpu,
            "cpu_change": current_cpu-previous_cpu if current_cpu is not None and previous_cpu is not None else None,
            "processes": processes, "contributors": contributors, "foreground": sorted(foreground.values(), key=lambda item: -item["observations"]),
            "anomalies": detect_anomalies(rows, threshold), "observations": facts, "hypotheses": hypotheses,
            "limitations": limits, "experiments": experiments,
            "quality": {"covered_seconds": covered, "unobserved_seconds": max(0, end-start-covered), "issues": dict(issues), "inaccessible_processes": denied}}
