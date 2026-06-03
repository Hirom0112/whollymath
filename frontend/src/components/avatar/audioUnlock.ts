// Safari/iOS autoplay unlock for the guide's voice (Slice AR.3 bugfix).
//
// Safari and iOS block programmatic `audio.play()` unless an <audio> element was first started
// inside a real user gesture (pointerdown/touch/key). The guide plays its banked line AFTER the
// help response arrives — outside any gesture's call stack — so the play() rejects silently and the
// learner sees only the caption bubble (no voice). The standard fix: keep ONE shared <audio>
// element, and on the learner's first gesture "bless" it by playing a tiny silent clip inside that
// gesture. Once blessed, Safari permits programmatic play() on that same element for the session.
//
// This module owns the shared element and the one-time gesture listener. The voice hook
// (`useGuideSpeech`) installs the unlock once and reuses `sharedAudioElement()` for every line.

// A 44-byte silent WAV (data URI) — enough to satisfy Safari's "started in a gesture" requirement
// without making any sound.
const SILENT_WAV =
  'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=';

// The gestures Safari/iOS accept as a user-activation that can unblock audio. Passive listeners:
// we never call preventDefault, so we must not block scrolling/taps.
const UNLOCK_EVENTS = ['pointerdown', 'touchend', 'keydown', 'mousedown'] as const;

// The single reused <audio> element. Created lazily so importing this module is side-effect-free
// (and SSR-safe). All voice lines set `.src` on this one element.
let sharedElement: HTMLAudioElement | null = null;

// True once the first gesture has played the silent clip — Safari now permits programmatic play().
let blessed = false;

// True once `installAudioUnlock()` has attached the gesture listeners (idempotency guard).
let listening = false;

/**
 * Lazily create and return the single reused <audio> element. Returns `null` when the `Audio`
 * constructor is unavailable (jsdom without the element, SSR) so callers can fall back to silent.
 */
export function sharedAudioElement(): HTMLAudioElement | null {
  if (typeof Audio === 'undefined') return null;
  if (sharedElement === null) {
    sharedElement = new Audio();
  }
  return sharedElement;
}

function blessOnce(): void {
  if (blessed) return;
  blessed = true;
  const element = sharedAudioElement();
  if (element !== null) {
    element.src = SILENT_WAV;
    element.muted = true;
    // Play the silent clip inside the gesture to bless the element; then reset so the first real
    // line starts clean and audible. The play() promise may reject in odd states — ignore it; the
    // gesture itself is what grants the activation Safari needs.
    void Promise.resolve(element.play()).catch(() => {});
    element.pause();
    element.currentTime = 0;
    element.muted = false;
  }
  removeUnlockListeners();
}

function removeUnlockListeners(): void {
  if (typeof window === 'undefined') return;
  for (const type of UNLOCK_EVENTS) {
    window.removeEventListener(type, blessOnce);
  }
  listening = false;
}

/**
 * Install the one-time gesture listener that blesses the shared <audio> element on the learner's
 * first interaction. Idempotent and a no-op during SSR or once already blessed. After the first
 * gesture fires, the listeners remove themselves.
 */
export function installAudioUnlock(): void {
  if (typeof window === 'undefined') return;
  if (blessed || listening) return;
  listening = true;
  for (const type of UNLOCK_EVENTS) {
    // Passive: this listener never calls preventDefault, so it must not block the gesture.
    window.addEventListener(type, blessOnce, { passive: true });
  }
}

/**
 * Reset the shared element + blessed/listening flags so each test starts from a clean slate.
 * Test-only: production has one element for the page's lifetime.
 */
export function resetAudioUnlockForTest(): void {
  removeUnlockListeners();
  sharedElement = null;
  blessed = false;
  listening = false;
}
