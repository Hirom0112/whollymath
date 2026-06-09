# app/llm/

The LLM **provider abstraction** (Claude) — the ONLY place an LLM is called.
Optional LangSmith tracing wraps this seam.

Surface text **only** (hints, voice, persona narration), always rendered *after* the
deterministic verdict and off the sub-100 ms turn loop (invariants 1–2). The LLM
**never** decides math correctness and never sees a persona's knowledge state.
