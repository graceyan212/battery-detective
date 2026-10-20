# Battery Detective

A local macOS battery recorder and investigation dashboard. Select a period, inspect the battery change alongside CPU and foreground-app observations, and read a report that separates measured facts from possible explanations.

The collector and dashboard run independently. History stays in SQLite on your Mac. There are no accounts, analytics, external assets, or model API calls.

## Setup

Requires Python 3.11 or newer and a Mac. Validated on an Apple Silicon MacBook Air with macOS 26.6.2 and Python 3.11.1. Other macOS versions and Intel Macs have not been validated.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

`psutil` reads battery and process counters. PyObjC provides AppKit context on macOS. The remaining application uses Python's standard library. `requirements.txt` also lists the runtime dependencies.

No administrator, Accessibility, Screen Recording, Full Disk Access, or browser permissions are required. Protected processes are skipped and counted, rather than prompting for more permissions. Foreground context is optional and can be unavailable outside a graphical login session.

## Start recording and open the dashboard

In one terminal:

```sh
source .venv/bin/activate
python -m battery_detective collect
```

In a second terminal:

```sh
source .venv/bin/activate
python -m battery_detective dashboard
open -a 'Brave Browser' http://127.0.0.1:8765
```

The first sample is immediate. CPU deltas become available after the next sample, normally 60 seconds later. Leave the collector running; click **Refresh** to read newly stored history. Closing the dashboard or browser does not stop the collector. Ctrl-C in the collector terminal stops it gracefully.

Both commands default to:

```text
~/Library/Application Support/Battery Detective/telemetry.sqlite
```

Use `--db /path/to/history.sqlite` on **both** commands to select another database. The dashboard binds only to `127.0.0.1`, reads the database without modifying it, and blocks foreign Host/Origin requests. It is intended for a single-user local session, not public hosting.

Useful collector options:

```sh
python -m battery_detective collect --interval 30 --retention-days 7
python -m battery_detective collect --db .context/check.sqlite --count 3
python -m battery_detective dashboard --port 8766
```

Sampling intervals are restricted to 30–60 seconds. Do not run a second collector for the same database; an OS file lock prevents this, including through symlink aliases.

## Explore the demonstration

Create a **new** database with six hours of explicitly synthetic measurements:

```sh
python -m battery_detective demo --db demo.sqlite
python -m battery_detective dashboard --db demo.sqlite --port 8766
open -a 'Brave Browser' http://127.0.0.1:8766
```

The example includes ordinary drain, a sustained build workload, a 25-minute sampling gap, and external power. Synthetic provenance appears in the dashboard and every report. The demo command refuses to overwrite an existing file, and the live collector refuses to append to a synthetic database. Choose another file name to generate a fresh demo.

An [example investigation](examples/synthetic-investigation.md) is generated from the same deterministic fixture.

## Investigate a period

1. Choose the last hour, last six hours, today, or a custom window.
2. Click a highlighted drain period, drag across the chart, or enter investigation start/end times.
3. Read the recorded process activity and investigation notes. Expand the limitations before interpreting a hypothesis.
4. Use **Save report** to download the complete five-section Markdown report.

Dashboard times use the browser's local timezone; the chart identifies it. Command-line reports require an explicit timezone and render their window in UTC:

```sh
python -m battery_detective report \
  --start '2026-10-19T13:00:00-07:00' \
  --end '2026-10-19T16:00:00-07:00' \
  --threshold 12 > investigation.md
```

No API key is needed. An external LLM integration is intentionally deferred; nothing in this application uploads activity histories.

## Optional background collection

Installing the user LaunchAgent is an explicit opt-in. Run these commands from the activated virtual environment and keep the application and environment in their current locations afterward.

```sh
# Inspect the configuration without changing your login items:
python -m battery_detective agent install --dry-run

# Opt in to recording at login, then start recording now:
python -m battery_detective agent install
python -m battery_detective agent start
python -m battery_detective agent status

# Stop for this login session:
python -m battery_detective agent stop

# Remove automatic startup; keep recorded history:
python -m battery_detective agent uninstall
```

`scripts/install_agent.sh` is a wrapper around installation using this checkout's `.venv`. `agent install --db ...` records a custom database path in the plist; subsequent start/stop/status commands manage that installed configuration. Uninstall and reinstall to change it. Installation schedules the next login but does not immediately start collection; `agent start` starts it now.

The plist lives at `~/Library/LaunchAgents/local.battery-detective.collector.plist`. It uses the current virtual environment's absolute Python path, a 30-second restart throttle, background priority, and restart-on-failure behavior. Ordinary collector failures retry at the normal sample interval; repeated failures exit so launchd can recover. The collector sleeps between samples and does not request system wakeups. After wake, it does not backfill invented observations.

The application error/heartbeat log is `collector.log` alongside the database (1 MB rotation, three backups). LaunchAgent stdout/stderr are under `~/Library/Logs/Battery Detective/`. Logs contain lifecycle/measurement metadata, not process histories. A stopped agent can start at the next login; uninstall it to disable future startup. The dashboard is never installed as a background service.

For complete removal, uninstall the agent, stop any manually launched collector, then remove the virtual environment/checkout. Historical data and logs remain until you explicitly delete them.

## Measurements and estimates

| Value | Meaning and limits |
| --- | --- |
| Battery percentage | macOS-reported charge percentage, subject to rounding and gauge adjustments. |
| External power | Whether `psutil` reports a power adapter. Being plugged in does not necessarily mean charging. |
| Charging, voltage, current, cycles | Optional raw `AppleSmartBattery` registry fields. Missing fields remain unknown. Current is signed; these are not calibrated per-app measurements. |
| System CPU | Utilization calculated from cumulative CPU/idle counters, averaged over all CPU cores. |
| Process CPU time | User + system CPU seconds between consecutive accessible observations of the same PID and start time. |
| Process CPU percentage | CPU seconds divided by observed wall time. One fully busy logical core is 100%, so multi-core processes can exceed 100%. |
| Memory | System used-memory percentage and process resident bytes at each sample. |
| Process I/O | Counter deltas only where `psutil` exposes them. Unavailable on this validated macOS setup; stored as null. |
| Foreground application | `NSWorkspace.frontmostApplication` name, bundle identifier, and PID at the sampling instant. |
| Process app identity | Direct `NSWorkspace.runningApplications` identities when available. Helpers and daemons remain separate; no guessed parent-app attribution. |
| Estimated discharge | Percentage points lost divided by elapsed hours across qualifying continuous, unplugged intervals. |
| Potential contributor | A hypothesis supported by recorded activity, not a measurement of energy consumed by that process. |

New processes, inaccessible processes that return, and counter resets have unknown deltas until a new baseline is established. Zero means observed inactivity; null means unavailable evidence. Processes that exit between samples can be missed or undercounted.

The collector never reads keystrokes, screenshots, window titles, document contents, browser history, command-line arguments, or environment variables. The raw battery registry response is reduced to the documented fields above; identifiers and other properties are discarded. Database and lock files are created with mode `0600`, and the default data directory with `0700`. Other software running as the same user can still read the database.

## Analysis rules

- Both endpoints must be unplugged, in the same collection session, and have known battery percentages. Charging, battery increases, unavailable readings, and session changes split discharge runs.
- An interval longer than 1.5 times the configured sampling cadence is missing data. A wall/monotonic-clock discrepancy over two seconds is marked as sleep or a clock change. No rates cross these boundaries.
- A rate needs at least 10 minutes and a loss of at least 2 percentage points. Short or nearly flat segments remain visible but do not produce a rate.
- Fast-drain detection uses rolling windows of at least 15 minutes at a configurable threshold (default 12 percentage points/hour). Overlapping windows are merged within a continuous run, and the merged mean must still meet the threshold. This conservative guard can suppress brief bursts, but avoids presenting a broad, below-threshold period as sustained fast drain. This is a screening threshold, not a diagnosis or a learned personal norm.
- An investigation's prior baseline is the preceding equal-length window using the same validity rules. Workloads are **not** matched. If there is insufficient history, the report says so.
- The process table includes only complete observed intervals within the requested time window. Hypotheses use a separate ranking restricted to qualifying unplugged discharge segments. Activity observed only on external power cannot become a drain contributor. No prorated CPU activity is invented at window edges.

These choices favor interpretable estimates. They cannot reconstruct power transitions, app switches, or very short sleeps that occur wholly between samples. Display, GPU, radio, thermal, and other power use is not assigned to processes. High CPU does not prove which application caused a particular battery drop.

## Architecture

```text
battery_detective/
  collector/     Battery, process, foreground, timing, and lifecycle code
  storage/       SQLite schema, transactions, queries, and retention
  analysis/      Continuous discharge, rolling anomalies, investigation evidence
  reports/       Deterministic five-section Markdown reports
  dashboard/     Read-only HTTP API and local HTML/CSS/JavaScript assets
  agent.py       Opt-in launchctl / plist management
  demo.py        Reproducible, isolated synthetic measurements
  cli.py         Command-line entry points
```

Each sample batches its battery/system record, all process rows, and foreground observation into one transaction. SQLite WAL permits concurrent dashboard readers; requests pin their analysis queries to one database snapshot. The session table records start/end and cadence. Detected anomalies are cached every 15 successful samples; the dashboard and reports recompute them with the requested threshold, so the cache is not authoritative.

Raw history defaults to seven days and is pruned daily while the collector runs. You can prune explicitly with `python -m battery_detective prune --days 7`. Pruning cascades to process and foreground rows; SQLite can reuse freed pages without immediately shrinking its file. Storage grows with the number of accessible processes and your retention period.

## Tests and validation

```sh
python -m pytest -q

# Optional browser checks with an installed Brave Browser:
python -m pip install -e '.[dev,ui]'
python -m pytest tests/test_browser.py -q
```

Tests cover PID reuse, vanished/inaccessible observations, counter resets, atomic rollback, persistence, pruning, read-only queries, valid discharge, charging, gaps, clock changes, quantization, anomalies, report evidence, duplicate collectors, plist serialization, input validation, synthetic isolation, local-only HTTP access, browser selection, downloads, and mobile layout.

See [validation notes](docs/validation.md) for the actual hardware run, overhead measurements, and what remains unverified. A short collection run does **not** establish negligible battery impact or multi-hour reliability.

## Reference and next steps

Architectural study: [OpenMacBattery](https://github.com/MuratDugan/openmacbattery), particularly its [sampler](https://github.com/MuratDugan/openmacbattery/blob/main/Sources/OpenMacBatteryCore/Sampler.swift), [bundle resolver](https://github.com/MuratDugan/openmacbattery/blob/main/Sources/OpenMacBatteryCore/BundleResolver.swift), and [database](https://github.com/MuratDugan/openmacbattery/blob/main/Sources/OpenMacBatteryCore/Database.swift). This implementation is original Python code; no source was copied. The study informed identity-safe deltas, batched writes, and explicit measurement limitations. API references: [psutil](https://psutil.readthedocs.io/), [NSWorkspace foreground application](https://developer.apple.com/documentation/appkit/nsworkspace/frontmostapplication), and [Apple's LaunchAgent guide](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html).

Next validation work is an unplugged multi-hour run, actual sleep/wake and charger-transition experiments, a collector-on/off overhead comparison, and an opt-in login/crash-recovery test. Optional LLM explanations, calibrated power measurements, workload-matched historical baselines, and a native menu-bar UI are deferred until the collector has that field evidence.
