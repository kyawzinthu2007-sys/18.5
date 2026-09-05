# TSO AI / TSO Turbo AI — OpenAI-key-free modern engine

This version does **not** require an OpenAI API key. TSO AI and TSO Turbo AI use
Groq's OpenAI-compatible Responses API with open-weight GPT-OSS models. Groq's
current API supports reasoning controls, browser search and code execution for
GPT-OSS, while Groq's Qwen 3.6 27B provides multimodal image understanding.

## Environment

```text
GROQ_API_KEY=your_groq_key
GROQ_REASONING_MODEL=openai/gpt-oss-20b
GROQ_TURBO_MODEL=openai/gpt-oss-120b
GROQ_VISION_MODEL=qwen/qwen3.6-27b
GROQ_ENABLE_CODE=true
GROQ_NEO_REASONING=medium
GROQ_TURBO_REASONING=high
```

## Capabilities

- TSO AI: stronger reasoning, multi-turn conversation, native browser search,
  optional hosted Python code/data execution, and image/file understanding.
- TSO Turbo AI: a separate stronger GPT-OSS 120B model and higher reasoning
  setting, plus the existing Turbo Memory and Projects.
- Existing Turbo Research, comparison and job-matching agents are preserved.
- Existing image generation is preserved on the existing RunPod/Hugging Face
  path; this change does not replace that service.
- TXT/MD/CSV/JSON/code/DOCX/PDF files are extracted server-side and supplied as
  grounded context; images are routed to the multimodal Groq model.
- Existing Supabase, Resend, Mail, Edu and job-board functionality is preserved.

## Important

There is no `OPENAI_API_KEY`, `OPENAI_MODEL`, or `OPENAI_TURBO_MODEL` dependency
in this version. You still need a Groq API credential for the hosted AI engine;
Groq usage can have its own limits/pricing, so check the current Groq plan for
your deployment.
