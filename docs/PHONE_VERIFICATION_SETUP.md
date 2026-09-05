# Talentshowoff Phone Verification Setup

The authentication flow now requires a verified phone number for new accounts and for Google accounts that do not already have a verified phone number.

## SMS provider

Phone OTP delivery uses Twilio's REST API without an additional Python dependency.
Set these environment variables in Railway/Render (or your local environment):

- `SMS_PROVIDER=twilio`
- `TWILIO_ACCOUNT_SID=...`
- `TWILIO_FROM_NUMBER=+...`
- Either `TWILIO_AUTH_TOKEN=...` **or** the pair `TWILIO_API_KEY_SID=...` + `TWILIO_API_KEY_SECRET=...`

`TWILIO_ACCOUNT_SID` is required in both cases (it identifies the account in
the API URL). The Auth Token is the simplest option and is found on the main
Console dashboard. An API Key/Secret is created separately under **Account →
API keys & tokens → Create API key** and is preferable for production
because it can be revoked individually without rotating the account's main
Auth Token. If both are set, the API Key takes priority.

The Twilio sending number must be permitted to send SMS to the countries you support. Keep all secrets private and never put them in frontend code.

## Telegram Gateway (optional, tried before SMS)

If `TELEGRAM_GATEWAY_TOKEN` is set, every phone OTP first attempts delivery
via Telegram's official Gateway API (https://core.telegram.org/gateway)
before falling back to Twilio SMS. Telegram delivery is typically faster and
cheaper than SMS, but only reaches numbers that have a Telegram account — the
fallback to Twilio is automatic and requires no extra logic per call site.

- `TELEGRAM_GATEWAY_TOKEN=...` — from https://gateway.telegram.org, after
  logging in with your Telegram account and funding the balance. Sending
  codes to your own phone number there is free, so you can test the whole
  flow before it costs anything.
- `TELEGRAM_GATEWAY_SENDER=...` — optional. A verified sender username shown
  to recipients, if you've set one up in the Gateway dashboard. Leave unset
  to use Telegram's default sender.

Leaving `TELEGRAM_GATEWAY_TOKEN` unset disables this path entirely — the app
falls back to the previous Twilio-only behavior with no other changes
required.

## User flows

### Manual account creation
1. User enters display name, email, phone number, date of birth and the remaining account fields.
2. Talentshowoff sends an email verification link and a 6-digit SMS OTP.
3. User verifies the phone with the OTP.
4. User opens the email verification link.
5. The account can then sign in.

### Google sign-in
If the Google account is already linked and has a verified phone, sign-in continues normally.
If the Google account has no verified phone, Talentshowoff asks for a phone number, sends an SMS OTP, and does not issue a session until the OTP is verified.

### Existing accounts
Accounts created before this update that do not have a verified phone are prompted to add and verify a phone number on their next password sign-in.

## Security

- OTPs are stored only as hashes in the existing `two_factor_challenges` table.
- Codes expire after 10 minutes.
- Verification attempts are rate-limited.
- Phone numbers are normalized with `phonenumbers` before storage.
- A phone number cannot be linked to multiple user accounts.


## New-account delivery behavior

Manual account creation now starts the phone verification challenge before the email verification request. This guarantees that new-account phone verification uses the exact same `issue_phone_verification()` delivery path as existing registered accounts: Telegram Gateway is attempted first when `TELEGRAM_GATEWAY_TOKEN` is configured, and Twilio SMS is used as the fallback.

The new account is not discarded when email delivery temporarily fails after the phone code has been sent. The phone challenge remains valid and the user can verify the phone first, then resend the email verification.
