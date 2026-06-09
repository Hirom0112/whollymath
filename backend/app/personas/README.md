# app/personas/

**Layers 2 + 3 of the synthetic-learner harness:** the persona configs (data — which
KCs each holds and in what mode, plus behavioral params) and the deterministic
**behavioral simulator** (config + problem ⇒ action).

Deterministic — same input, same output, **no LLM** here (the natural-language surface
is `persona_surface/`). The five personas are the mastery model's integration suite.
