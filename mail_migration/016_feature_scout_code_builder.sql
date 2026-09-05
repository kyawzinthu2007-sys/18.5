-- Feature Scout implementation builder upgrade.
-- Safe to run repeatedly; app.py also applies these columns automatically.
ALTER TABLE tso_feature_scout_proposals
  ADD COLUMN IF NOT EXISTS code_plan JSONB;
ALTER TABLE tso_feature_scout_proposals
  ADD COLUMN IF NOT EXISTS github_result JSONB;
ALTER TABLE tso_feature_scout_proposals
  ADD COLUMN IF NOT EXISTS build_error TEXT;
