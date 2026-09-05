# TSO AI Turbo V2

This upgrade adds new Turbo V2 features. An earlier build of this upgrade
also silently dropped several existing Turbo Research/Agent features while
claiming to be fully additive — that regression has been corrected in this
version. See "Corrected in this build" below for what that means for you.

## Added
- ⚡ Deep Research endpoint and UI: searches multiple query angles, deduplicates sources, then synthesizes a research brief.
- 🧠 User-controlled AI Memory: signed-in Turbo users can add and delete memories; relevant memories are supplied to Turbo only when available.
- 📁 Turbo Projects: create/delete lightweight project contexts for study, work and research organization.
- 🌅 **Daily Brief** (`GET /api/turbo/brief`): a short, priority-ordered digest for the signed-in Turbo user, in the spirit of the Gemini app's Daily Brief. Pulls together, and ranks by relevance: newly-posted jobs that match the user's bio/saved memories (highest priority), any newly-posted jobs generally, their least-recently-updated Project, and their Turbo subscription status. Gemini writes a 2–4 sentence natural-language summary leading with the most useful item when available; falls back to a plain-text summary of the top item if Gemini is unavailable. No new tables — reads from existing jobs/memory/projects/subscription data.
- 🗺️ **Visualize** (`POST /api/turbo/visualize`): turns a concept, process, or comparison into a small interactive diagram, in the spirit of the Gemini app's Visualize feature. Gemini returns structured node/edge JSON (a left-to-right flow for processes, or a radial concept map for relationships); the frontend renders it as a tappable inline SVG diagram (`DiagramView`) — each node reveals a one-line note on tap. No image generation involved, so it stays fast and text-cheap. Requires Gemini; no offline fallback (a diagram can't be built deterministically from a bare topic string the way research/job-match can).
- 🇲🇲 **Translate** (`POST /api/turbo/translate`): English ⇄ Myanmar translation built around the two gaps Myanmar users most commonly report with general AI translators — wrong formality/register and no way to sanity-check the phrasing. Requests one of three formality levels (formal/polite/casual); Gemini selects correct sentence-final particles and honorifics for that register, returns an alternate phrasing, and a short explanation of the register/particle choices. Any Burmese output is additionally proofread with TSO's own conservative offline spelling checker (`edu_app.myanmar_spelling`, previously only wired into TSO Edu) before being returned — a local-language quality pass general translators have no equivalent of. Requires Gemini; no offline fallback (translation quality/register selection isn't something the deterministic tools can do).
- Turbo V2 tools panel in the TSO AI page (calculator, unit converter, text stats, writing-level checker, prompt templates, keyword-based job match), now with dedicated Daily Brief, Visualize, and Translate tabs alongside Research/Memory/Projects.
- Source links are shown for Deep Research results.
- New database migration: `mail_migration/012_tso_turbo_v2.sql`.

## Corrected in this build
An earlier V2 build removed the following without documenting it. They have
been restored here, and now coexist with the new Turbo V2 tools above:
- The `researchMode` request parameter on `/api/ai/chat` and its UI (the
  "⚡ Turbo Research" mode picker: Quick / Research / Deep), which is
  separate from the newer `/api/turbo/research` panel endpoint.
- The Turbo Research pipeline (`run_turbo_research` and helpers):
  multi-angle query expansion, source ranking, and cross-source conflict
  detection — richer than the single-pass version the new endpoint uses.
- The auto-comparison agent (`run_turbo_comparison`): detects "compare X
  vs Y" / "X vs Y" style requests inside `researchMode` chat and returns a
  structured comparison table with a confidence signal per subject.
- The AI-scored job-match agent (`run_turbo_job_match`): detects
  job-seeking intent in `researchMode` chat and returns a weighted,
  reasoned Job / Match / Reason table (title and category weighted above
  description). This is distinct from the new `/api/turbo/tools`
  `job_match` action, which is a simpler unweighted keyword-overlap tool
  usable outside chat.
- The `TSOAIRichText` frontend component, which renders markdown-style
  tables and lists from Turbo Agent replies as real HTML. Required for the
  comparison and job-match tables above to display correctly rather than
  as raw `| a | b |` text.

## Compatibility / preservation
- Existing files were retained.
- Existing Turbo subscriptions, payment review, chat history, Neo, image generation, Edu, mail and job-board functionality were not removed.
- New database tables are additive and use `CREATE TABLE IF NOT EXISTS`.
- If Gemini is unavailable, Deep Research falls back to the existing local search reply builder.

# TSO AI 3D character (Aug 2026 upgrade)
- Replaced `tso-ai-robot.glb` with a higher-detail character sculpt (deduplicated from a source export containing 8 identical copies; 4K textures compressed to 1K — 56MB source down to 5MB shipped) — see `enhance_glb_v2_character.py` for the full pipeline writeup.
- Rigged as two nodes (Body root, Head child pivoting at the neck) rather than full skeletal skinning — the source mesh has no separable arm/eyelid/jaw geometry, so a real skin/weight-paint rig wasn't achievable non-destructively.
- All 6 animation clips the frontend already calls (Idle, Wave, Talk, Happy, Smile, Wink) are present, expressed through head-tilt/timing/whole-body motion rather than facial or hand animation given the geometry constraint above. No frontend animation-triggering code changed.

# Account security (Aug 2026 upgrade)
- **Two-factor authentication**: users can require a second step at sign-in — either an authenticator app (TOTP, RFC 6238, compatible with Google Authenticator/Authy/1Password) or an emailed 6-digit code. TOTP setup shows a scannable QR code (rendered as inline SVG by a from-scratch stdlib-only QR encoder — no third-party QR service ever sees the secret) plus the raw secret for manual entry. 10 single-use backup codes are issued when 2FA is turned on, shown once, stored hashed (SHA-256) like passwords, individually consumed and regenerable.
- Sign-in (`/api/auth/signin`) now returns `requiresTwoFactor` + a short-lived challenge id instead of a session token when 2FA is on; `/api/auth/2fa/verify` exchanges a valid code for the actual session. No session is ever issued on a password check alone for a 2FA-protected account.
- **Session token hashing**: session tokens are now SHA-256 hashed before being stored (previously stored in plaintext) — a read-only leak of the `sessions` table no longer hands out directly-usable live tokens. This invalidates all sessions that existed before this change ships; every signed-in user needs to sign in again once.
- **Login alerts**: an email is sent on every successful sign-in (toggleable per-account via `/api/auth/login-alerts`, on by default).
- **Active session management**: `/api/auth/sessions` lists an account's active sessions; `/api/auth/sessions/revoke-others` signs out every session except the current one.
- **Rate limiting**: both password sign-in and 2FA code verification are rate-limited (8 attempts per 15-minute window, then a 15-minute lockout), tracked in a dedicated DB table rather than in-process memory so it holds up across multiple worker processes.
- New tables: `two_factor_challenges`, `auth_rate_limits` — see `mail_migration/013_tso_security.sql`.
