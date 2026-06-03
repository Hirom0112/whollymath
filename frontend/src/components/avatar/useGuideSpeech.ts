// The guide's VOICE hook: play a banked help line's cached audio and drive lip-sync (Slice AR.3).
//
// Given the `SpokenAudio | null` the backend ships on a help moment (a banked nudge with cached
// audio — see `SpokenAudio` in shared-types), this hook plays the mp3 and exposes the state the
// avatar mouths to: `speaking` (true while the clip plays AND lip-sync is allowed) and `wordIndex`
// (which word is being spoken right now, derived from `wtimes`). The 2D `Mascot` reads `speaking`
// to run a talking-mouth animation; a future 3D guide reads the same fields. When `audio` is null
// the hook stays silent and returns `speaking: false` — the dynamic/LLM lines remain captions-only.
//
// Two things gate the VOICE off (captions always stay — they are the meaning, the audio is an
// enhancement): the persisted mute (`wm-mascot-muted`, the same key `Mascot` uses) and a
// missing/failed clip. `prefers-reduced-motion` does NOT silence the voice — it only calms the
// per-word lip-sync ANIMATION: under reduced motion the clip still plays, but `speaking` stays
// false and the mouth does not animate. (Reduce-motion is an animation preference, not a
// hearing/mute preference; muting that voice was the Safari-silence bug's quieter cousin.)
//
// Safari/iOS block programmatic playback unless the element was first started inside a real user
// gesture, so we reuse ONE shared <audio> element that `audioUnlock` blesses on the first gesture
// (see `audioUnlock.ts`). No API key, no network beyond the static mp3 GET — the URL is served off
// the cache (CLAUDE.md §8.1: off the turn loop).

import type { SpokenAudio } from '@whollymath/shared-types';
import { useEffect, useRef, useState } from 'react';

import { installAudioUnlock, sharedAudioElement } from './audioUnlock';

// The persisted-mute storage key — MUST match `Mascot`'s `MUTE_STORAGE_KEY` so one toggle governs
// both the caption visibility and the audio. (Kept in lock-step by this shared literal.)
const MUTE_STORAGE_KEY = 'wm-mascot-muted';

/** What the avatar needs to render a spoken line: whether it is speaking and the live word index. */
export interface GuideSpeech {
  /** True while the clip is actively playing AND lip-sync runs (drives the talking-mouth). */
  speaking: boolean;
  /** Index into `audio.words` of the word being spoken now; -1 when not animating. */
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
 * Play `audio` (if present + not muted) and track the current spoken word.
 *
 * - `audio === null` → silent, `speaking: false` (captions-only lines).
 * - muted (persisted) → silent, `speaking: false` (captions still show; the caller renders them).
 * - reduced-motion → the clip STILL plays (voice is not an animation), but `speaking` stays false
 *   and `wordIndex` stays -1 (no per-word lip-sync tick).
 * - otherwise → play the mp3 and advance `wordIndex` from `audio.wtimes` on each animation frame;
 *   `speaking` is true until the clip ends, errors, or `audio` changes.
 *
 * Re-runs whenever `audio` changes (a new help moment, identified by its `audio_url`), tearing the
 * previous clip down first so two lines never overlap. Returns `SILENT` during SSR/tests with no
 * audio element support.
 */
export function useGuideSpeech(audio: SpokenAudio | null): GuideSpeech {
  const [speech, setSpeech] = useState<GuideSpeech>(SILENT);
  // Hold the rAF handle so the effect cleanup can stop the lip-sync tick deterministically. The
  // <audio> element itself is the shared singleton from `audioUnlock` — never destroyed here.
  const frameRef = useRef<number | null>(null);

  // Bless the shared <audio> element on the learner's first gesture so Safari permits the later,
  // out-of-gesture play() that voices each banked line. Idempotent; installs once for the page.
  useEffect(() => {
    installAudioUnlock();
  }, []);

  // Key the effect on the URL (a primitive) so a re-render with an equal `audio` object does not
  // restart the clip; a genuinely new line (new URL) does.
  const audioUrl = audio?.audio_url ?? null;

  useEffect(() => {
    // No line, or the voice is muted → stay silent. Captions are unaffected (rendered by the
    // caller); this hook governs only sound + the talking animation. NOTE: reduced-motion is NOT
    // a suppressor here — the clip still plays; only the lip-sync tick is skipped (see below).
    if (audio === null || audioUrl === null || readStoredMuted()) {
      setSpeech(SILENT);
      return;
    }
    // Guard environments without the Audio constructor (jsdom without the element, SSR).
    const element = sharedAudioElement();
    if (element === null) {
      setSpeech(SILENT);
      return;
    }

    // Bind the (now non-null) shared element to a const so the closures below keep the narrowed,
    // non-nullable type — TS would widen a hoisted `function`'s capture back to `... | null`.
    const audioEl = element;
    const wtimes = audio.wtimes;
    const reduceMotion = prefersReducedMotion();
    audioEl.src = audioUrl;
    audioEl.currentTime = 0;
    let cancelled = false;

    // The current spoken word = the last word whose start time has passed. Recomputed each frame
    // from the element's own clock (`currentTime`), so it stays in sync even if playback stutters.
    const currentWordIndex = (timeSeconds: number): number => {
      let index = -1;
      for (let i = 0; i < wtimes.length; i += 1) {
        if (timeSeconds >= wtimes[i]) index = i;
        else break;
      }
      return index;
    };

    const tick = (): void => {
      if (cancelled) return;
      setSpeech({ speaking: true, wordIndex: currentWordIndex(audioEl.currentTime) });
      frameRef.current = window.requestAnimationFrame(tick);
    };

    const stop = (): void => {
      if (frameRef.current !== null) {
        window.cancelAnimationFrame(frameRef.current);
        frameRef.current = null;
      }
      if (!cancelled) setSpeech(SILENT);
    };

    audioEl.addEventListener('ended', stop);
    audioEl.addEventListener('error', stop);

    // `play()` returns a promise that rejects if autoplay is blocked or the asset 404s — a silent
    // failure (captions still carry the line), never a thrown error in render. After it resolves we
    // start the lip-sync tick ONLY when reduced motion is off; under reduced motion the voice plays
    // but the mouth stays still (`speaking` remains false).
    void Promise.resolve(audioEl.play())
      .then(() => {
        if (cancelled || reduceMotion) return;
        frameRef.current = window.requestAnimationFrame(tick);
      })
      .catch(() => {
        if (!cancelled) setSpeech(SILENT);
      });

    return () => {
      cancelled = true;
      audioEl.removeEventListener('ended', stop);
      audioEl.removeEventListener('error', stop);
      if (frameRef.current !== null) {
        window.cancelAnimationFrame(frameRef.current);
        frameRef.current = null;
      }
      // Pause (stop the current line) but do NOT destroy the shared element — it is reused for the
      // next line and must stay "blessed" for Safari.
      audioEl.pause();
      setSpeech(SILENT);
    };
    // Keyed on `audioUrl` (the line identity) and `audio` (captured for its words/wtimes). A
    // re-render with an equal `audio` object + same URL produces a stable effect; a new line
    // (new URL) tears down the old clip and starts the new one.
  }, [audioUrl, audio]);

  return speech;
}
