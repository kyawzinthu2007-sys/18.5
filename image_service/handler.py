"""
TSO AI — RunPod Serverless worker for image generation.

This is the handler RunPod runs on-demand: it spins up a GPU worker only
when a job arrives, generates one image with a locally-run Stable
Diffusion model, and returns it. No external image-generation API
(Gemini, DALL-E, etc.) is used — the model runs on your own RunPod worker,
you just don't have to keep a server up 24/7 to host it.

RunPod's contract: define handler(job) and call runpod.serverless.start.
`job["input"]` is whatever JSON the caller sent as `input`. See
https://docs.runpod.io/serverless/workers/handler-functions
"""
import base64
import io
import os
import time

import runpod
import torch
from diffusers import StableDiffusionPipeline

MODEL_ID = os.getenv("SD_MODEL_ID", "stable-diffusion-v1-5/stable-diffusion-v1-5").strip()
DEFAULT_STEPS = int(os.getenv("SD_STEPS", "25"))
DEFAULT_SIZE = int(os.getenv("SD_IMG_SIZE", "512"))
MAX_PROMPT_LEN = 1200

print(f"[worker] Loading {MODEL_ID} …")
_device = "cuda" if torch.cuda.is_available() else "cpu"
_dtype = torch.float16 if _device == "cuda" else torch.float32
_pipe = StableDiffusionPipeline.from_pretrained(MODEL_ID, torch_dtype=_dtype).to(_device)
try:
    _pipe.enable_attention_slicing()
except Exception:
    pass
print(f"[worker] Model loaded on device={_device}. Ready for jobs.")


def handler(job):
    """RunPod calls this once per job. Return value is sent back to the
    caller as the job's `output`."""
    job_input = job.get("input") or {}

    prompt = (job_input.get("prompt") or "").strip()
    if not prompt:
        return {"error": "A prompt is required."}
    if len(prompt) > MAX_PROMPT_LEN:
        return {"error": f"Prompt must be under {MAX_PROMPT_LEN} characters."}

    negative_prompt = (job_input.get("negativePrompt") or "").strip() or None

    steps = int(job_input.get("steps") or DEFAULT_STEPS)
    steps = max(5, min(steps, 60))

    size = int(job_input.get("size") or DEFAULT_SIZE)
    size = max(256, min(size, 768))
    size = size - (size % 8)  # SD requires dimensions divisible by 8

    generator = None
    seed = job_input.get("seed")
    if seed is not None:
        try:
            generator = torch.Generator(device=_device).manual_seed(int(seed))
        except (TypeError, ValueError):
            generator = None

    try:
        start = time.time()
        with torch.inference_mode():
            result = _pipe(
                prompt=prompt,
                negative_prompt=negative_prompt,
                num_inference_steps=steps,
                height=size,
                width=size,
                generator=generator,
            )
        elapsed = round(time.time() - start, 1)
        image = result.images[0]

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        return {
            "image": f"data:image/png;base64,{b64}",
            "seconds": elapsed,
            "device": _device,
        }
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller as a clean error
        return {"error": f"Generation failed: {exc}"}


runpod.serverless.start({"handler": handler})
