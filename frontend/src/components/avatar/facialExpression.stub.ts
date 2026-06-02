// INERT SEAM — animal facial expression (Avatar Phase 0). No behavior; do not wire this up.
//
// Decision (V2_TODO "AVATAR DIRECTION", 2026-06-02): the CC0 animal guides (fox/owl/otter) convey
// emotion through BODY LANGUAGE plus JAW lip-sync in v1 — they have no rigged faces. Custom Blender
// face rigs for the animals are an explicitly DEFERRED decision (P3-ish), not a Phase-0 task.
//
// This file exists only to mark where that future face-rig driver will attach, so the seam is
// discoverable instead of being invented from scratch later. It maps nothing and renders nothing.
// The live emotion already flows through `emotionToGuide` (mood/gesture) — a 3D face rig, if/when
// it ships, would consume those same fields here.

import type { GuidePresentation } from './emotionToGuide';

/**
 * Whether a guide model has a rigged FACE that can play expression morphs.
 *
 * Phase 0: always false. CC0 animals use body-language + jaw lip-sync; the VRoid humanoid's face is
 * driven by the 3D runtime's own expression channel (Phase 1+), not through this seam.
 */
export function hasFacialRig(): boolean {
  return false;
}

/**
 * INERT. Intended future shape: translate a `GuidePresentation` into per-model facial morph targets
 * for a rigged animal face. Returns no targets in v1 — body-language + jaw lip-sync carry emotion.
 *
 * TODO(P3): when/if custom animal face rigs are authored in Blender, implement this against the
 * model's morph-target names and consume `mood`/`weight` from the shared contract.
 */
export function facialMorphTargets(presentation: GuidePresentation): Record<string, number> {
  // INERT: the parameter shape is the seam's documented contract, but v1 derives no morph targets
  // from it (animals convey emotion via body-language + jaw lip-sync). `void` marks it intentionally
  // unconsumed until a face rig exists (TODO(P3)).
  void presentation;
  return {};
}
