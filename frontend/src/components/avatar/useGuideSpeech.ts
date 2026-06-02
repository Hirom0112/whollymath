// The guide's VOICE hook: play a banked help line's cached audio and drive lip-sync (Slice AR.3).
//
// Given the `SpokenAudio | null` the backend ships on a help moment (a banked nudge with cached
// audio — see `SpokenAudio` in shared-types), this hook plays the mp3 and exposes the state the
// avatar mouths to: `speaking` (true while the clip plays) and `wordIndex` (which word is being
// spoken right now, derived from `wtimes`). The 2D `Mascot` reads `speaking` to run a talking-mouth
// animation; a future 3D guide reads the same fields. When `audio` is null the hook stays silent
// and returns `speaking: false` — the dynamic/LLM lines remain captions-only, today's behavior.
//
// Three things gate audio+animation OFF (captions always stay — they are the meaning, the audio is
// an enhancement): the persisted mute (`wm-mascot-muted`, the same key `Mascot` uses) and the OS
// `prefers-reduced-motion` setting BOTH suppress sound and lip-sync; and a missing/failed clip just
// leaves `speaking` false. No API key, no network beyond the static mp3 GET — the URL is served off
// the cache (CLAUDE.md §8.1: off the turn loop).

import type { SpokenAudio } from '@whollymath/shared-types';
import { useEffect, useRef, useState } from 'react';

// The persisted-mute storage key — MUST match `Mascot`'s `MUTE_STORAGE_KEY` so one toggle governs
// both the caption visibility and the audio. (Kept in lock-step by this shared literal.)
const MUTE_STORAGE_KEY = 'wm-mascot-muted';

/** What the avatar needs to render a spoken line: whether it is speaking and the live word index. */
export interface GuideSpeech {
  /** True while the clip is actively playing (drives the talking-mouth animation). */
  speaking: boolean;
  /** Index into `audio.words` of the word being spoken now; -1 when not speaking. */
  wordIndex: number;
}

const SILENT: GuideSpeech = { speaking: false, wordIndex: -1 };

function readStoredMuted(): boolean {
  try {
    return window.localStorage?.getItem(MUTE_STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

function prefersReducedMotion(): boolean {
  try {
    return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
  } catch {
    return false;
  }
}

/**
 * Play `audio` (if present + allowed) and track the current spoken word.
 *
 * - `audio === null` → silent, `speaking: false` (captions-only lines).
 * - muted (persisted) OR reduced-motion → silent, `speaking: false` (captions still show; the
 *   caller renders them regardless of this hook).
 * - otherwise → fetch+play the mp3 and advance `wordIndex` from `audio.wtimes` on each animation
 *   frame; `speaking` is true until the clip ends, errors, or `audio` changes.
 *
 * Re-runs whenever `audio` changes (a new help moment, identified by its `audio_url`), tearing the
 * previous clip down first so two lines never overlap. Returns `SILENT` during SSR/tests with no
 * audio element support.
 */
export function useGuideSpeech(audio: SpokenAudio | null): GuideSpeech {
  const [speech, setSpeech] = useState<GuideSpeech>(SILENT);
  // Hold the live <audio> + rAF handle so the effect cleanup can stop them deterministically.
  const elementRef = useRef<HTMLAudioElement | null>(null);
  const frameRef = useRef<number | null>(null);

  // Key the effect on the URL (a primitive) so a re-render with an equal `audio` object does not
  // restart the clip; a genuinely new line (new URL) does.
  const audioUrl = audio?.audio_url ?? null;

  useEffect(() => {
    // No line, or audio/anim suppressed → stay silent. Captions are unaffected (rendered by the
    // caller); this hook governs only sound + the talking animation.
    if (audio === null || audioUrl === null || readStoredMuted() || prefersReducedMotion()) {
      setSpeech(SILENT);
      return;
    }
    // Guard environments without the Audio constructor (jsdom without the element, SSR).
    if (typeof Audio === 'undefined') {
      setSpeech(SILENT);
      return;
    }

    const wtimes = audio.wtimes;
    const element = new Audio(audioUrl);
    elementRef.current = element;
    let cancelled = false;

    // The current spoken word = the last word whose start time has passed. Recomputed each frame
    // from the element's own clock (`currentTime`), so it stays in sync even if playback stutters.
    function currentWordIndex(timeSeconds: number): number {
      let index = -1;
      for (let i = 0; i < wtimes.length; i += 1) {
        if (timeSeconds >= wtimes[i]) index = i;
        else break;
      }
      return index;
    }

    function tick(): void {
      if (cancelled) return;
      setSpeech({ speaking: true, wordIndex: currentWordIndex(element.currentTime) });
      frameRef.current = window.requestAnimationFrame(tick);
    }

    function stop(): void {
      if (frameRef.current !== null) {
        window.cancelAnimationFrame(frameRef.current);
        frameRef.current = null;
      }
      if (!cancelled) setSpeech(SILENT);
    }

    element.addEventListener('ended', stop);
    element.addEventListener('error', stop);

    // `play()` returns a promise that rejects if autoplay is blocked or the asset 404s — a silent
    // failure (captions still carry the line), never a thrown error in render.
    void element
      .play()
      .then(() => {
        if (cancelled) return;
        frameRef.current = window.requestAnimationFrame(tick);
      })
      .catch(() => {
        if (!cancelled) setSpeech(SILENT);
      });

    return () => {
      cancelled = true;
      element.removeEventListener('ended', stop);
      element.removeEventListener('error', stop);
      if (frameRef.current !== null) {
        window.cancelAnimationFrame(frameRef.current);
        frameRef.current = null;
      }
      element.pause();
      elementRef.current = null;
      setSpeech(SILENT);
    };
    // Keyed on `audioUrl` (the line identity) and `audio` (captured for its words/wtimes). A
    // re-render with an equal `audio` object + same URL produces a stable effect; a new line
    // (new URL) tears down the old clip and starts the new one.
  }, [audioUrl, audio]);

  return speech;
}
