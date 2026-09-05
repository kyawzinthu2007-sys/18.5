# RunPod Serverless worker image for TSO AI's self-hosted image generation.
# Build & push this to a container registry (Docker Hub, GHCR, etc.), then
# point a RunPod Serverless endpoint at the image — see README.md.
FROM runpod/base:0.6.2-cuda12.1.0

COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

COPY handler.py /handler.py

# Bake the model weights into the image at build time so the first request
# on a fresh worker doesn't pay a multi-GB Hugging Face download on top of
# the cold start. Override SD_MODEL_ID at build time with
# `--build-arg SD_MODEL_ID=...` to bake a different model.
ARG SD_MODEL_ID=stable-diffusion-v1-5/stable-diffusion-v1-5
ENV SD_MODEL_ID=${SD_MODEL_ID}
RUN python -c "from diffusers import StableDiffusionPipeline; import os, torch; \
    StableDiffusionPipeline.from_pretrained(os.environ['SD_MODEL_ID'], torch_dtype=torch.float16)"

CMD ["python", "-u", "handler.py"]
