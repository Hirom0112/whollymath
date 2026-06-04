// PHASE-1 SPIKE — the dev opt-in flag that, TOGETHER with a capability-strong probe, is the ONLY way
// the 3D avatar mounts. Default is OFF, so the default experience is the unchanged 2D Mascot.
//
// Two ways to opt in (either is sufficient), both intentionally explicit and developer-driven:
//   1. URL query param `?avatar3d=1`  — one-off, no persistence (handy for a quick Chromebook test).
//   2. localStorage `wm-avatar-3d` = '1' — persists across reloads (set once on the test device).
//
// This is a PURE read of the environment (no side effects), so the gate's decision is testable and
// the default-OFF isolation guarantee is a single, auditable function. Storage/URL access is wrapped
// so SSR / private-mode / no-`window` environments safely return false (stay 2D).

/** The localStorage key for the persistent spike opt-in. Namespaced `wm-*` per the global-CSS/key
 * convention so it can't collide with another preference. */
export const AVATAR_3D_FLAG_KEY = 'wm-avatar-3d';

/** The URL query param for a one-off opt-in (no persistence). */
export const AVATAR_3D_QUERY_PARAM = 'avatar3d';

function flagFromStorage(): boolean {
  try {
    return window.localStorage?.getItem(AVATAR_3D_FLAG_KEY) === '1';
  } catch {
    return false;
  }
}

function flagFromQuery(): boolean {
  try {
    if (typeof window === 'undefined' || !window.location) return false;
    return new URLSearchParams(window.location.search).get(AVATAR_3D_QUERY_PARAM) === '1';
  } catch {
    return false;
  }
}

/**
 * Whether the developer has explicitly opted into the 3D avatar spike. Default FALSE.
 *
 * True only when `?avatar3d=1` is in the URL OR `localStorage['wm-avatar-3d'] === '1'`. Pure and
 * side-effect-free; safe to call during render or in tests.
 */
export function isAvatar3DEnabled(): boolean {
  return flagFromQuery() || flagFromStorage();
}
