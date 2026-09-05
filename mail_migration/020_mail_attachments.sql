-- ============================================================
-- TalentShowoff Mail — real file attachments
-- Run this in the MAIL Supabase project's SQL Editor.
--
-- File bytes live in Supabase Storage (bucket "mail-attachments",
-- created below via storage.buckets — private, service-role only,
-- consistent with how the rest of this schema relies on RLS + the
-- backend's service-role key rather than public bucket policies).
-- This table stores metadata and links an attachment to either a
-- message already sent/received, or (while composing) just to the
-- uploading mailbox before the message exists yet.
-- ============================================================

CREATE TABLE IF NOT EXISTS public.mail_attachments (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    mailbox_id      uuid NOT NULL REFERENCES public.mailboxes(id) ON DELETE CASCADE,
    message_id      uuid REFERENCES public.messages(id) ON DELETE CASCADE,
    filename        text NOT NULL,
    content_type    text NOT NULL DEFAULT 'application/octet-stream',
    size_bytes      bigint NOT NULL,
    storage_path    text NOT NULL UNIQUE,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mail_attachments_message
    ON public.mail_attachments (message_id);
CREATE INDEX IF NOT EXISTS idx_mail_attachments_mailbox_unlinked
    ON public.mail_attachments (mailbox_id) WHERE message_id IS NULL;

ALTER TABLE public.mail_attachments ENABLE ROW LEVEL SECURITY;
-- No public policies: only the backend's service-role key can access this
-- table, same as mailboxes/folders/messages above.

-- Private storage bucket for the actual file bytes. Private (not public) —
-- the backend downloads bytes server-side via the service-role key and
-- streams them to the user, so no attachment URL is ever publicly guessable.
INSERT INTO storage.buckets (id, name, public)
VALUES ('mail-attachments', 'mail-attachments', false)
ON CONFLICT (id) DO NOTHING;
