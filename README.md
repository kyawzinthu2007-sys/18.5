# Talentshowoff Job Board — GitHub + Railway + Supabase + Resend

This project deploys from GitHub to Railway. Persistent data is stored in
Supabase PostgreSQL. Resend handles verification and application emails.

## Repository layout

Upload the **contents** of this folder (not the folder itself) to the root
of your GitHub repo:

```
Procfile               # tells Railway/gunicorn how to start the app
railway.json            # Railway build/deploy config (Nixpacks)
requirements.txt         # single source of truth for Python deps
start.sh / start-windows.bat
.env.example             # placeholder values only — never commit real secrets
.gitignore
.gitattributes            # forces LF line endings on text files (prevents corruption)
README.md

backend/
  app.py                  # Flask app — all routes + Supabase logic

frontend/
  index.html               # the whole React app (Babel-in-browser, no build step)
  logo.jpg
  tso-ai-robot.glb          # 3D character model for the TSO AI assistant widget

mail_migration/
  001_mail_schema.sql
  003_job_post_viewers.sql
  004_registered_only_job_views.sql
  005_tso_coins.sql
  006_job_post_moderation.sql
  007_tso_custom_tasks.sql

docs/
  DEPLOYMENT.md
  README_FULL_UPDATE.txt
  REGISTERED_ONLY_JOB_VIEWS.md
  UNIFIED_LOGIN_MAIL_SECURITY_UPDATE.md
```

Do not commit a real `.env` file or any API keys/passwords.

## How to upload correctly

`frontend/index.html` is one large file (~2,100 lines, no line breaks inside
the script logic in places). GitHub's drag-and-drop **Upload files** page can
silently fail to save changes if you navigate away before clicking the green
**"Commit changes"** button at the bottom of the page — the file can look
uploaded in the UI without actually being committed. After uploading:

1. Scroll to the bottom of the upload page and click **Commit changes**.
2. Refresh the repo's main page and confirm the commit count increased.
3. Open `frontend/index.html` in GitHub and confirm it ends with:
   `root.render(<App />);` followed by `</script>`.

## Environment variables

Set these in Railway → your service → **Variables** (never in a Dockerfile
or committed file):

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | Yes | Supabase Postgres session pooler URL |
| `TSO_OWNER_PASSWORD` | Yes | Password for the `tsoofficial` creator account |
| `TSO_EDITOR_PASSWORD` | Yes (first boot only) | Password for the built-in `pageadmin` account |
| `RESEND_API_KEY` | Yes | For verification/application emails |
| `RESEND_FROM` | Yes | e.g. `Talentshowoff <noreply@talentshowoff.com>` |
| `APP_BASE_URL` | Yes | e.g. `https://talentshowoff.com` |
| `GOOGLE_CLIENT_ID` | Optional | Enables Google Sign-In |
| `TSO_LOCAL_LLM_URL` | Optional | Ollama-compatible private/local endpoint used by the Edu essay generator. |
| `TSO_LOCAL_LLM_MODEL` | Optional | Local model name, default `gpt-oss:20b`. |
| `TSO_LOCAL_LLM_TIMEOUT` | Optional | Local generation timeout in seconds. |
| `TSO_LOCAL_LLM_FALLBACK` | Optional | `true` keeps the deterministic generator available if the local model is unavailable. |
| `GROQ_API_KEY` | Optional | Enables the separate TSO AI/Turbo assistant features. |
| `GROQ_REASONING_MODEL` | Optional | Normal TSO AI model; defaults to `openai/gpt-oss-20b`. |
| `GROQ_TURBO_MODEL` | Optional | Turbo model; defaults to `openai/gpt-oss-120b`. |
| `GROQ_VISION_MODEL` | Optional | Image understanding model; defaults to `qwen/qwen3.6-27b`. |
| `GROQ_ENABLE_CODE` | Optional | `true` enables Groq hosted code execution for supported GPT-OSS models. |
| `RUNPOD_ENDPOINT_ID` | Optional (not set up yet) | Recommended path for TSO AI's image generation feature — our own self-hosted Stable Diffusion worker (`image_service/`, see its README), run on GPU compute we rent. Pay-per-second, no idle cost, no shared-quota limits |
| `RUNPOD_API_KEY` | Optional (not set up yet) | Your RunPod API key, used to call the endpoint above |
| `HF_API_TOKEN` | Optional | Lightweight fallback image generation backend via Hugging Face's routed Inference Providers, only used if RunPod isn't set up. Free HF accounts get well under $0.10/month of image credit before being blocked — fine for a quick test, not a real production path |
| `MAIL_SUPABASE_URL` / `MAIL_SUPABASE_SERVICE_ROLE_KEY` | Optional | Separate Supabase project for the Mail tab |
| `MAIL_INBOUND_WEBHOOK_SECRET` | Optional | Secures the Resend inbound webhook |
| `GITHUB_TOKEN` | Optional | Fine-grained GitHub token with repository Contents read/write permission for the Feature Scout review-branch workflow |
| `GITHUB_REPO` | Optional | Repository in `owner/repository` form used by Feature Scout |
| `GITHUB_BASE_BRANCH` | Optional | Preferred base branch; defaults to `main`, but Feature Scout automatically falls back to the repository's actual default branch if `main` does not exist |

Railway provides `PORT` automatically — don't set it manually.

**Every request, including the homepage, checks that `DATABASE_URL`,
`TSO_OWNER_PASSWORD`, and (on first boot) `TSO_EDITOR_PASSWORD` are set.**
If any are missing, the server returns an error response instead of the
page — this is the most common cause of a blank/white screen in production.

## User sign-in

Users sign in with their Talentshowoff email address, not their internal
username:

```
yourname@talentshowoff.com
Password: account password
```

The sign-up email may be Gmail or another valid address, used for
verification/recovery. Google Sign-In is available when `GOOGLE_CLIENT_ID`
is configured.

## Creator accounts

- **Main creator** — Username: `tsoofficial`, password: the value of
  `TSO_OWNER_PASSWORD`.
- **Built-in editor** — Username: `pageadmin`, password: the value of
  `TSO_EDITOR_PASSWORD` at first database initialization.

Passwords are never stored in this repository. Additional creator accounts
are managed by the main creator through the Creator management screen.

## Database

Tables are created automatically on first request. No manual setup needed.
Data lives in Supabase, not Railway's ephemeral filesystem, so deploys and
restarts don't erase it.

## Local Windows test

Install Python, set the required environment variables (especially
`DATABASE_URL`, `TSO_OWNER_PASSWORD`, `TSO_EDITOR_PASSWORD`), then run
`start-windows.bat` or:

```
python backend/app.py
```

Serves on `http://localhost:5000` by default.

## TSO AI assistant, 3D character, and tasks

- The floating "TSO AI" chat widget now renders TSO as an interactive 3D
  character (`frontend/tso-ai-robot.glb`, shown with Google's
  `<model-viewer>`) instead of only the flat SVG mascot. If the model fails
  to load for any reason, the widget automatically falls back to the
  original animated SVG mascot, so the assistant is never broken.
- TSO's built-in greeting matcher recognizes a much wider set of hellos
  ("hi", "hey", "yo", "good morning", etc.) using whole-word matching, and
  replies conversationally to whatever the visitor or creator types next,
  using the Groq-backed upgrade when `GROQ_API_KEY` is set and falling back
  to the built-in FAQ/keyless responder otherwise.
- The creator dashboard's **Tasks** menu (previously "TSO Coins") now
  combines: giving TSO coins directly to a registered user, and creating,
  pausing, or deleting custom tasks that any signed-in user can claim once
  from their own Tasks & Rewards page for a coin reward you choose.

## Job-post moderation and security

- Registered-user job posts are created as `pending` and are **not publicly visible** until a creator/admin approves them.
- The creator moderation queue can approve or reject submissions. Rejected submissions stay hidden and the original 2 TSO coin posting fee is refunded once.
- Existing posts without an approval status are treated as approved for backward compatibility.
- The server adds security headers, lightweight per-route abuse throttling, strict authorization checks, and no-store API responses.
- Browser-side copy, context-menu, print, common developer-tool shortcuts, drag/export actions, and visibility changes are blocked/deterred where the browser permits. **A normal website cannot technically guarantee prevention of screenshots made by the OS, another device, browser extensions, accessibility tools, or third-party capture software.**
- Keep Railway HTTPS enabled and never expose passwords/API keys in client-side code or committed files.

## Security

- Passwords are hashed before creator accounts are stored in PostgreSQL.
- Production secrets come only from environment variables, set in Railway's
  dashboard — never in a Dockerfile `ARG`/`ENV`, never committed to git.
- No default creator passwords are embedded in the application.


## SEO features

The site now includes:
- `/robots.txt` with a sitemap reference and API/admin crawl rules.
- `/sitemap.xml`, generated from publicly approved job posts.
- Crawlable `/jobs/<job-id>` pages with unique title, meta description, canonical URL, Open Graph metadata and Schema.org `JobPosting` structured data.
- Improved homepage title, description, keywords and crawl directives.
- Shareable job URLs in the React frontend.

Set `APP_BASE_URL=https://talentshowoff.com` in Railway so sitemap, canonical URLs and structured-data URLs use the custom domain. After deployment, verify:
`https://talentshowoff.com/robots.txt`
`https://talentshowoff.com/sitemap.xml`
and a published job at `https://talentshowoff.com/jobs/<job-id>`.


## TSO Edu language switch

TSO Edu now includes an **English / မြန်မာ** language switch in the Edu header.
- English mode keeps the existing English essay generator and analysis dashboard.
- Myanmar mode keeps the same generation/analyse settings but generates Myanmar-language စာစီစာကုံး and uses a Myanmar-language offline analysis profile.
- The selected language is remembered in the browser for the next Edu visit.
- The API accepts `language: "en"` or `language: "my"` for both analysis and essay generation.

- Edu navigation now shows only the English/Myanmar language switch. Essay/Debate mode is hidden in English and appears inside the page only when Myanmar language is selected.

## TikTok Myanmar Job Collector
The creator dashboard now includes **TikTok Jobs**. It supports authorized manual TikTok URL/caption/transcript import plus optional automatic Myanmar public-video search through TikTok's approved Research API. Imported posts use the same TSO AI scam-risk gate and normalized job publishing workflow as Facebook. See `TIKTOK_JOB_COLLECTOR.md` and migration `mail_migration/015_tiktok_job_collector.sql`.


## TSO Feature Scout

Creator accounts now have a **Feature Scout** screen. It can:

1. Search public web results for a product/feature topic, or inspect public URLs supplied by the creator.
2. Respect `robots.txt` where available and use a small, rate-limited public-page fetcher.
3. Extract only product-level signals such as headings, buttons, page titles and public links.
4. Ask TSO AI to identify useful feature ideas that are not already present in Talentshowoff.
5. Store each idea as a creator-review proposal.
6. Generate an independent implementation draft after the creator reviews the idea.
7. Let the creator **Approve**, **Reject**, or **Add to build queue**.

The Feature Scout deliberately does **not** copy another site's source code, private content,
credentials, cookies, protected pages, exact branding, or assets. Approval is required before
a proposal enters the build queue; production deployment is not performed automatically by
the scout. This prevents a web research agent from silently changing the live job board.

Optional environment variables:

| Variable | Default | Purpose |
|---|---:|---|
| `FEATURE_SCOUT_USER_AGENT` | `TalentshowoffFeatureScout/1.0 (+https://talentshowoff.com)` | User-Agent used for public research |
| `FEATURE_SCOUT_TIMEOUT` | `12` | Public request timeout in seconds |
| `FEATURE_SCOUT_MAX_PAGES` | `5` | Maximum pages inspected per scan |
| `FEATURE_SCOUT_MAX_CHARS` | `18000` | Maximum extracted research payload |

`GROQ_API_KEY` is required to generate AI analysis and implementation drafts.

## Receiving Gmail -> Talentshowoff Mail

The Mail inbox uses Resend Receiving. Resend sends an `email.received` webhook with metadata and the app then retrieves the full received email from the Resend Receiving API before saving it to the creator Inbox.

Required production variables:
- `MAIL_SUPABASE_URL`
- `MAIL_SUPABASE_SERVICE_ROLE_KEY`
- `MAIL_DOMAIN` (for example `talentshowoff.com`)
- `RESEND_API_KEY`
- `MAIL_INBOUND_WEBHOOK_SECRET` (optional legacy app secret; if used, configure the same value on the webhook request)

In Resend, enable Receiving for the domain and create a webhook for `email.received` pointing to:
`https://YOUR-DEPLOYED-DOMAIN/api/mail/inbound`

For a custom receiving domain, its MX record must point to the Resend receiving MX target shown in the Resend dashboard. If the root domain already has MX records for another mail provider, use a dedicated receiving subdomain instead of replacing the existing MX records. Resend stores received mail even when the webhook is temporarily unavailable, so failed webhook deliveries can be replayed from the Resend dashboard.


## TSO AI / TSO Turbo AI — modern assistant engine

TSO AI (Neo) and TSO Turbo AI use Groq's modern Responses stack. Neo uses `GROQ_REASONING_MODEL`; Turbo uses `GROQ_TURBO_MODEL`.
and the same conversation/multimodal pipeline with native web search. The app
keeps its existing Groq and keyless local fallbacks, so removing the OpenAI key
does not delete the previous functionality.

Capabilities added to the provider layer:
- Multi-turn conversation history
- Image and file understanding from chat attachments
- Native web search grounding instead of relying only on scraped snippets
- Optional hosted code execution via `GROQ_ENABLE_CODE=true`
- Existing TSO memory, projects, Turbo Research, translation, visualization,
  job matching, image generation, mail and Edu features remain intact

This does not copy or expose ChatGPT's private system instructions; it gives TSO
a comparable application architecture using public API capabilities. API usage
is billed separately by the provider.


## TSO Edu ChatGPT Essay Generation
The Edu `/edu/api/generate-essay` endpoint uses the OpenAI Responses API. Configure `OPENAI_API_KEY`; see `docs/TSO_EDU_CHATGPT_ESSAY_GENERATION.md`.
