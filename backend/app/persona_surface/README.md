# app/persona_surface/

**Layer 4 of the synthetic-learner harness:** the LLM-mediated natural language that
renders an already-computed persona action (answer/hint/explanation) as chat text.

It **never sees the persona's knowledge state** (invariant 3) — only the action it is
about to voice. Additive and optional: disable it and the harness still runs
deterministically, losing only chat naturalness, never evaluation evidence.
