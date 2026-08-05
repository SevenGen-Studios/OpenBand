CREATE TABLE IF NOT EXISTS analytics_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  received_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  occurred_at TEXT NOT NULL,
  page TEXT NOT NULL,
  event_name TEXT NOT NULL,
  community_id TEXT,
  fiscal_year TEXT,
  session_id TEXT NOT NULL,
  visitor_id TEXT NOT NULL,
  country TEXT NOT NULL DEFAULT 'Unknown',
  province TEXT NOT NULL DEFAULT 'Unknown',
  device_type TEXT NOT NULL,
  browser TEXT NOT NULL,
  referrer TEXT NOT NULL,
  parameters_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_analytics_time ON analytics_events(occurred_at);
CREATE INDEX IF NOT EXISTS idx_analytics_event_time ON analytics_events(event_name, occurred_at);
CREATE INDEX IF NOT EXISTS idx_analytics_visitor_time ON analytics_events(visitor_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_analytics_session_time ON analytics_events(session_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_analytics_community_time ON analytics_events(community_id, occurred_at);

CREATE TABLE IF NOT EXISTS analytics_rate_limits (
  bucket TEXT PRIMARY KEY,
  event_count INTEGER NOT NULL,
  expires_at TEXT NOT NULL
);
