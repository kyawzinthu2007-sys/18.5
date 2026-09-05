# TSO AI — Self-Hosted Image Generation (Modal or RunPod Serverless)

This generates images locally with an open-weights Stable Diffusion model
(via Hugging Face `diffusers`) — not Gemini, DALL-E, or any other external
image API. Two interchangeable hosting options are included:

- **`modal_app.py` (Modal)** — recommended default. No Docker required;
  `modal deploy` builds the container in the cloud for you. Has a free
  tier (~$30/mo of compute credit as of this writing) that comfortably
  covers light/regular daily use for a small group.
- **`handler.py` + `Dockerfile` (RunPod Serverless)** — kept as a
  fallback/alternative. Requires a local Docker build and a container
  registry push, but is a solid option if you'd rather not depend on
  Modal, or want to compare pricing/GPU availability between the two.

Both are billed pay-per-second of GPU time actually used — there's no
idle 24/7 server cost either way. The backend (`backend/app.py`) tries
Modal first if configured, then RunPod, then falls back to a free (very
limited) Hugging Face path if neither is set up — see
`ai_generate_image()` in app.py.

## Option A: Modal (no Docker)

```bash
pip install modal
modal setup                     # links this machine to a free Modal account
cd image_service
modal secret create tso-modal-auth MODAL_AUTH_TOKEN=<make up a long random string>
modal deploy modal_app.py       # builds + deploys, prints your endpoint URL
```

Then set on the main backend:

```
MODAL_IMAGE_URL=<the URL modal deploy printed>
MODAL_AUTH_TOKEN=<the same random string you used above>
```

See the docstring at the top of `modal_app.py` for local testing and
cost details.

## Option B: RunPod Serverless (Docker required)

## How it works

- `handler.py` loads the model once when a worker container starts, then
  handles one job per call: prompt in, PNG out.
- RunPod keeps zero workers running when nothing is happening. A request
  triggers a **cold start** (spin up a container, ~10-30s depending on the
  GPU and whether the image already has the model baked in) and then runs
  in seconds after that.
- You pay per-second of GPU time actually used, not by the month.

## One-time setup

### 1. Build and push the worker image

You need a Docker registry account (Docker Hub is free for public images).

```bash
cd image_service
docker build -t YOUR_DOCKERHUB_USERNAME/tso-ai-image-worker:latest .
docker push YOUR_DOCKERHUB_USERNAME/tso-ai-image-worker:latest
```

This bakes the model weights into the image at build time (see the
`Dockerfile`), which trades a slower one-time build for faster cold
starts later. Building this image requires a GPU-capable machine or a
service like Docker's `buildx` cloud builders — building it locally on a
CPU-only machine is fine too since we're only *downloading* weights
during build, not running inference.

### 2. Create the RunPod Serverless endpoint

1. Sign up at [runpod.io](https://runpod.io) and add a payment method
   (pay-as-you-go; no monthly minimum).
2. Go to **Serverless → New Endpoint**.
3. Choose **Custom Source → Docker Image**, and point it at the image you
   pushed (`YOUR_DOCKERHUB_USERNAME/tso-ai-image-worker:latest`).
4. Pick a GPU tier — an RTX 4090 or A4000-class GPU is plenty for
   512x512 Stable Diffusion and keeps per-second cost low.
5. Set **Max Workers** to something small (1-2) — this is a personal/small
   site feature, not a high-traffic API.
6. Set **Idle Timeout** to something short (e.g. 5s) so a worker scales
   back to zero quickly after each image and you're not billed for idle
   time between requests.
7. Deploy. RunPod gives you an **Endpoint ID** and you already have your
   **API Key** under Settings → API Keys.

### 3. Connect it to the main app

Set these on the main Talentshowoff backend:

```
RUNPOD_ENDPOINT_ID=<the endpoint ID from step 2>
RUNPOD_API_KEY=<your RunPod API key>
```

That's it — `/api/ai/generate-image` will call your RunPod endpoint
instead of any external image-generation API.

## Cost expectations

- RTX 4090-class workers on RunPod run roughly $0.0002-0.0006 per second.
  A 512x512 image at 25 steps takes on the order of 5-10 seconds once the
  worker is warm — a fraction of a cent per image.
- The real cost driver is **cold starts**: each time a worker has to spin
  up from zero, you're billed for that startup time too. If usage is
  bursty (a handful of images now and then), expect most of the cost to
  come from cold starts rather than generation itself — still well within
  a $5-10/mo budget for light/personal use, but worth knowing.
- Set a spend limit in RunPod's billing settings if you want a hard cap.

## Local testing without deploying

You can run the handler locally to sanity-check it before building the
Docker image (needs a GPU for reasonable speed, but will also run on CPU):

```bash
pip install -r requirements.txt
python handler.py
```

RunPod's SDK includes a local test server flag; see
[RunPod's docs](https://docs.runpod.io/serverless/development/local-testing)
for details on `--rp_serve_api` if you want to hit it with curl locally.

## Configuration reference

| Env var (set at RunPod endpoint level) | Default | Meaning |
|---|---|---|
| `SD_MODEL_ID` | `stable-diffusion-v1-5/stable-diffusion-v1-5` | Hugging Face model repo |
| `SD_STEPS` | `25` | Inference steps (quality vs. speed) |
| `SD_IMG_SIZE` | `512` | Output width/height in pixels |

Request-level overrides (`prompt`, `steps`, `size`, `seed`, `negativePrompt`)
are sent by the main app per-request; see `handler.py`.
