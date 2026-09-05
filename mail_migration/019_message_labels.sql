-- ============================================================
-- TalentShowoff Mail — message labels (Work / Personal / Projects)
-- Run this in the MAIL Supabase project's SQL Editor.
-- ============================================================

ALTER TABLE public.messages
  ADD COLUMN IF NOT EXISTS labels text[] NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_messages_labels
  ON public.messages USING gin (labels);
