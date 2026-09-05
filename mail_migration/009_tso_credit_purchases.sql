-- Credit purchase requests: manual mobile-money (KBZ Pay / UAB Pay / AYA
-- Pay) top-ups reviewed by a creator before Credit is granted.
-- The backend also creates this table automatically in init_db().

CREATE TABLE IF NOT EXISTS tso_credit_purchases (
  id TEXT PRIMARY KEY,
  username_key TEXT NOT NULL,
  package_id TEXT NOT NULL,
  credit_amount INTEGER NOT NULL,
  price_kyat INTEGER NOT NULL,
  payment_method TEXT NOT NULL,
  screenshot TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  reviewed_by TEXT,
  reviewed_at TIMESTAMPTZ,
  rejection_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tso_credit_purchases_user_time
  ON tso_credit_purchases(username_key, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_tso_credit_purchases_status
  ON tso_credit_purchases(status, created_at DESC);
