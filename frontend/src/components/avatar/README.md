# `avatar/` — the guide (talking, emotive companion)

The capability-gated guide surface. `AvatarGuide` is the public component the app mounts; it reads the device capability and renders a runtime. Phase 0 ships **zero 3D weight**: the only runtime is the existing CSS `Mascot.tsx`, driven by the live `{ emotion, intensity }` payload (slice 1.3) through the shared `emotionToGuide` contract.

What lives here:

- `AvatarGuide.tsx` — public component; mounts the right runtime (Phase 0: always the 2D mascot).
- `emotionToGuide.ts` — the PURE, total `(emotion, intensity) → {mascotClass, mood, gesture, weight}` contract that BOTH the 2D mascot and the future 3D surface read.
- `capabilityProbe.ts` — returns `"2d"` now; Phase 1 adds the WebGL2 + perf probe.
- `facialExpression.stub.ts` — INERT seam for CC0-animal face rigs (deferred; body-language + jaw lip-sync in v1).

What does NOT live here: the guide PREFERENCE + capability state — that is `state/GuideContext.tsx`. No 3D deps in Phase 0 (no three.js).
