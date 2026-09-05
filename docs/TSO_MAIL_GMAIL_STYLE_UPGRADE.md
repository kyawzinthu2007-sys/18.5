# TSO Mail — Gmail-style mailbox UI upgrade

The Mail tab has been redesigned around a Gmail-style three-column workspace while preserving the existing TSO Mail backend and Resend/Supabase receiving flow.

## Included UI/features
- TSO Mail header with mailbox identity, global mail search, help/settings/app controls.
- Compose button and Gmail-style left navigation.
- Inbox, Sent, Drafts, Spam and Trash folders from the existing database.
- Starred and All Mail virtual views.
- Unread counts and starred counts.
- Primary / Promotions / Social inbox tabs for a familiar Gmail-style presentation.
- Select-all and multi-select message controls.
- Bulk move/delete actions using the existing secure move API.
- Refresh control.
- Local search across sender, address, subject and preview.
- Message reading view with toolbar, sender information, date, reply/forward controls.
- Email details side panel showing sender, recipients, CC, date, subject, mailbox and labels.
- Responsive layout for smaller screens.
- Compose window with To, Cc, Subject, body, formatting controls and Send.
- Existing mail receiving, Resend sending, Supabase storage and security logic are preserved.

## Backend compatibility
The `/api/mail/messages` endpoint now supports the virtual `Starred` and `All Mail` views without changing the existing database schema.

The existing physical folders and message schema remain unchanged.
