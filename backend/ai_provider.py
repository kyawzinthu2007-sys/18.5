"""
TSO AI — text generation provider (Groq).

Replaces the previous Google Gemini text backend. Groq serves open-weight
models (Llama 3.3, etc.) — not a Google product — over a Gemini-shaped
problem: pay-as-you-go, keyed by an API key, called over plain HTTPS, no
SDK dependency (stdlib urllib, consistent with the rest of this file).

Why Groq and not a truly "local" model: this app deploys to small
CPU-only web hosts (Railway/Render/Koyeb/etc.) with no GPU and not enough
resident RAM to run an LLM in-process. Groq is the pragmatic middle
ground — an inference API for open models, not Google's Gemini — reached
the same way the app already reaches DuckDuckGo or RunPod: an HTTPS call
from this backend. If a genuinely self-hosted model (e.g. Ollama on your
own server) becomes available later, only GROQ_BASE_URL/GROQ_MODEL and
the request/response shape below need to change — every call site in
app.py goes through the functions in this file, not a provider SDK.

Get a free/pay-as-you-go API key at https://console.groq.com/keys
Set GROQ_API_KEY in the environment. Optionally override GROQ_MODEL /
GROQ_TIMEOUT. No key set -> every function here raises RuntimeError with
a clear message, exactly like the old Gemini helpers did.

Image generation (call_hf_generate_image, below) is a separate concern
from text: it calls Hugging Face's free "Inference Providers" routing
(router.huggingface.co — the old api-inference.huggingface.co domain
was fully retired and no longer resolves) to reach an open Stable
Diffusion-class model. Free-tier tradeoffs worth knowing — shared/queued
capacity (slower, occasional cold-start delay when a model hasn't been
used recently, handled here with one automatic retry), a specific model
can occasionally be unserved by any provider without notice (swap
HF_IMAGE_MODEL if that happens), and Hugging Face may retain/review
inputs sent to the free tier per their terms, similar to how free-tier
LLM APIs generally work. Set HF_API_TOKEN to enable it; the app's
existing self-hosted RunPod path (see app.py) remains available as a
paid, faster, more private alternative if you ever want it instead.
"""
import base64
import json
import os
import time
import urllib.error
import urllib.request

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
# Llama 3.3 70B — strong general-purpose open-weight model, good default
# for both Neo's occasional calls and Turbo's higher-volume ones.
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
# A smaller/faster model for latency-sensitive paths (mirrors the old
# GEMINI_TURBO_MODEL "flash-lite" pattern) — used where callers pass
# fast=True.
GROQ_FAST_MODEL = os.getenv("GROQ_FAST_MODEL", "llama-3.1-8b-instant").strip()
# Vision-capable model — used only when a user attaches an image in Turbo
# chat and asks about it. Text-only calls never use this model.
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "llama-4-scout-17b-16e-instruct").strip()
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# --- Groq-native modern assistant engine (no OpenAI API key required) ---
# Groq's Responses API can run open-weight GPT-OSS models with reasoning,
# native browser search, and hosted Python code execution. Vision is routed to
# Groq's multimodal Qwen model. The only AI credential required by this stack
# is GROQ_API_KEY.
GROQ_REASONING_MODEL = os.getenv("GROQ_REASONING_MODEL", "openai/gpt-oss-20b").strip()
GROQ_TURBO_MODEL = os.getenv("GROQ_TURBO_MODEL", "openai/gpt-oss-120b").strip()
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.6-27b").strip()
GROQ_RESPONSES_URL = "https://api.groq.com/openai/v1/responses"
GROQ_ENABLE_CODE = os.getenv("GROQ_ENABLE_CODE", "true").strip().lower() in {"1", "true", "yes", "on"}
GROQ_NEO_REASONING = os.getenv("GROQ_NEO_REASONING", "medium").strip()
GROQ_TURBO_REASONING = os.getenv("GROQ_TURBO_REASONING", "high").strip()

# --- Hugging Face free Inference Providers routing (image generation) ---
# Free-tier text-to-image via a hosted Stable Diffusion-class model. Set
# HF_API_TOKEN (a free Hugging Face access token with "Make calls to
# Inference Providers" permission, from huggingface.co/settings/tokens) to
# enable it. HF_IMAGE_MODEL can be overridden to point at a different
# text-to-image model if the default isn't available through free routing.
HF_API_TOKEN = os.getenv("HF_API_TOKEN", "").strip()
HF_IMAGE_MODEL = os.getenv("HF_IMAGE_MODEL", "stabilityai/stable-diffusion-xl-base-1.0").strip()
HF_IMAGE_API_URL = "https://router.huggingface.co/hf-inference/models/{model}"
# Applied whenever a caller doesn't supply their own negative_prompt, to
# steer the free SD-class models away from the most common artifacts.
DEFAULT_NEGATIVE_PROMPT = (
    "blurry, low quality, low resolution, distorted, deformed, disfigured, "
    "extra limbs, extra fingers, watermark, text, signature, ugly, bad anatomy"
)



def _decode_attachment_text(mime: str, raw: bytes, filename: str = "attachment") -> str:
    """Extract useful text from common uploaded documents without another AI API.
    Images are intentionally handled by the vision model instead."""
    mime = (mime or "").lower()
    name = (filename or "attachment").lower()
    try:
        if mime.startswith("text/") or any(name.endswith(x) for x in (".txt", ".md", ".csv", ".tsv", ".log", ".py", ".js", ".html", ".css", ".json")):
            return raw.decode("utf-8", errors="replace")[:120000]
        if name.endswith(".json") or mime == "application/json":
            return raw.decode("utf-8", errors="replace")[:120000]
        if name.endswith(".docx") or mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            import zipfile, xml.etree.ElementTree as ET
            with zipfile.ZipFile(__import__('io').BytesIO(raw)) as z:
                xml = z.read("word/document.xml")
            root = ET.fromstring(xml)
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            return "\n".join(t.text for t in root.findall(".//w:t", ns) if t.text)[:120000]
        if name.endswith(".pdf") or mime == "application/pdf":
            try:
                from pypdf import PdfReader
                import io
                reader = PdfReader(io.BytesIO(raw))
                return "\n\n".join((page.extract_text() or "") for page in reader.pages)[:120000]
            except Exception:
                return "[PDF attached; text extraction was unavailable on this deployment.]"
    except Exception:
        return ""
    return ""


def _groq_responses_request(instructions: str, input_items, max_tokens: int = 1200,
                            model: str | None = None, enable_search: bool = False,
                            enable_code: bool = False, turbo: bool = False,
                            timeout: int = 90, json_mode: bool = False) -> str:
    """Modern TSO engine using Groq's Responses API.

    No OpenAI API key is used. Browser search and code execution happen on
    Groq when enabled; the model autonomously decides when the tools help.
    """
    if not GROQ_API_KEY:
        raise RuntimeError("TSO AI is not configured. Set GROQ_API_KEY in the environment.")

    chosen = model or (GROQ_TURBO_MODEL if turbo else GROQ_REASONING_MODEL)
    body = {
        "model": chosen,
        "instructions": instructions,
        "input": input_items,
        "max_output_tokens": max_tokens,
        "reasoning_effort": GROQ_TURBO_REASONING if turbo else GROQ_NEO_REASONING,
    }
    tools = []
    if enable_search:
        tools.append({"type": "browser_search"})
    if enable_code and GROQ_ENABLE_CODE and chosen in {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}:
        tools.append({"type": "code_interpreter", "container": {"type": "auto"}})
    if tools:
        body["tools"] = tools
    if json_mode:
        body["text"] = {"format": {"type": "json_object"}}

    req = urllib.request.Request(
        GROQ_RESPONSES_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:700]
        if e.code == 429:
            raise RuntimeError("TSO's AI rate limit has been reached. Please try again in a few minutes.")
        if e.code in (400, 404):
            raise RuntimeError(f"Groq AI configuration/model error ({e.code}): {detail}")
        raise RuntimeError(f"Groq AI request failed ({e.code}): {detail}")
    except (urllib.error.URLError, OSError) as e:
        raise RuntimeError(f"Could not reach Groq AI: {e}")

    text = (result.get("output_text") or "").strip()
    if not text:
        chunks = []
        for item in result.get("output") or []:
            for content in item.get("content") or []:
                if content.get("type") in {"output_text", "text"} and content.get("text"):
                    chunks.append(content["text"])
        text = "\n".join(chunks).strip()
    if not text:
        raise RuntimeError("Groq AI returned an empty response.")
    return text


def _contents_to_responses(contents: list) -> list:
    items = []
    for item in contents:
        role = "assistant" if item.get("role") in {"model", "assistant"} else "user"
        content = []
        for part in item.get("parts") or []:
            if part.get("text"):
                content.append({"type": "input_text", "text": part["text"]})
            inline = part.get("inlineData")
            if inline:
                mime = inline.get("mimeType") or "application/octet-stream"
                data = inline.get("data") or ""
                if mime.startswith("image/"):
                    content.append({"type": "input_image", "detail": "auto", "image_url": f"data:{mime};base64,{data}"})
                else:
                    decoded = base64.b64decode(data, validate=False) if data else b""
                    extracted = _decode_attachment_text(mime, decoded, inline.get("name", "attachment"))
                    if extracted:
                        content.append({"type": "input_text", "text": f"ATTACHED FILE ({inline.get('name','attachment')}):\n{extracted}"})
        if content:
            items.append({"role": role, "content": content})
    return items or [{"role": "user", "content": [{"type": "input_text", "text": "(no message)"}]}]


def call_ai(system: str, user_message: str, max_tokens: int = 1200, fast: bool = False) -> str:
    """Structured/single-turn TSO call using Groq JSON mode."""
    if not GROQ_API_KEY:
        raise RuntimeError("TSO AI is not configured. Set GROQ_API_KEY in the environment.")
    return _groq_responses_request(
        system + "\nReturn ONLY the requested JSON object. Do not wrap it in markdown fences.",
        [{"role": "user", "content": [{"type": "input_text", "text": user_message}]}],
        max_tokens=max_tokens,
        json_mode=True, model=GROQ_TURBO_MODEL if fast else GROQ_REASONING_MODEL, timeout=70,
    )


def call_ai_chat(system: str, contents: list, max_tokens: int = 800, enable_search: bool = False,
                  fast: bool = False, timeout: int = 60, search_context: str | None = None,
                  turbo: bool = False, enable_code: bool = False) -> str:
    """ChatGPT-like multi-turn engine using Groq GPT-OSS Responses.
    Supports reasoning, native web search, optional code execution, and text
    extracted from common uploaded files."""
    effective_system = system
    if search_context:
        effective_system += "\n\nAdditional web evidence supplied by TSO:\n" + search_context
    return _groq_responses_request(
        effective_system, _contents_to_responses(contents), max_tokens=max_tokens,
        turbo=(turbo or fast), enable_search=enable_search, enable_code=enable_code,
        timeout=timeout,
    )


def call_ai_vision(system: str, contents: list, max_tokens: int = 900, timeout: int = 60) -> dict:
    """Multimodal attachment understanding via Groq Qwen 3.6 27B."""
    if not GROQ_API_KEY:
        raise RuntimeError("TSO AI is not configured. Set GROQ_API_KEY in the environment.")
    messages = [{"role": "system", "content": system}]
    for item in contents:
        role = "assistant" if item.get("role") == "model" else "user"
        parts = item.get("parts") or []
        content = []
        for part in parts:
            if part.get("text"):
                content.append({"type": "text", "text": part["text"]})
            inline = part.get("inlineData")
            if inline:
                mime = inline.get("mimeType") or "image/png"
                data = inline.get("data") or ""
                if mime.startswith("image/"):
                    content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}})
                else:
                    decoded = base64.b64decode(data, validate=False) if data else b""
                    extracted = _decode_attachment_text(mime, decoded, inline.get("name", "attachment"))
                    if extracted:
                        content.append({"type": "text", "text": f"ATTACHED FILE ({inline.get('name','attachment')}):\n{extracted}"})
        if content:
            messages.append({"role": role, "content": content})
    body = {"model": GROQ_VISION_MODEL, "messages": messages, "max_completion_tokens": max_tokens, "reasoning_effort": "medium"}
    req = urllib.request.Request(GROQ_API_URL, data=json.dumps(body).encode("utf-8"),
                                 headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:700]
        raise RuntimeError(f"Groq vision request failed ({e.code}): {detail}")
    except (urllib.error.URLError, OSError) as e:
        raise RuntimeError(f"Could not reach Groq vision: {e}")
    text = ((result.get("choices") or [{}])[0].get("message") or {}).get("content", "").strip()
    if not text:
        raise RuntimeError("Groq vision returned an empty response.")
    return {"text": text, "images": []}


def call_ai_enhance_image_prompt(prompt: str) -> str:
    """Turn a short image request into a detailed generation prompt.

    Kept in ai_provider because backend/app.py imports this helper at startup.
    Uses the existing Groq TSO engine; it does not require an OpenAI API key.
    If enhancement fails, return the original prompt so image generation can
    continue instead of preventing the Flask application from starting.
    """
    original = (prompt or "").strip()
    if not original:
        return original
    if not GROQ_API_KEY:
        return original
    instructions = (
        "You are TSO AI's image-prompt enhancer. Rewrite the user's image request "
        "into one concise, production-ready prompt for an open-weight text-to-image "
        "model. Preserve the user's subject, intent, composition and any explicit "
        "text. Add useful visual details such as setting, lighting, camera/framing, "
        "materials, style and quality only when appropriate. Do not add unrelated "
        "objects, logos, people, or claims. Return only the final prompt as plain text."
    )
    try:
        return _groq_responses_request(
            instructions,
            [{"role": "user", "content": [{"type": "input_text", "text": original}]}],
            max_tokens=700,
            model=GROQ_FAST_MODEL,
            enable_search=False,
            enable_code=False,
            turbo=False,
            timeout=45,
        ).strip() or original
    except Exception:
        return original



def call_hf_generate_image(prompt: str, negative_prompt: str | None = None,
                            steps: int | None = None, size: int | None = None,
                            timeout: int = 60) -> dict:
    """Generates an image from a text prompt using Hugging Face's free
    Inference Providers routing (a hosted Stable Diffusion-class model —
    open-weight, not Gemini/DALL-E/etc.). Returns {"image":
    "data:image/png;base64,...", "seconds": None} — matching the shape
    app.py's RunPod path already returns, so the /api/ai/generate-image
    route can use either interchangeably. Raises RuntimeError with a
    human-readable message on failure.

    negative_prompt/steps/size are forwarded to the model as HF's standard
    `parameters` object (guidance/quality knobs supported by every
    Diffusers text-to-image pipeline HF routes to) — this is what lets a
    caller ask for a more precise result instead of relying on the raw
    prompt alone. Falls back to DEFAULT_NEGATIVE_PROMPT when the caller
    doesn't supply one.

    Handles the free tier's most common failure mode automatically: on a
    cold model (not currently loaded on a shared worker), Hugging Face
    returns a 503 with an estimated_time. This function waits that long
    (capped at 20s) and retries once before giving up, so a short cold
    start resolves silently instead of surfacing as an error to the user."""
    if not HF_API_TOKEN:
        raise RuntimeError(
            "Image generation isn't connected yet. Set HF_API_TOKEN (a free Hugging Face "
            "access token with 'Make calls to Inference Providers' permission, from "
            "huggingface.co/settings/tokens) to enable it."
        )

    url = HF_IMAGE_API_URL.format(model=HF_IMAGE_MODEL)
    parameters = {"negative_prompt": (negative_prompt or DEFAULT_NEGATIVE_PROMPT)}
    if steps:
        parameters["num_inference_steps"] = max(5, min(int(steps), 60))
    if size:
        clamped = max(256, min(int(size), 1024))
        clamped -= clamped % 8
        parameters["width"] = clamped
        parameters["height"] = clamped
    payload = json.dumps({"inputs": prompt, "parameters": parameters}).encode("utf-8")

    def _attempt():
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Authorization": f"Bearer {HF_API_TOKEN}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.headers.get("Content-Type", ""), response.read()

    retried = False
    while True:
        try:
            content_type, raw = _attempt()
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:500]
            if e.code == 503 and not retried:
                wait = 5
                try:
                    info = json.loads(detail)
                    wait = min(round(info.get("estimated_time", 5)), 20)
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
                time.sleep(max(wait, 1))
                retried = True
                continue
            if e.code == 503:
                raise RuntimeError("The free image model is warming up — please try again in about 30 seconds.")
            if e.code == 429:
                raise RuntimeError("Hugging Face's free image generation rate limit has been reached. Please try again in a few minutes.")
            if e.code == 404:
                raise RuntimeError(
                    f"The image model \"{HF_IMAGE_MODEL}\" isn't available through Hugging Face's free routing "
                    "right now. Try setting HF_IMAGE_MODEL to a different text-to-image model."
                )
            raise RuntimeError(f"Image generation failed ({e.code}): {detail}")
        except (urllib.error.URLError, OSError) as e:
            raise RuntimeError(f"Could not reach the image generation service: {e}")

    if "application/json" in content_type:
        # An error came back as JSON instead of image bytes (e.g. a
        # validation error) even with a 200 status in some HF edge cases.
        try:
            info = json.loads(raw.decode("utf-8"))
            raise RuntimeError(info.get("error") or "Image generation returned an unexpected response.")
        except json.JSONDecodeError:
            raise RuntimeError("Image generation returned an unexpected response.")

    if not raw:
        raise RuntimeError("Image generation returned an empty result.")

    mime = content_type if content_type.startswith("image/") else "image/png"
    encoded = base64.b64encode(raw).decode("ascii")
    return {"image": f"data:{mime};base64,{encoded}", "seconds": None}
