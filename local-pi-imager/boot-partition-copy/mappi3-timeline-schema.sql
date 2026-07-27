-- MapPI3 Timeline Recorder schema v1
-- Local SQLite store for Pi-backed offline trip recording. No Supabase/cloud dependency.
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS trips (
  id TEXT PRIMARY KEY,
  route_id TEXT,
  route_name TEXT,
  title TEXT,
  state TEXT NOT NULL DEFAULT 'active',
  started_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  ended_at REAL,
  paused_at REAL,
  resumed_at REAL,
  cumulative_distance_m REAL DEFAULT 0,
  summary_json TEXT NOT NULL DEFAULT '{}',
  route_json TEXT NOT NULL DEFAULT '{}',
  archived INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS gps_samples (
  id TEXT PRIMARY KEY,
  trip_id TEXT NOT NULL,
  timestamp REAL NOT NULL,
  lat REAL,
  lon REAL,
  alt REAL,
  accuracy_m REAL,
  speed_mps REAL,
  track_deg REAL,
  fix_mode INTEGER DEFAULT 0,
  stale INTEGER NOT NULL DEFAULT 0,
  source TEXT DEFAULT 'gpsd',
  raw_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY(trip_id) REFERENCES trips(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sensor_samples (
  id TEXT PRIMARY KEY,
  trip_id TEXT NOT NULL,
  timestamp REAL NOT NULL,
  temp_c REAL,
  humidity REAL,
  pressure_hpa REAL,
  battery_percent REAL,
  charging INTEGER,
  source TEXT DEFAULT 'sensehat',
  raw_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY(trip_id) REFERENCES trips(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS timeline_events (
  id TEXT PRIMARY KEY,
  trip_id TEXT NOT NULL,
  timestamp REAL NOT NULL,
  category TEXT NOT NULL DEFAULT 'note',
  event_type TEXT NOT NULL DEFAULT 'note',
  title TEXT NOT NULL DEFAULT 'Timeline event',
  description TEXT DEFAULT '',
  lat REAL,
  lon REAL,
  source TEXT DEFAULT 'manual',
  severity TEXT DEFAULT 'info',
  hidden INTEGER NOT NULL DEFAULT 0,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  FOREIGN KEY(trip_id) REFERENCES trips(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS timeline_ranges (
  id TEXT PRIMARY KEY,
  trip_id TEXT NOT NULL,
  start_timestamp REAL NOT NULL,
  end_timestamp REAL,
  range_type TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT 'Timeline range',
  description TEXT DEFAULT '',
  severity TEXT DEFAULT 'info',
  source TEXT DEFAULT 'recorder',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  FOREIGN KEY(trip_id) REFERENCES trips(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS media_items (
  id TEXT PRIMARY KEY,
  trip_id TEXT NOT NULL,
  captured_at REAL NOT NULL,
  event_id TEXT,
  media_type TEXT NOT NULL DEFAULT 'photo',
  path TEXT NOT NULL,
  thumbnail_path TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY(trip_id) REFERENCES trips(id) ON DELETE CASCADE,
  FOREIGN KEY(event_id) REFERENCES timeline_events(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_gps_trip_timestamp ON gps_samples (trip_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_sensor_trip_timestamp ON sensor_samples (trip_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_event_trip_timestamp ON timeline_events (trip_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_event_category_timestamp ON timeline_events (trip_id, category, timestamp);
CREATE INDEX IF NOT EXISTS idx_range_trip_start ON timeline_ranges (trip_id, start_timestamp);
CREATE INDEX IF NOT EXISTS idx_media_trip_timestamp ON media_items (trip_id, captured_at);

INSERT OR REPLACE INTO metadata(key, value, updated_at) VALUES ('timeline_schema_version', '1', strftime('%s','now') * 1000);
