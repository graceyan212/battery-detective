CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    started REAL NOT NULL,
    ended REAL,
    interval_seconds REAL NOT NULL CHECK (interval_seconds > 0),
    source TEXT NOT NULL CHECK (source IN ('live', 'synthetic'))
);
CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    timestamp REAL NOT NULL,
    monotonic REAL NOT NULL,
    elapsed_seconds REAL CHECK (elapsed_seconds > 0),
    battery_percent REAL CHECK (battery_percent BETWEEN 0 AND 100),
    plugged INTEGER CHECK (plugged IN (0, 1)),
    charging INTEGER CHECK (charging IN (0, 1)),
    voltage_mv INTEGER,
    current_ma INTEGER,
    cycle_count INTEGER,
    cpu_percent REAL CHECK (cpu_percent BETWEEN 0 AND 100),
    memory_percent REAL,
    gap_reason TEXT,
    sensor_errors TEXT,
    inaccessible_processes INTEGER DEFAULT 0,
    observed_processes INTEGER DEFAULT 0,
    duration_ms REAL,
    collector_cpu_seconds REAL,
    collector_rss INTEGER
);
CREATE INDEX IF NOT EXISTS samples_timestamp ON samples(timestamp);
CREATE INDEX IF NOT EXISTS samples_session ON samples(session_id, timestamp);
CREATE TABLE IF NOT EXISTS process_activity (
    sample_id INTEGER NOT NULL REFERENCES samples(id) ON DELETE CASCADE,
    pid INTEGER NOT NULL,
    started REAL NOT NULL,
    name TEXT NOT NULL,
    app_name TEXT,
    bundle_id TEXT,
    cpu_seconds REAL CHECK (cpu_seconds >= 0),
    cpu_percent REAL CHECK (cpu_percent >= 0),
    rss INTEGER,
    read_bytes INTEGER CHECK (read_bytes >= 0),
    write_bytes INTEGER CHECK (write_bytes >= 0),
    PRIMARY KEY (sample_id, pid, started)
);
CREATE TABLE IF NOT EXISTS foreground_activity (
    sample_id INTEGER PRIMARY KEY REFERENCES samples(id) ON DELETE CASCADE,
    pid INTEGER,
    name TEXT,
    bundle_id TEXT
);
CREATE TABLE IF NOT EXISTS anomalies (
    id INTEGER PRIMARY KEY,
    start REAL NOT NULL,
    end REAL NOT NULL,
    threshold REAL NOT NULL,
    details TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS anomalies_time ON anomalies(start, end);
PRAGMA user_version = 1;
