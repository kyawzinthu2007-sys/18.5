# Adding AI Image Generation to Your Stack (GitHub + Railway + Resend + Supabase)

Your main app already deploys fine as-is: GitHub → Railway (Nixpacks +
Gunicorn), Supabase for the database, Resend for email. None of that
changes. Image generation is the one piece that needs a GPU, and Railway
doesn't offer GPU instances — so that one feature lives on **Modal**
instead, and your Railway app just calls out to it over HTTPS, the same
way it already calls Resend or Groq.

Nothing else in your stack is affected. This is additive.

---

## 1. Deploy the image worker to Modal (one-time, from your own machine)

This step happens on your laptop/dev machine, not in Railway or GitHub —
Modal has its own deploy mechanism, separate from your Railway pipeline.

```bash
pip install modal
modal setup
```

`modal setup` opens a browser and links this machine to a free Modal
account (no credit card required for the free tier).

```bash
cd tso_project/image_service
modal secret create tso-modal-auth MODAL_AUTH_TOKEN=<make up a long random string>
modal run modal_app.py::download_model
modal deploy modal_app.py
```

`download_model` only needs to run once — it downloads the Stable
Diffusion weights into a persistent Modal Volume so they're cached and
ready before your worker ever handles a real request. (Modal's image
build itself runs with network access off, which is why this is a
separate step rather than baked into the image.)

Modal builds the container in the cloud and prints an endpoint URL like:

```
https://your-workspace--tso-image-worker-generate.modal.run
```

Save that URL and the random string you made up — you need both in the
next step.

---

## 2. Add two environment variables in Railway

Open your Railway project → your service → **Variables**, and add:

```text
MODAL_IMAGE_URL=https://your-workspace--tso-image-worker-generate.modal.run
MODAL_AUTH_TOKEN=<the same random string you used in step 1>
```

Railway redeploys automatically when you save new variables — no code
push needed for this part, since the backend already knows how to call
Modal once these two vars are set (that logic shipped in `app.py`).

Your full Railway variable list now looks like the existing
`docs/DEPLOYMENT.md` list, plus these two:

```text
DATABASE_URL=...              # Supabase, unchanged
TSO_OWNER_PASSWORD=...
TSO_EDITOR_PASSWORD=...
RESEND_API_KEY=...            # unchanged
RESEND_FROM=...
APP_BASE_URL=...
GOOGLE_CLIENT_ID=...
GROQ_API_KEY=...
MODAL_IMAGE_URL=...           # new
MODAL_AUTH_TOKEN=...          # new
```

---

## 3. Push to GitHub as usual

The `image_service/` folder (including `modal_app.py`) just needs to be
in your repo — Railway's build doesn't touch it, since it's not part of
the Flask app it runs. It only matters when *you* run `modal deploy`
from your own machine, as in step 1.

```bash
git add .
git commit -m "Add Modal-hosted image generation"
git push
```

Railway redeploys the web app (picking up the two new env vars); Modal
is already live from step 1 and doesn't need redeploying unless you
change `modal_app.py` itself — in which case re-run `modal deploy`.

---

## 4. Verify it works

Once Railway finishes redeploying, hit your app's image generation
feature (`/api/ai/generate-image`) from the site. First request after
an idle period will be a bit slower (~10-30s cold start as the Modal
container spins up); after that it should return in a few seconds.

If something's misconfigured, the endpoint returns a clear error instead
of a stack trace — e.g. "Image generation isn't connected yet" if the
env vars are missing, or a Modal-side error message if the worker itself
fails.

---

## How this fits your existing pieces

| Piece | Role | Changed? |
|---|---|---|
| GitHub | Source of truth, triggers Railway deploys | No |
| Railway | Hosts the Flask app (no GPU) | No — just 2 new env vars |
| Supabase | Job board + optional mail database | No |
| Resend | Transactional email | No |
| **Modal** | **Hosts the GPU worker for image generation** | **New** |

Cost: Railway/Supabase/Resend keep whatever billing you already have.
Modal is separate and pay-per-second — its free tier (~$30/mo of credit)
should comfortably cover a small group's daily use; you'll only see a
Modal bill once you exceed that.

## If you ever want to swap providers later

`backend/app.py`'s `ai_generate_image()` tries Modal first, then RunPod
(if `RUNPOD_ENDPOINT_ID`/`RUNPOD_API_KEY` are set), then a free
Hugging Face fallback (`HF_API_TOKEN`) as a last resort. To switch
primary providers, you don't need to touch code — just set or unset the
relevant Railway env vars.
