-- Resend inbound email reliability upgrade.
-- Prevents webhook retries from creating duplicate Inbox messages.
create unique index if not exists idx_messages_mailbox_message_uid
  on public.messages (mailbox_id, message_uid)
  where message_uid is not null;
