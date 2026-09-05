# TSO Edu — Local ChatGPT-like Essay Engine

The Edu **စာစီစာကုံး / English Essay** generator no longer needs an OpenAI API key. It uses a self-hosted local LLM through Ollama.

## Why this is called ChatGPT-like, not ChatGPT itself

The exact ChatGPT model/service cannot simply be copied into a ZIP and embedded in a website. OpenAI's GPTs are designed to run inside ChatGPT, while applications that need an OpenAI model normally use the API. For a genuinely local deployment, OpenAI's open-weight `gpt-oss-20b` and `gpt-oss-120b` can be run on infrastructure you control.

## Recommended model

- `gpt-oss:20b` — practical local default.
- `gpt-oss:120b` — stronger quality when the server has enough GPU/RAM.

The TSO prompt gives the local model a dedicated system role, topic planning rules, language/CEFR requirements, essay-type rules, target word count and Myanmar school-writing behavior.

## Install Ollama

Install Ollama on the same server as TSO, then pull the model:

```bash
ollama pull gpt-oss:20b
```

For a powerful GPU server you can instead use:

```bash
ollama pull gpt-oss:120b
```

Start Ollama and verify it is reachable at `http://127.0.0.1:11434`.

## Environment variables

```env
TSO_LOCAL_LLM_URL=http://127.0.0.1:11434/api/chat
TSO_LOCAL_LLM_MODEL=gpt-oss:20b
TSO_LOCAL_LLM_TIMEOUT=180
TSO_LOCAL_LLM_FALLBACK=true
```

No `OPENAI_API_KEY` is required for this essay generator.

## Generation flow

1. TSO receives the topic, language, level, essay type and target words.
2. The backend validates the request and applies the existing TSO coin rules.
3. The local LLM receives a dedicated system instruction.
4. The model creates the complete essay.
5. Existing TSO plagiarism analysis runs after generation.
6. If the local model is temporarily unavailable and fallback is enabled, the original deterministic offline generator produces the essay instead.

## Important deployment note

A local LLM still needs compute. The ZIP contains the integration and prompts, not the multi-gigabyte model weights. This keeps the website package deployable.

## Bundled TSO Edu Generation Database

The ZIP now includes a prebuilt SQLite generation database at:
`backend/edu_app/data/writing_coach.db`.

It contains the existing analysis/reference database plus the local-generation
knowledge layer:
- 182 original/sample training-style essays for analysis and similarity screening
- 31 reference metadata records
- 7 English essay task types
- 11 composition/debate task rules
- 6 CEFR level rules (A1–C2)
- 66 level × task paragraph plans
- 32 topic knowledge domains with keywords, angles, benefits, limitations and example contexts
- existing vocabulary and feedback rules

The local LLM generator retrieves a small relevant subset of this database for
each request. It does not copy stored essays into the answer. The database is
an original pedagogical grounding layer; it is not intended to reproduce
ChatGPT itself or to contain copyrighted textbook chapters.

To rebuild/upgrade the bundled database after changing its seed data:

```bash
cd backend/edu_app
python build_generation_database.py
```
