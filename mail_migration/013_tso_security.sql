-- TSO account security: two-factor authentication challenges and login
-- rate limiting. Both additive (init_db() already creates these
-- CREATE TABLE IF NOT EXISTS on every boot, same as prior migrations —
-- this file exists purely as a readable record of the schema change).
--
-- Note: this release also changes what's stored in the existing `sessions`
-- table (session tokens are now SHA-256 hashed before storage instead of
-- stored in plaintext) — no schema change for that fix, but every
-- currently-active session becomes invalid the moment this ships, since a
-- plaintext token can no longer match a hashed lookup. This is intentional:
-- there is no way to migrate old plaintext tokens forward without briefly
-- re-exposing them, so the safe choice is to invalidate them and let users
-- sign in again.
CREATE TABLE IF NOT EXISTS two_factor_challenges (
  challenge_id TEXT PRIMARY KEY,
  username_key TEXT NOT NULL,
  method TEXT NOT NULL,
  email_code_hash TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_2fa_challenges_expires ON two_factor_challenges(expires_at);

CREATE TABLE IF NOT EXISTS auth_rate_limits (
  rate_key TEXT PRIMARY KEY,
  attempts INTEGER NOT NULL DEFAULT 0,
  window_start TIMESTAMPTZ NOT NULL DEFAULT now(),
  locked_until TIMESTAMPTZ
);
