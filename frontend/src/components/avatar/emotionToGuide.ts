// The single emotion→presentation contract shared by EVERY guide surface (Avatar Phase 0).
//
// The backend already ships `{ emotion, intensity }` (slice 1.3 — `hint_emotion`/`hint_intensity`
// on the turn response, `emotion`/`intensity` on InterventionView). This module is the ONE place
// that turns that payload into how a guide should look/behave, so the 2D `Mascot.tsx` (Phase 0)
// and the future 3D surface (Phase 1+) read the exact same mapping and can never drift apart.
//
// PURE + TOTAL + DETERMINISTIC: every one of the five `Emotion` values has an entry (compile-time
// enforced by the `Record<Emotion, ...>` table), no I/O, no randomness, same input ⇒ same output.

import type { Emotion } from '@whollymath/shared-types';

/**
 * How a guide should present a given emotion.
 *
 * - `mascotClass` — the namespaced CSS class the 2D mascot applies NOW (`wm-guide-emotion-*`).
 *   Namespaced per the global-CSS footgun (reused class names collide app-wide).
 * - `mood` / `gesture` — forward-looking, abstract fields the 3D path (TalkingHead.js `playGesture`,
 *   VRM expression morphs) will read. They carry no 2D behavior today; they exist so the contract
 *   is complete the moment a 3D surface is wired, with no second mapping to invent.
 * - `weight` — a bounded [0,1] scalar derived from `intensity`; how strongly to play the emotion
 *   (animation amplitude in 2D, gesture/expression strength in 3D).
 */
export interface GuidePresentation {
  /** The `wm-guide-emotion-*` class the 2D mascot applies. */
  mascotClass: string;
  /** Abstract VRM/expression mood the 3D path will map to a face/posture. */
  mood: string;
  /** Abstract body gesture the 3D path will map to a TalkingHead.js `playGesture` clip. */
  gesture: string;
  /** Bounded [0,1] strength derived from the backend `intensity`. */
  weight: number;
}

// One row per emotion. `Record<Emotion, ...>` makes this table TOTAL by construction: adding a new
// `Emotion` to the shared type without a row here is a compile error, so the contract can never go
// partial silently. `mood`/`gesture` follow the Phase-0 brief (celebrate→cheer, think→ponder,
// encourage→point, reassure→nod, neutral→idle).
const PRESENTATION: Record<Emotion, Omit<GuidePresentation, 'weight'>> = {
  encourage: { mascotClass: 'wm-guide-emotion-encourage', mood: 'warm', gesture: 'point' },
  celebrate: { mascotClass: 'wm-guide-emotion-celebrate', mood: 'joyful', gesture: 'cheer' },
  think: { mascotClass: 'wm-guide-emotion-think', mood: 'curious', gesture: 'ponder' },
  reassure: { mascotClass: 'wm-guide-emotion-reassure', mood: 'calm', gesture: 'nod' },
  neutral: { mascotClass: 'wm-guide-emotion-neutral', mood: 'attentive', gesture: 'idle' },
};

/** Clamp an arbitrary number into [0,1]; NaN/±Infinity collapse to a safe 0. */
function clamp01(value: number): number {
  if (!Number.isFinite(value)) return 0;
  if (value < 0) return 0;
  if (value > 1) return 1;
  return value;
}

/**
 * Map the live `{ emotion, intensity }` payload to a complete `GuidePresentation`.
 *
 * Total over all five `Emotion` values and deterministic. `intensity` is clamped to a bounded
 * [0,1] `weight` (the backend documents it as a [0,1] scalar, but we defend the boundary here so
 * an out-of-range or NaN value can never produce an unbounded animation).
 */
export function emotionToGuide(emotion: Emotion, intensity: number): GuidePresentation {
  return { ...PRESENTATION[emotion], weight: clamp01(intensity) };
}
