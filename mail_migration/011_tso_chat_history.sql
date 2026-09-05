-- TSO AI chat/search history: every message either side of the conversation,
-- per signed-in user, so someone can revisit what they previously asked TSO.
-- Anonymous visitors aren't signed in, so nothing is saved for them.
-- The backend also creates this table automatically in init_db().

CREATE TABLE IF NOT EXISTS tso_chat_history (
  id TEXT PRIMARY KEY,
  username_key TEXT NOT NULL,
  role TEXT NOT NULL,
  text TEXT NOT NULL,
  engine TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tso_chat_history_user_time
  ON tso_chat_history(username_key, created_at DESC);
