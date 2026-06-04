// Phoneme-level lip-sync: map the spoken stream to mouth shapes (visemes) over time.
//
// The avatar ships `words` + `wtimes` + `wdurations` (the ElevenLabs word timing) on every clip,
// banked or live-synthesised. Word-level timing alone only tells us WHEN a word is spoken, which is
// why the old mouth just pulsed open/close. This module turns that same data into a PHONEME-class
// viseme stream — the mouth SHAPE at any instant — so the lip-sync reads as speech, not a buzzer.
//
// It is a grapheme→viseme approximation (Preston-Blair-style shapes), derived purely from the text +
// timing we already have: no external binary (Rhubarb is an optional higher-fidelity acoustic
// upgrade — see `rhubarb_visemes.stub.py`), no re-render, no network. Graphemes are a good proxy for
// mouth shape (vowels open, bilabials close, f/v tuck the lip) for a stylised mouth; the same viseme
// vocabulary is what a future 3D (TalkingHead/VRM) guide consumes, so this generalises upward.
//
// Pure + deterministic: `visemeAt` is a function of (words, wtimes, wdurations, timeSeconds) only, so
// it is unit-tested without a clock or the DOM.

/** The mouth shapes the avatar can render. `rest` is the closed/neutral idle (silence + gaps). */
export type Viseme =
  | 'rest' // silence / between words — closed, neutral
  | 'closed' // m b p — lips pressed together
  | 'open' // a i — jaw open, wide
  | 'wide' // e — lips spread, slightly open
  | 'round' // o — lips rounded, open
  | 'narrow' // u w — small rounded pucker
  | 'teeth' // f v — lower lip to upper teeth
  | 'lips' // l t d n th — tongue tip / teeth
  | 'consonant'; // other consonants — slight open

// Grapheme → viseme. Lower-cased single characters; anything not listed (digits already never reach
// here — help lines are read as words; punctuation) falls back to `rest` via the lookup default.
const _GRAPHEME_VISEME: Readonly<Record<string, Viseme>> = {
  a: 'open',
  i: 'open',
  e: 'wide',
  y: 'wide',
  o: 'round',
  u: 'narrow',
  w: 'narrow',
  m: 'closed',
  b: 'closed',
  p: 'closed',
  f: 'teeth',
  v: 'teeth',
  l: 'lips',
  t: 'lips',
  d: 'lips',
  n: 'lips',
  c: 'consonant',
  g: 'consonant',
  h: 'consonant',
  j: 'consonant',
  k: 'consonant',
  q: 'consonant',
  r: 'consonant',
  s: 'consonant',
  x: 'consonant',
  z: 'consonant',
};

/** The viseme for a single character (letter → mouth shape); non-letters → `rest`. */
export function visemeForGrapheme(char: string): Viseme {
  return _GRAPHEME_VISEME[char.toLowerCase()] ?? 'rest';
}

/**
 * The mouth shape at `timeSeconds` for a spoken line.
 *
 * Finds the word being spoken at that instant (the last word whose start has passed and whose
 * duration has not elapsed), then the grapheme within it from how far through the word we are
 * (`(t - start) / duration` → letter index), and maps that grapheme to a viseme. Returns `rest`
 * before the first word, after the last word ends, and in the silent gaps between words — so the
 * mouth closes between words instead of holding a shape.
 *
 * `wtimes`/`wdurations` are index-aligned with `words` (the SpokenAudio contract). Defensive against
 * empty input and a zero-length word/duration (→ `rest`), so it never throws into the render loop.
 */
export function visemeAt(
  words: readonly string[],
  wtimes: readonly number[],
  wdurations: readonly number[],
  timeSeconds: number,
): Viseme {
  for (let i = 0; i < words.length; i += 1) {
    const start = wtimes[i];
    const duration = wdurations[i];
    if (start === undefined || duration === undefined) continue;
    if (timeSeconds < start) break; // not reached this word yet → we're in a leading/inter-word gap
    if (timeSeconds >= start + duration) continue; // this word already finished → check the next
    const word = words[i];
    if (word.length === 0 || duration <= 0) return 'rest';
    const progress = (timeSeconds - start) / duration; // 0..1 through the word
    const letterIndex = Math.min(word.length - 1, Math.floor(progress * word.length));
    return visemeForGrapheme(word[letterIndex]);
  }
  return 'rest';
}
