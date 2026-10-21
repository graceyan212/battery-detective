# Measurements and architecture

[Project overview](../README.md) · [Setup and commands](usage.md)

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

## References

Architectural study: [OpenMacBattery](https://github.com/MuratDugan/openmacbattery), particularly its [sampler](https://github.com/MuratDugan/openmacbattery/blob/main/Sources/OpenMacBatteryCore/Sampler.swift), [bundle resolver](https://github.com/MuratDugan/openmacbattery/blob/main/Sources/OpenMacBatteryCore/BundleResolver.swift), and [database](https://github.com/MuratDugan/openmacbattery/blob/main/Sources/OpenMacBatteryCore/Database.swift). This implementation is original Python code; no source was copied. The study informed identity-safe deltas, batched writes, and explicit measurement limitations. API references: [psutil](https://psutil.readthedocs.io/), [NSWorkspace foreground application](https://developer.apple.com/documentation/appkit/nsworkspace/frontmostapplication), and [Apple's LaunchAgent guide](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html).
