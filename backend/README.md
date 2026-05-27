# backend/

Python + FastAPI service: the domain model, mastery model, personas, policy, HelpNeed predictor, tutor loop, and API. SymPy (all math correctness) lives here in `app/domain/`; LLM calls live only in `app/llm/`. Managed by `uv` as a standalone Python project — it is **not** part of the pnpm workspace.

Does NOT live here: React/frontend code (`frontend/`), generated TS types (`shared-types/`), AWS CDK (`infrastructure/`).
