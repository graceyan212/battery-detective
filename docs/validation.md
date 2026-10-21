# Validation

Checks performed on October 19–20, 2026, on an Apple Silicon MacBook Air with macOS 26.6.2 and Python 3.11.1. These results describe the tested prototype; they do not establish every acceptance criterion in the [PRD](prd.md).

## Automated coverage

The latest complete run passed **97 tests**, including **14 Brave browser cases**. Python compilation, JavaScript syntax, and wheel packaging checks also passed; the wheel contains the schema, dashboard assets, and hosted adapter.

Run `python -m pytest -q` after installing `.[dev,ui]`. Browser checks use an installed Brave Browser with isolated temporary profiles and are skipped when unavailable.

| Area | Verified behavior |
| --- | --- |
| Collection | PID reuse, inaccessible/exited processes, counter resets, sleep/clock discontinuities, failure recovery, duplicate exclusion, graceful termination, and restart baselines. |
| Storage | Atomic writes and rollback, persistence, read-only access, retention, and consistent query snapshots. |
| Analysis | Known discharge rates, charging transitions, gaps, quantization, anomaly thresholds, and contributor evidence restricted to valid unplugged intervals. |
| Interface | Presets, manual and chart selection, canceled drags, report downloads, empty/error states, fractional timestamps, measurement help, keyboard focus, and responsive layouts. |
| Sharing | Bounded exports, partial-interval exclusion, source preservation, independent deployment, provenance, validation of requests, and restricted asset routes. |

Synthetic fixtures supply known answers for calculations and failure cases. They complement hardware observations; they do not replace them.

## Hardware observations

A ten-sample collection run at the default 60-second cadence recorded 4,766 process rows over 540.04 seconds without root access or additional permissions. Battery fields and foreground-app context were available, with no sensor errors. Between 470 and 484 processes were observed per sample; 212–214 protected processes were counted and skipped.

The first CPU interval was unknown, and subsequent readings contained nonnegative deltas. SQLite integrity and foreign-key checks passed. This run stayed on external power, so it checks collection, not discharge accuracy.

A separate process lifecycle check confirmed duplicate exclusion, successful SIGTERM shutdown with a closed session, and a fresh baseline after restart. The LaunchAgent plist passed `plutil -lint` after a dry-run render; actual login startup and launchd crash recovery have not been validated.

### Observed collection cost

| Metric | Result |
| --- | ---: |
| Initial collection, including AppKit import | 1,203.5 ms |
| Median subsequent collection duration | 78.9 ms |
| Maximum subsequent collection duration | 206.9 ms |
| Median subsequent collector CPU time per sample | 0.0429 seconds |
| Maximum observed resident memory | 48.2 MiB |

Timing and CPU measurements exclude database writes, subprocess CPU, and periodic analysis. At a 60-second cadence, the median collection CPU corresponds to roughly 0.071% of one core within those limits. This short run does **not** measure battery-energy overhead. No controlled recorder-on/off battery comparison has been performed.

## Hosted recording

The [public demo](https://battery-detective.vercel.app) contains 256 actual readings from October 20, 2026, 2:14–8:14 PM Pacific, including unplugged and charging periods and gaps. The ending charge is 31%; qualifying discharge averages 13.5 percentage points/hour, with three flagged intervals. Core analysis was compared with the local dashboard for the same recording.

The production page was checked without credentials using HTTPS requests and a clean Brave profile. Interval selection, thresholds, reset, and Markdown downloads worked. Desktop and mobile checks found no page script errors, external page requests, or horizontal overflow. Database, metadata, source-code, and environment-file URL probes returned 404.

This is a fixed copy of the selected recording. It receives no future readings and cannot access a visitor's device. History outside the export is unavailable for comparisons. Raw recordings and local test artifacts are excluded from Git.

## Remaining validation

- Controlled unplugged workloads to evaluate drain estimates and false-positive rates.
- Actual suspend/resume, wall-clock adjustments, and charger-transition experiments.
- Opt-in LaunchAgent installation, login startup, intentional stop, and crash recovery.
- Repeated recorder-on/off trials measuring total CPU, memory, storage, and battery impact.
- A walkthrough with users unfamiliar with system metrics, plus broader Mac and macOS coverage.
