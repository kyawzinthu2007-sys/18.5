"""
TSO AI -- Self-hosted image generation on Modal (no Docker required).

This is an alternative to the RunPod Serverless worker in handler.py /
Dockerfile -- same idea (your own Stable Diffusion weights, pay only for
GPU-seconds actually used, zero idle cost), but Modal builds the
container image for you in the cloud from the `image` definition below.
There is nothing to `docker build` or push to a registry locally.

## One-time setup

    pip install modal
    modal setup          # opens a browser, links this machine to your
                          # free Modal account (no credit card required
                          # for the free tier)

## Deploy

    cd image_service
    modal run modal_app.py::download_model    # one-time: caches SD weights into a Volume
    modal deploy modal_app.py

That's it. Modal prints a URL like:

    https://<your-workspace>--tso-image-worker-generate.modal.run

Set that on the main Talentshowoff backend as MODAL_IMAGE_URL, along
with a shared secret you choose yourself (see MODAL_AUTH_TOKEN below) --
that's what backend/app.py's call_modal_generate_image() sends and
checks, so randoms on the internet can't burn your Modal credits by
hitting the URL directly.

    MODAL_IMAGE_URL=https://<your-workspace>--tso-image-worker-generate.modal.run
    MODAL_AUTH_TOKEN=<any long random string you make up>

Also set the *same* MODAL_AUTH_TOKEN as a Modal secret so the deployed
function can check it:

    modal secret create tso-modal-auth MODAL_AUTH_TOKEN=<the same string>

## Cost

Modal's free tier includes roughly $30/month of compute credit
(check https://modal.com/pricing for the current figure -- this
changes over time). An A10G-class GPU on Modal runs on the order of
$0.0006/second; a 512x512 image at 25 steps takes a few seconds once
the container is warm, so light/regular daily use for a small group
should comfortably fit inside the free credit. As with RunPod, cold
starts (spinning a container up from zero) are the main cost driver
for bursty traffic, not generation time itself -- `scaledown_window`
below keeps a worker warm for a short period after each request so a
handful of images in a row only pays one cold start, not one per image.

## Local test before deploying

    modal run modal_app.py::download_model      # if you haven't already
    modal run modal_app.py --prompt "a red bicycle in a park"

This runs the same function without deploying a persistent endpoint --
useful for a quick sanity check that the model loads and produces an
image before you `modal deploy`. Requires the Volume to already be
populated by download_model (above) -- it does not download on the fly.
"""
import io
import os
import time

import modal

app = modal.App("tso-image-worker")

# Modal builds this image in the cloud on first deploy -- no local
# Docker daemon, no registry account, no `docker push`. Override
# SD_MODEL_ID below to bake a different model in.
SD_MODEL_ID = os.getenv("SD_MODEL_ID", "stable-diffusion-v1-5/stable-diffusion-v1-5")

# Model weights are downloaded once into this persistent Volume (via
# download_model() below, at deploy time) rather than during the image
# build itself -- Modal's image-build sandbox has outbound network
# access disabled by default, so a build-time `from_pretrained()` call
# fails with "outgoing traffic has been disabled". A Volume-backed
# download function *does* get network access and only needs to run
# once; after that the weights are cached and every container mounts
# the same Volume instead of re-downloading.
model_volume = modal.Volume.from_name("tso-sd-weights", create_if_missing=True)
MODEL_CACHE_DIR = "/cache"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "torch>=2.1.0",
        "diffusers>=0.29.0",
        "transformers>=4.41.0",
        "accelerate>=0.30.0",
        "safetensors>=0.4.3",
        # Required explicitly for @modal.fastapi_endpoint -- Modal no
        # longer bundles this automatically.
        "fastapi[standard]",
    )
)


def _download_model():
    """Runs once (with network access) to populate the Volume with model
    weights. Not part of the image build -- see the comment above
    model_volume for why."""
    import torch
    from diffusers import StableDiffusionPipeline

    StableDiffusionPipeline.from_pretrained(
        SD_MODEL_ID, torch_dtype=torch.float16, cache_dir=MODEL_CACHE_DIR
    )
    model_volume.commit()


@app.function(image=image, volumes={MODEL_CACHE_DIR: model_volume}, timeout=1800)
def download_model():
    """Run once before your first real deploy (see the README/deploy
    instructions) to warm the Volume: `modal run modal_app.py::download_model`.
    Subsequent deploys and container cold-starts reuse the cached weights
    instead of re-downloading."""
    _download_model()


MAX_PROMPT_LEN = 1200


@app.cls(
    image=image,
    gpu="A10G",
    volumes={MODEL_CACHE_DIR: model_volume},
    # Keep a worker warm for 30s after the last request so a burst of a
    # few images in a row (one user session) only cold-starts once.
    scaledown_window=30,
    secrets=[modal.Secret.from_name("tso-modal-auth")],
)
class Worker:
    @modal.enter()
    def load_model(self):
        import torch
        from diffusers import StableDiffusionPipeline

        # Force this container's view of the Volume to pick up whatever
        # download_model() committed -- a freshly-started container can
        # otherwise see a stale (possibly empty) snapshot of the Volume
        # taken before the download happened.
        model_volume.reload()

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if self.device == "cuda" else torch.float32
        try:
            self.pipe = StableDiffusionPipeline.from_pretrained(
                SD_MODEL_ID, torch_dtype=dtype, cache_dir=MODEL_CACHE_DIR, local_files_only=True
            ).to(self.device)
        except OSError as e:
            import os as _os
            try:
                cache_contents = _os.listdir(MODEL_CACHE_DIR)
            except OSError:
                cache_contents = "<cache dir itself missing>"
            raise RuntimeError(
                "Model weights aren't cached yet or the Volume is empty "
                f"(cache dir contents: {cache_contents}). Run "
                "`modal run modal_app.py::download_model` once, wait for it to "
                "finish without errors, then redeploy."
            ) from e
        try:
            self.pipe.enable_attention_slicing()
        except Exception:
            pass

    def _generate(self, prompt: str, negative_prompt: str | None, steps: int, size: int, seed):
        import torch

        generator = None
        if seed is not None:
            try:
                generator = torch.Generator(device=self.device).manual_seed(int(seed))
            except (TypeError, ValueError):
                generator = None

        start = time.time()
        with torch.inference_mode():
            result = self.pipe(
                prompt=prompt,
                negative_prompt=negative_prompt,
                num_inference_steps=steps,
                height=size,
                width=size,
                generator=generator,
            )
        elapsed = round(time.time() - start, 1)
        return result.images[0], elapsed

    @modal.fastapi_endpoint(method="POST", docs=True)
    def generate(self, item: dict):
        """HTTPS endpoint the main backend calls. Expects JSON body:
        {"prompt": str, "negativePrompt"?: str, "steps"?: int, "size"?: int,
        "seed"?: int, "token": str}. `token` must match MODAL_AUTH_TOKEN
        (the tso-modal-auth secret) or the request is rejected -- this is
        what keeps the endpoint from being usable by anyone who finds the
        URL. Returns {"image": "data:image/png;base64,...", "seconds": float}
        or {"error": str}."""
        import base64

        from fastapi import HTTPException

        expected_token = os.environ.get("MODAL_AUTH_TOKEN", "")
        if not expected_token or item.get("token") != expected_token:
            raise HTTPException(status_code=401, detail="Invalid or missing token.")

        prompt = (item.get("prompt") or "").strip()
        if not prompt:
            raise HTTPException(status_code=400, detail="A prompt is required.")
        if len(prompt) > MAX_PROMPT_LEN:
            raise HTTPException(status_code=400, detail=f"Prompt must be under {MAX_PROMPT_LEN} characters.")

        negative_prompt = (item.get("negativePrompt") or "").strip() or None

        steps = int(item.get("steps") or 25)
        steps = max(5, min(steps, 60))

        size = int(item.get("size") or 512)
        size = max(256, min(size, 768))
        size = size - (size % 8)  # SD requires dimensions divisible by 8

        seed = item.get("seed")

        try:
            img, elapsed = self._generate(prompt, negative_prompt, steps, size, seed)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Image generation failed: {e}")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        encoded = base64.b64encode(buf.getvalue()).decode("ascii")
        return {"image": f"data:image/png;base64,{encoded}", "seconds": elapsed}


@app.local_entrypoint()
def main(prompt: str = "a scenic mountain lake at sunrise"):
    """Local test entrypoint: `modal run modal_app.py --prompt "..."`.
    Runs generation directly (bypassing the HTTPS/token layer) to
    sanity-check the model before deploying."""
    w = Worker()
    w.load_model.local()
    img, elapsed = w._generate.local(prompt, None, 25, 512, None)
    out_path = "/tmp/modal_test_output.png"
    img.save(out_path)
    print(f"Generated in {elapsed}s -> {out_path}")
