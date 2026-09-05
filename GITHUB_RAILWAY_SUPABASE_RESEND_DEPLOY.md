# TSO deployment: GitHub + Railway + Supabase + Resend

## 1. GitHub
Upload the contents of this repository to GitHub. Do not commit `.env`, API keys, passwords, or LLM model weights.

## 2. Supabase
Create a Supabase project and obtain a PostgreSQL connection string. Put it in Railway as `DATABASE_URL`.

The repository includes SQL migrations under `mail_migration/`. The application also creates/updates its required core tables during startup/first request. Run any optional migration SQL in Supabase SQL Editor when its feature is needed.

## 3. Resend
Verify `talentshowoff.com` in Resend, then create a sending API key. Set:

- `RESEND_API_KEY`
- `RESEND_FROM` (for example `Talentshowoff <noreply@talentshowoff.com>`)

## 4. Railway
Create a Railway service from the GitHub repository. Railway detects `railway.json` and uses Gunicorn through `wsgi.py`.

Required variables:

- `DATABASE_URL`
- `TSO_OWNER_PASSWORD`
- `TSO_EDITOR_PASSWORD` (needed for first initialization)
- `APP_BASE_URL`
- `RESEND_API_KEY`
- `RESEND_FROM`

Railway supplies `PORT` automatically.

## 5. Local essay LLM
The TSO essay generator is designed to call an Ollama-compatible local/private inference endpoint. The application code and TSO writing database are included in this repository, but model weights are intentionally NOT included in GitHub.

For Railway production, run the LLM as a separate private Railway service (or another private GPU/CPU host) and set `TSO_LOCAL_LLM_URL` to that service's private URL. Install/download the selected model there, for example `gpt-oss:20b`.

If you do not deploy the LLM service yet, leave `TSO_LOCAL_LLM_FALLBACK=true` so the existing deterministic generator remains available.

## 6. Security
Never put Supabase service-role keys, Resend keys, creator passwords, or model credentials in frontend files or GitHub. Keep all secrets in Railway Variables.
