# TSO Edu — Local LLM Essay Generation

The previous cloud OpenAI essay endpoint has been replaced by the **local TSO Edu essay engine**.

The backend calls an Ollama server running on infrastructure controlled by the TSO deployment. The recommended local models are OpenAI open-weight `gpt-oss:20b` and `gpt-oss:120b`.

## Environment

```env
TSO_LOCAL_LLM_URL=http://127.0.0.1:11434/api/chat
TSO_LOCAL_LLM_MODEL=gpt-oss:20b
TSO_LOCAL_LLM_TIMEOUT=180
TSO_LOCAL_LLM_FALLBACK=true
```

No OpenAI API key is required for essay generation.

## What the local engine does

- Understands the supplied title/topic before writing.
- Uses a dedicated TSO Edu system prompt.
- Respects English CEFR level selection.
- Respects Myanmar စာစီစာကုံး type selection.
- Keeps အဆိုအချေ as its separate workflow.
- Targets the requested word count.
- Avoids invented statistics/citations.
- Produces only the final composition.
- Runs the existing plagiarism analysis after generation.
- Falls back to the original deterministic local generator if the model is unavailable and fallback is enabled.
