# shared-types/

TypeScript types generated from the backend Pydantic schemas — one source of truth for the API contract (TECH_STACK §2). Run `pnpm generate` to regenerate after backend models change; the output (`src/generated.ts`) is committed so the frontend has a stable import target. A pnpm workspace package.

Generation runs `pydantic2ts` in the backend's uv environment (it shells into `../backend`). That tool requires the `pydantic-to-typescript` Python package plus the `json-schema-to-typescript` npm CLI; both get added when the first real Pydantic models land in `backend/app/api/schemas.py`. Until then `pnpm generate` is wired but has nothing to generate, and `src/index.ts` is an empty placeholder.

Does NOT live here: hand-written types (those belong with their consumer), runtime code, or the Pydantic models themselves (`backend/`).
