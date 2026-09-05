# TSO Edu — Natural Writing Coach

## Three tools are intentionally different

- **Analyze writing (2 TSO coins):** evaluates an existing essay. It scores grammar, vocabulary, coherence, cohesion, relevance and CEFR-style level and gives feedback. It does not rewrite the essay.
- **Generate essay (3 TSO coins):** creates a new model essay from a topic, type and level. It is a starting model, not a student's personal draft.
- **Natural Writing Coach (2 TSO coins):** improves a draft the student already wrote. It uses the local deterministic engine to reduce formulaic wording, adjust overly advanced vocabulary and vary repetitive sentence openings. It does not call an external AI API.

## Academic-integrity positioning

The feature is deliberately called **Natural Writing Coach / Student Voice** rather than an AI-detector bypass or "AI humanizer". It does not promise to make text undetectable by AI detectors and does not certify authorship. Students should review every change and keep their own ideas and evidence.

## Production setup

No new API key or third-party plagiarism service is required. The engine runs inside the Flask backend and works with English drafts. Myanmar text is preserved safely until Myanmar-specific natural-writing rules are added.
