-- Creator-defined promo codes that users can redeem once each for a
-- one-time TSO coin bonus. Managed from the "Tasks" screen in the creator
-- dashboard, alongside creator-defined tasks.
-- The backend also creates these objects automatically in init_db().

CREATE TABLE IF NOT EXISTS tso_promo_codes (
  code TEXT PRIMARY KEY,
  coins INTEGER NOT NULL,
  max_uses INTEGER,
  uses_count INTEGER NOT NULL DEFAULT 0,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tso_promo_redemptions (
  code TEXT NOT NULL REFERENCES tso_promo_codes(code) ON DELETE CASCADE,
  username_key TEXT NOT NULL,
  redeemed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (code, username_key)
);


-- Per-user Promode/referral codes.
-- A new account using a user's code gives 10 Credit to both accounts.
CREATE TABLE IF NOT EXISTS tso_referral_codes (
    code TEXT PRIMARY KEY,
    owner_username TEXT NOT NULL UNIQUE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tso_referral_codes_owner
    ON tso_referral_codes(owner_username);

CREATE TABLE IF NOT EXISTS tso_referral_redemptions (
    new_username TEXT PRIMARY KEY,
    referral_code TEXT NOT NULL REFERENCES tso_referral_codes(code),
    referrer_username TEXT NOT NULL,
    redeemed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tso_referral_redemptions_referrer
    ON tso_referral_redemptions(referrer_username);
