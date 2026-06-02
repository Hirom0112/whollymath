import type { Emotion } from '@whollymath/shared-types';
import { useCallback, useEffect, useState } from 'react';

import { emotionToGuide } from './avatar/emotionToGuide';
import './Mascot.css';

// Where the mute preference is remembered, so the choice persists across reloads/sessions.
const MUTE_STORAGE_KEY = 'wm-mascot-muted';

function readStoredMuted(): boolean {
  try {
    return window.localStorage?.getItem(MUTE_STORAGE_KEY) === '1';
  } catch {
    // Private mode / storage disabled — fall back to unmuted (captions-first default).
    return false;
  }
}

function writeStoredMuted(muted: boolean): void {
  try {
    window.localStorage?.setItem(MUTE_STORAGE_KEY, muted ? '1' : '0');
  } catch {
    // Best-effort; a failed write just means the toggle isn't remembered next load.
  }
}

/**
 * The WhollyMath pie mascot — the reusable character figure (conic-gradient pie
 * face with eyes, smile, arms, legs). Pure presentation, no animation or
 * positioning of its own: callers wrap it and animate the wrapper (the landing's
 * idle-bob → roll-off, the cold-start's roll-in). Rendered at a base 130×100 box;
 * scale it via a transform on the wrapper.
 *
 * Speech (Slice AR.1): pass `speech` to make the mascot SAY a short line in a bubble beside
 * the figure (e.g. routine number-line verdict narration). Captions are shown by default —
 * this app has no audio yet, so the bubble IS the speech. A small MUTE control suppresses any
 * future audio/auto-speak; honestly, with no audio it simply hides the speech bubble. The
 * preference is persisted (localStorage) so a learner who mutes stays muted. Captions-first per
 * the teacher panel: default is UNMUTED (the line is always shown unless the learner opts out).
 *
 * When `speech` is omitted the mascot renders exactly as before (a bare figure with no bubble or
 * control), so existing callers (Landing, CourseMap, PiMenu) are unaffected — they wrap a plain,
 * aria-hidden figure.
 *
 * Emotion (Avatar Phase 0): pass the live `{ emotion, intensity }` the backend already ships
 * (slice 1.3) to make the figure visibly REFLECT it — encourage / celebrate / think / reassure /
 * neutral. The mapping is owned by the shared `emotionToGuide` contract (so the future 3D guide
 * reads the same thing); here it applies a namespaced `.wm-guide-emotion-*` class plus an intensity
 * weight CSS var. Omit `emotion` and the figure is exactly as before — no emotion styling at all.
 */
export function Mascot({
  speech,
  speechKind = 'say',
  emotion,
  intensity = 0,
  speaking = false,
}: {
  /** A short line for the mascot to speak in a bubble; omit for a bare, silent figure. */
  speech?: string;
  /** Tints the bubble by intent (correct verdict vs. a neutral line); purely visual. */
  speechKind?: 'correct' | 'neutral' | 'say';
  /** The live backend emotion to reflect; omit to leave the figure unstyled (legacy behavior). */
  emotion?: Emotion;
  /** How strongly to play `emotion`, a [0,1] scalar (clamped by the shared contract). */
  intensity?: number;
  /**
   * True while the mascot is actively SPEAKING cached audio (Slice AR.3): runs a subtle
   * talking-mouth animation. Driven by `useGuideSpeech`; defaults false, so every existing caller
   * (Landing, CourseMap, PiMenu) that passes nothing renders the still figure exactly as before.
   * Captions (the speech bubble) are independent of this — they always show regardless of audio.
   */
  speaking?: boolean;
} = {}): React.JSX.Element {
  const [muted, setMuted] = useState<boolean>(() => readStoredMuted());

  // The shared emotion→presentation contract. Only consulted when an emotion is supplied, so the
  // no-emotion path is byte-for-byte the old figure (no class, no CSS var).
  const guide = emotion !== undefined ? emotionToGuide(emotion, intensity) : null;

  // Re-read the stored preference if it changed in another tab/route (keeps the toggle honest
  // across the app). We only subscribe while a speech line could be shown.
  useEffect(() => {
    if (speech === undefined) return;
    function onStorage(event: StorageEvent): void {
      if (event.key === MUTE_STORAGE_KEY) setMuted(readStoredMuted());
    }
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, [speech]);

  const toggleMuted = useCallback(() => {
    setMuted((m) => {
      const next = !m;
      writeStoredMuted(next);
      return next;
    });
  }, []);

  // The talking-mouth class is namespaced (`.wm-guide-*`) to avoid the global-CSS collision footgun
  // (reused class names collide app-wide). Only added while speaking, so the idle figure is byte-
  // for-byte the legacy one. The base figure class string is composed so the no-emotion / no-speak
  // path stays exactly `wm-mascot-figure`.
  const figureClass = [
    'wm-mascot-figure',
    guide?.mascotClass,
    speaking ? 'wm-guide-speaking' : null,
  ]
    .filter(Boolean)
    .join(' ');

  const figure = (
    <div
      className={figureClass}
      // The intensity weight drives animation amplitude in CSS (clamped [0,1] by the contract).
      // Only set when an emotion is in play, so the legacy figure carries no inline style.
      style={guide ? ({ '--wm-guide-weight': guide.weight } as React.CSSProperties) : undefined}
      data-emotion={emotion}
      data-speaking={speaking ? 'true' : undefined}
    >
      <div className="wm-mascot-pie">
        <div className="wm-mascot-smile" />
        {/* The animated talking mouth — only visible/animating while `speaking` (CSS gates it on
            the `.wm-guide-speaking` ancestor). Decorative; the caption carries the words. */}
        <div className="wm-guide-mouth" aria-hidden="true" />
      </div>
      <div className="wm-mascot-arm-l" />
      <div className="wm-mascot-arm-r" />
      <div className="wm-mascot-leg-l" />
      <div className="wm-mascot-leg-r" />
    </div>
  );

  // No speech requested → the original bare figure, untouched (existing callers).
  if (speech === undefined) return figure;

  return (
    <div className="wm-mascot-speak">
      {/* The bubble is the caption; it is hidden when muted. role="status" + aria-live so a
          screen reader announces a freshly-spoken line without stealing focus. */}
      {!muted ? (
        <p className={`wm-mascot-bubble wm-mascot-bubble--${speechKind}`} role="status">
          {speech}
        </p>
      ) : null}
      <div className="wm-mascot-fig-wrap">
        {/* The figure itself is decorative; the spoken line carries the meaning. */}
        <span aria-hidden="true">{figure}</span>
        {/* Mute control — honest about there being no audio yet: it shows/hides the caption.
            aria-pressed states the toggle; the label says what it does in this captions-only app. */}
        <button
          type="button"
          className="wm-mascot-mute"
          aria-pressed={muted}
          aria-label={muted ? 'Show what the mascot says' : 'Hide what the mascot says'}
          onClick={toggleMuted}
        >
          <span aria-hidden="true">{muted ? 'Show caption' : 'Mute'}</span>
        </button>
      </div>
    </div>
  );
}
