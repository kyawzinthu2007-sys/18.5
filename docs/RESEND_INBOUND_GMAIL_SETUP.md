# Gmail -> Talentshowoff Mail Receiving Setup

## What was fixed

Resend `email.received` webhooks do not contain the email body. They contain metadata inside `data`, including `email_id`, `from`, `to`, `subject`, and `message_id`. The backend now reads the nested event correctly and uses the Resend Receiving API to retrieve the full HTML/text message before inserting it into the creator Inbox.

Webhook retries are also deduplicated using the Resend `message_id`.

## Required environment variables

```env
RESEND_API_KEY=re_xxxxxxxxx
MAIL_SUPABASE_URL=https://YOUR-MAIL-PROJECT.supabase.co
MAIL_SUPABASE_SERVICE_ROLE_KEY=YOUR_MAIL_SERVICE_ROLE_KEY
MAIL_DOMAIN=talentshowoff.com
```

Optional:

```env
MAIL_INBOUND_WEBHOOK_SECRET=YOUR_PRIVATE_WEBHOOK_SECRET
```

## Resend configuration

1. Open Resend -> Emails -> Receiving.
2. Enable a receiving domain/address.
3. For `talentshowoff.com`, configure the MX record required by Resend.
4. Open Resend -> Webhooks.
5. Add a webhook endpoint:
   `https://YOUR_DEPLOYED_DOMAIN/api/mail/inbound`
6. Select `email.received`.
7. Send a test email from Gmail to a mailbox such as `tsoofficial@talentshowoff.com`.

## Important DNS note

If `talentshowoff.com` already has MX records for another mailbox provider, do not blindly replace them. Resend recommends using a receiving subdomain in that situation, or configuring forwarding through the existing mail provider. A custom domain can receive mail only when its MX routing is configured for Resend.

## Expected flow

Gmail -> DNS MX -> Resend Receiving -> `email.received` webhook -> `/api/mail/inbound` -> Resend Receiving API -> Mail Supabase -> Creator Inbox.
