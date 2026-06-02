// Decides which guide RUNTIME a given device can drive (Avatar Phase 0).
//
// Phase 0 ships zero 3D weight by design, so the probe ALWAYS returns "2d": every user gets the
// existing CSS `Mascot.tsx`. Phase 1 will add the real detection (WebGL2 availability + a short
// perf probe; the hard acceptance gate is ~30fps on a real low-end Chromebook — see V2_TODO
// "AVATAR DIRECTION"). The contract is fixed now so nothing downstream changes when 3D lands.

/** The guide runtime a device can drive. "3d" is unreachable until Phase 1 wires the real probe. */
export type GuideCapability = '2d' | '3d';

/**
 * Probe the device for the guide runtime it can drive.
 *
 * Phase 0: unconditionally "2d". Synchronous and side-effect-free so it can run during context
 * init without blocking.
 */
export function probeCapability(): GuideCapability {
  // TODO(P1): WebGL2 + perf probe. Detect WebGL2 + a basic GPU tier, run a short frame-time probe,
  // and return "3d" only when the ~30fps low-end-Chromebook gate is met; otherwise stay "2d".
  return '2d';
}
