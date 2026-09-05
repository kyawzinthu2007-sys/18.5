-- Creator-defined TSO coin tasks, in addition to the built-in daily login
-- reward. Managed from the "Tasks" screen in the creator dashboard.
-- The backend also creates these objects automatically in init_db().

CREATE TABLE IF NOT EXISTS tso_custom_tasks (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  reward INTEGER NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tso_task_claims (
  task_id TEXT NOT NULL REFERENCES tso_custom_tasks(id) ON DELETE CASCADE,
  username_key TEXT NOT NULL,
  claimed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (task_id, username_key)
);
