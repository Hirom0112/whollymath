# `avatar/` — the guide (talking, emotive companion)

The capability-gated guide surface. `AvatarGuide` is the public component the app mounts; it reads the device capability and renders a runtime. Phase 0 ships **zero 3D weight**: the only runtime is the existing CSS `Mascot.tsx`, driven by the live `{ emotion, intensity }` payload (slice 1.3) through the shared `emotionToGuide` contract.

What lives here:

- `AvatarGuide.tsx` — public component; mounts the right runtime (Phase 0: always the 2D mascot).
- `emotionToGuide.ts` — the PURE, total `(emotion, intensity) → {mascotClass, mood, gesture, weight}` contract that BOTH the 2D mascot and the future 3D surface read.
- `capabilityProbe.ts` — returns `"2d"` now; Phase 1 adds the WebGL2 + perf probe.
- `facialExpression.stub.ts` — INERT seam for CC0-animal face rigs (deferred; body-language + jaw lip-sync in v1).

What does NOT live here: the guide PREFERENCE + capability state — that is `state/GuideContext.tsx`. No 3D deps in Phase 0 (no three.js).

---

## Phase-1 3D SPIKE (capability-gated, default OFF, isolated)

A behind-a-flag spike that exists for ONE purpose: let the owner run the hard acceptance test from
V2_TODO "AVATAR DIRECTION" — **does a single 3D character hold ~30fps on a low-end Chromebook?** It
does **not** touch the 2D path: with the spike off (the default), the experience is byte-for-byte the
existing `Mascot`.

Spike files:

- `Avatar3D.tsx` — an `@react-three/fiber` `<Canvas>` rendering a representative 3D character (lit,
  idle-animated, with a drei `<Stats/>` FPS meter). Default export, **lazy-loaded** so the three.js
  bundle stays in its own chunk and never bloats the main bundle.
- `Avatar3DGate.tsx` — the isolation boundary. Renders the 3D surface **only** when the device is
  capability-strong **AND** the dev opt-in flag is set; otherwise renders `null` (the host page keeps
  its existing 2D mascot). Exported from `components/index.ts` as `Avatar3DGate`.
- `avatar3dFlag.ts` — the pure dev opt-in flag (`isAvatar3DEnabled()`), default OFF.

### How to turn the spike ON

Both conditions must hold:

1. **Capability**: the device must be "strong". The Phase-0 `capabilityProbe` still returns `'2d'`
   unconditionally (the real WebGL2 + perf probe isn't wired yet), so for the perf test pass
   `forceCapable` to the gate. This bypass STILL requires the opt-in flag below — it can never turn
   the 3D path on for a default user.
2. **Dev opt-in flag** (either form):
   - URL: append **`?avatar3d=1`** to any page (one-off, no persistence), OR
   - localStorage: `localStorage.setItem('wm-avatar-3d', '1')` on the test device (persists).

To run the test, mount the gate somewhere visible (e.g. temporarily in a page during the test):

```tsx
import { Avatar3DGate } from '../components';

// forceCapable lets the test run before the real WebGL2/perf probe is wired; the flag is still
// mandatory. Drop forceCapable once `capabilityProbe` returns '3d' on capable hardware.
<Avatar3DGate forceCapable emotion="celebrate" intensity={1} />;
```

Open the page on the Chromebook **with `?avatar3d=1`**, read the on-screen FPS meter (top-left,
drei `<Stats/>`), and let it run on the idle animation. Drag to orbit. The gate stays `null` and the
default 2D mascot shows for every page load WITHOUT the flag.

### What's real vs. stubbed (be honest)

- **Real**: a live r3f render loop (per-frame idle bob/sway via `useFrame`), real lighting + shadow,
  the FPS meter, the capability+flag gate, lazy chunk-splitting, and the emotion contract wired
  through — `Avatar3D` consumes the SAME `emotionToGuide(emotion, intensity)` mapping the 2D mascot
  uses (mood → body color is a SPIKE stand-in for a VRM expression), and the word-timing from
  `useGuideSpeech` drives a first-pass open/closed jaw (`wordIndex >= 0` → mouth opens).
- **Stubbed / placeholder (under-represents real GPU load)**: the character is a `three`/drei
  **primitive placeholder**, NOT the production rigged CC0 VRM. The TalkingHead.js / `@pixiv/three-vrm`
  layer (skinned mesh, viseme/expression morph targets, real triangle count + textures) is a clearly
  marked seam (`LIPSYNC SEAM` / `TODO(P2, VRM)` in `Avatar3D.tsx`). **A "strong" 30fps reading on this
  placeholder is necessary-but-not-sufficient** evidence that the real rigged model will hold frame
  rate — the real model is heavier.

No new deps in the main bundle: `three`, `@react-three/fiber`, `@react-three/drei` load only inside
the lazy `Avatar3D` chunk, fetched only when the gate enables.
