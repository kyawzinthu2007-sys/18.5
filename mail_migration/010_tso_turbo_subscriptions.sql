-- Turbo search engine subscriptions: manual mobile-money (KBZ Pay / UAB Pay /
-- AYA Pay) monthly or yearly top-ups reviewed by a creator before Turbo
-- access is activated. Mirrors 009_tso_credit_purchases.sql's shape.
-- The backend also creates these tables automatically in init_db().

CREATE TABLE IF NOT EXISTS tso_turbo_purchases (
  id TEXT PRIMARY KEY,
  username_key TEXT NOT NULL,
  plan_id TEXT NOT NULL,
  days INTEGER NOT NULL,
  price_kyat INTEGER NOT NULL,
  payment_method TEXT NOT NULL,
  screenshot TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  reviewed_by TEXT,
  reviewed_at TIMESTAMPTZ,
  rejection_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tso_turbo_purchases_user_time
  ON tso_turbo_purchases(username_key, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_tso_turbo_purchases_status
  ON tso_turbo_purchases(status, created_at DESC);

CREATE TABLE IF NOT EXISTS tso_turbo_subscriptions (
  username_key TEXT PRIMARY KEY,
  expires_at TIMESTAMPTZ NOT NULL
);
