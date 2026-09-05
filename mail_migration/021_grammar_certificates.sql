-- ============================================================
-- TSO Edu Grammar Academy — issued certificate registry.
-- Run this in the MAIN TSO Supabase project's SQL Editor (the same
-- project that holds the `users` table) — NOT the mail project.
--
-- Certificates were previously stored only inside each user's
-- `users.data -> 'tsoEduGrammar' -> 'certificate'` JSONB blob, which works
-- for a signed-in user checking their own certificate but cannot support
-- a public verification lookup by certificate ID alone (that would
-- require scanning every user's row). This table is the source of truth
-- for public verification; the JSONB copy on the user's row can stay as
-- a convenience cache for "my certificate" UI, but this table is what
-- /verify/<cert_id> actually checks against.
-- ============================================================

CREATE TABLE IF NOT EXISTS public.grammar_certificates (
  cert_id             text PRIMARY KEY,
  username_key        text NOT NULL,
  student_name        text NOT NULL,
  verification_code   text NOT NULL,
  course_title         text NOT NULL DEFAULT 'Grammar Academy — Full Curriculum',
  lessons_completed    integer NOT NULL,
  final_exam_score     numeric NOT NULL,
  completion_date      date NOT NULL,
  completion_time      text NOT NULL,
  issued_at            timestamptz NOT NULL DEFAULT now(),
  revoked              boolean NOT NULL DEFAULT false,
  revoked_reason        text
);

-- One user, one certificate: enforced at the database level (not just in
-- application code) so a race condition or a future code change can never
-- issue a second certificate row for the same username_key. The API layer
-- (edu_api_grammar_certificate_issue) checks for an existing certificate
-- before generating a new one, but this constraint is the real backstop.
CREATE UNIQUE INDEX IF NOT EXISTS idx_grammar_certificates_username_unique
  ON public.grammar_certificates (username_key);

-- Verification lookups are always by cert_id (primary key) + code, so no
-- extra index is needed for the code itself — the code alone should never
-- be queryable without a cert_id, since that would let someone enumerate
-- valid codes.
