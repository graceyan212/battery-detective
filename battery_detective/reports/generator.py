from datetime import datetime, timezone


def stamp(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def render_report(report):
    lines = ["# Battery Detective investigation", "",
             f"Window: {stamp(report['start'])} to {stamp(report['end'])}", ""]
    if "synthetic" in report["sources"]:
        lines.extend(["**Synthetic measurements: demonstration data, not activity from this Mac.**", ""])
    lines.extend(["## 1. What happened?", ""])
    if not report["sample_count"]:
        lines.append("No measurements in this window.")
    elif report["observations"]:
        first = report["observations"][0]
        lines.append(f"[{first['id']}] {first['text']}")
    lines.extend(["", "## 2. What changed?", ""])
    if report["baseline"]["rate"] is not None:
        lines.append(f"Preceding equal-length window: {report['baseline']['rate']:.1f} percentage points/hour. Workloads are not matched.")
    else:
        lines.append("No qualifying prior-window discharge baseline is available.")
    if report["cpu_change"] is not None:
        lines.append(f"Mean system CPU changed by {report['cpu_change']:+.1f} percentage points relative to that window.")
    for fact in report["observations"][1:]:
        lines.append(f"- [{fact['id']}] {fact['text']}")
    if report["foreground"]:
        lines.append("Foreground observations: " + ", ".join(f"{item['name']} ({item['observations']} samples)" for item in report["foreground"]) + ".")
    lines.extend(["", "## 3. Potential explanations", ""])
    if not report["hypotheses"]:
        lines.append("Insufficient evidence to rank contributors to battery drain.")
    for hypothesis in report["hypotheses"]:
        lines.append(f"{hypothesis['rank']}. {hypothesis['text']} Evidence: {', '.join(hypothesis['evidence'])}. Confidence: {hypothesis['confidence']}.")
    lines.extend(["", "## 4. Limitations", ""])
    lines.extend(f"- {limitation}" for limitation in report["limitations"])
    lines.extend(["", "## 5. Suggested next experiments", ""])
    lines.extend(f"- {experiment}" for experiment in report["experiments"])
    return "\n".join(lines) + "\n"
