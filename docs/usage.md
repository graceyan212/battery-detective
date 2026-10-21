# Running Battery Detective

[Project overview](../README.md) · [Measurement definitions](measurements.md)

## Setup

Requires Python 3.11 or newer and a Mac. Validated on an Apple Silicon MacBook Air with macOS 26.6.2 and Python 3.11.1. Other macOS versions and Intel Macs have not been validated.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
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
open http://127.0.0.1:8765
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
open http://127.0.0.1:8766
```

The example includes ordinary drain, a sustained build workload, a 25-minute sampling gap, and external power. Synthetic provenance appears in the dashboard and every report. The demo command refuses to overwrite an existing file, and the live collector refuses to append to a synthetic database. Choose another file name to generate a fresh demo.

An [example investigation](../examples/synthetic-investigation.md) is generated from the same deterministic fixture.

## Investigate a period

1. Choose the last hour, last six hours, today, or a custom window.
2. Click a highlighted drain period, drag across the chart, or enter investigation start/end times.
3. Read the recorded process activity and investigation notes. Expand the limitations before interpreting a hypothesis.
4. Use **Save report** to download the complete five-section Markdown report.

Use **What we measure**, or a question-mark button beside a reading, for plain-language definitions and the macOS/Python source of each measurement. Investigation notes show the main finding first; supporting measurements and limitations can be expanded. The activity table starts with five processes and can show up to 20 of the busiest recorded processes.

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

## Share a recorded dashboard

Export a selected interval into a **new** directory, then deploy that directory to Vercel:

```sh
python -m battery_detective share \
  --start '2026-10-20T14:14:00-07:00' \
  --end '2026-10-20T20:14:00-07:00' \
  --output .context/shared-recording

vercel .context/shared-recording --prod
```

The export includes real app/process names, timestamps, and measurements in the chosen interval. Review those before publishing. It leaves the live recorder and database untouched and performs no upload itself. The deployment contains only the selected data, required analysis modules, and frontend assets; keep the generated directory out of Git.

The hosted dashboard opens to the saved recording, even after its date passes. Visitors can select intervals, adjust detection settings, and download reports. A saved-recording label distinguishes it from live monitoring, and it never reads the visitor's device or receives future readings. Earlier comparison history outside the export is unavailable. The SQLite file is bundled for server-side analysis, not served as a downloadable asset.

The hosted adapter adds Flask; the local collector does not need it. For a local preview, install `python -m pip install -e '.[share]'`, then run `python -m flask --app .context/shared-recording/app.py run --port 8767` and open `http://127.0.0.1:8767`. The generated deployment has its own dependencies and Vercel configuration. Vercel deployment access settings determine who can view it; verify the production link in a signed-out browser before sharing.
