CREATE TABLE IF NOT EXISTS follow_subscriptions (
    id TEXT PRIMARY KEY,
    endpoint TEXT NOT NULL UNIQUE,
    subscription TEXT NOT NULL,
    community_id TEXT,
    followed_at INTEGER,
    version INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS follow_subscriptions_community
ON follow_subscriptions (community_id, followed_at);

CREATE TABLE IF NOT EXISTS follow_deliveries (
    subscription_id TEXT NOT NULL REFERENCES follow_subscriptions(id) ON DELETE CASCADE,
    item_id TEXT NOT NULL,
    first_seen INTEGER NOT NULL,
    payload TEXT NOT NULL,
    lease_until INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    delivered_at INTEGER,
    PRIMARY KEY (subscription_id, item_id)
);

CREATE INDEX IF NOT EXISTS follow_deliveries_due
ON follow_deliveries (delivered_at, lease_until, first_seen);
