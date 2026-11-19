CREATE TABLE IF NOT EXISTS creator_donations (
  session_id TEXT PRIMARY KEY NOT NULL,
  livemode INTEGER NOT NULL CHECK (livemode IN (0, 1)),
  amount_cents INTEGER NOT NULL CHECK (amount_cents BETWEEN 200 AND 99999999),
  created_at INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'paid', 'failed', 'expired')),
  paid_at INTEGER,
  payment_intent TEXT UNIQUE,
  CHECK (status <> 'paid' OR (paid_at IS NOT NULL AND payment_intent IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS creator_donations_recent
  ON creator_donations (livemode, COALESCE(paid_at, created_at) DESC, session_id DESC);

-- A refund webhook can arrive before the associated Checkout webhook.
CREATE TABLE IF NOT EXISTS creator_refunds (
  refund_id TEXT PRIMARY KEY NOT NULL,
  payment_intent TEXT NOT NULL,
  livemode INTEGER NOT NULL CHECK (livemode IN (0, 1)),
  amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
  status TEXT NOT NULL CHECK (status IN ('pending', 'requires_action', 'succeeded', 'failed', 'canceled'))
);
CREATE INDEX IF NOT EXISTS creator_refunds_intent ON creator_refunds (payment_intent, livemode);

CREATE VIEW IF NOT EXISTS creator_donation_totals AS
SELECT d.*,
  MIN(d.amount_cents, COALESCE(SUM(CASE WHEN r.status = 'succeeded' THEN r.amount_cents END), 0)) AS refunded_cents,
  COALESCE(MAX(r.status IN ('pending', 'requires_action')), 0) AS refund_pending,
  COALESCE(MAX(r.status IN ('failed', 'canceled')), 0) AS refund_failed
FROM creator_donations d
LEFT JOIN creator_refunds r ON r.payment_intent = d.payment_intent AND r.livemode = d.livemode
GROUP BY d.session_id;
