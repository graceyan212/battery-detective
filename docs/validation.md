# Validation record

Validated locally on 2026-10-19 on an Apple Silicon MacBook Air, macOS 26.6.2, Python 3.11.1. This record distinguishes executed checks from unverified acceptance criteria.

## Real collector run

Command: `python -m battery_detective collect --db .context/live.sqlite --count 10` at the default 60-second interval, without root access or new macOS permissions.

- Ten samples across 540.04 seconds, 4,766 process rows, with an ended collection session.
- Between 470 and 484 processes observed per sample; 212–214 protected processes per sample were counted and skipped.
- Battery and native charging/voltage/current/cycle data were available. Foreground-app context was available. No sensor errors were recorded.
- The Mac was connected to external power throughout this run. This validates collection and charging-state handling, **not** real-world discharge accuracy or anomaly sensitivity.
- First-sample CPU utilization was unknown. Subsequent intervals recorded CPU deltas. No negative process CPU deltas were stored.
- `PRAGMA integrity_check` returned `ok`; `PRAGMA foreign_key_check` returned no violations.
- Raw history remains gitignored in `.context/live.sqlite`; no personal process history is included in committed examples.
- A separate real-process lifecycle check confirmed that a duplicate collector exits with an explanatory error, SIGTERM closes the session and exits successfully, and restarting records a fresh baseline in a distinct session. No persistent collector was left running after these checks.

## Observed collection overhead

| Metric | Result |
| --- | ---: |
| First collection duration, including AppKit import | 1,203.5 ms |
| Median subsequent collection duration | 78.9 ms |
| Maximum subsequent collection duration | 206.9 ms |
| Median subsequent collector CPU time per sample | 0.0429 seconds |
| Maximum observed collector resident memory | 48.2 MiB |

The duration and CPU fields measure collection before its database write. The rotating log also records full tick time including storage. At a 60-second cadence, the measured median collection CPU corresponds to approximately 0.071% of one core, excluding SQLite write/prune time, subprocess CPU, startup, and occasional anomaly analysis. This is a short-run estimate, **not a battery-energy measurement**.

The maximum RSS includes startup; later observed samples were around 27 MiB. No controlled collector-on/off battery comparison was performed. The initial sample is more expensive because AppKit is loaded once.

## Automated and browser checks

The final suite passed 69 tests, including four Brave browser tests. It checks discharge arithmetic, power transitions, missing/sleep intervals, process identity and reset handling, transaction rollback, read-only access, retention, anomaly merging, report provenance, locking, argument validation, and HTTP boundaries. Optional browser tests use the actual installed Brave executable with an isolated temporary profile; they do not change the user's browser settings.

Browser checks exercise synthetic data, known-rate manual interval selection, presets, anomaly selection, report download, empty databases, page script errors, lack of external page requests, and a 390-pixel viewport. Screenshots are saved under `.context/` when `BATTERY_DETECTIVE_SCREENSHOTS=1` is set. The dashboard was also opened in the user's Brave browser.

The real-history dashboard was checked against SQLite in Brave: its displayed battery percentage matched the latest persisted sample, synthetic labeling was absent, and no discharge rate was invented for external-power observations.

Independent code review identified mixed-power attribution, merged anomaly thresholds, timestamp truncation, stale browser errors, maintenance-failure continuity, and a status/pruning race. Regression tests reproduced those failures before fixes. Hypothesis evidence now uses qualifying unplugged intervals; merged anomalies must still meet the threshold; unchanged date controls retain sub-second boundaries; failed refreshes invalidate stale evidence; maintenance failures leave sampling baselines intact; and status queries use a consistent snapshot.

The LaunchAgent was rendered with `agent install --dry-run`; `plutil -lint` accepted the resulting plist. It was **not installed or enabled**. OS login/startup behavior cannot be claimed from plist validation alone.

Python compilation and JavaScript syntax checks passed. A wheel built successfully and includes the SQL schema and all dashboard assets. The installed command-line entry point was also checked from outside the repository.

## Still to validate

- Several hours of unattended collection on battery.
- Real suspend/resume, wall-clock corrections, and charger transitions on hardware.
- LaunchAgent installation, login startup, intentional stop, and recovery after a crash, when the user opts in.
- Controlled workload repetitions with and without the collector to measure battery impact.
- Different macOS versions, machines, batteries, and graphical-login configurations.

Synthetic datasets and deterministic tests provide known answers for analysis edge cases. They do not substitute for these hardware and lifecycle experiments.
