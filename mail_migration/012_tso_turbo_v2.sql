-- TSO AI Turbo V2: additive memory and project tables.
CREATE TABLE IF NOT EXISTS tso_ai_memory (
  id UUID PRIMARY KEY,
  username_key TEXT NOT NULL,
  memory TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tso_ai_memory_user ON tso_ai_memory(username_key, updated_at DESC);
CREATE TABLE IF NOT EXISTS tso_ai_projects (
  id UUID PRIMARY KEY,
  username_key TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tso_ai_projects_user ON tso_ai_projects(username_key, updated_at DESC);
