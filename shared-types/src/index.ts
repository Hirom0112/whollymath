// Public entry point for the API types — the ONE source of truth for the wire
// contract (TECH_STACK §2). `./generated` is produced from the backend Pydantic
// schemas (app.api.schemas) by `pnpm generate` (pydantic2ts). Do NOT hand-edit the
// generated file: change the Pydantic models and re-run generation, so the backend
// and frontend cannot drift.
//
// Note: pydantic2ts emits per-field duplicate aliases for an enum that is referenced
// by a Field carrying a description (e.g. `SurfaceState1` / `SurfaceState2` are
// byte-identical to `SurfaceState`). They are harmless; consumers import the
// canonical names (`SurfaceState`, `ProblemView`, …).
export * from './generated';
