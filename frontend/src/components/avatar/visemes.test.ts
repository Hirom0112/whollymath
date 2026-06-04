import { describe, expect, it } from 'vitest';

import { type Viseme, visemeAt, visemeForGrapheme } from './visemes';

describe('visemeForGrapheme', () => {
  it('maps vowels and key consonants to distinct mouth shapes', () => {
    expect(visemeForGrapheme('a')).toBe('open');
    expect(visemeForGrapheme('E')).toBe('wide'); // case-insensitive
    expect(visemeForGrapheme('o')).toBe('round');
    expect(visemeForGrapheme('u')).toBe('narrow');
    expect(visemeForGrapheme('m')).toBe('closed');
    expect(visemeForGrapheme('p')).toBe('closed');
    expect(visemeForGrapheme('f')).toBe('teeth');
    expect(visemeForGrapheme('l')).toBe('lips');
    expect(visemeForGrapheme('s')).toBe('consonant');
  });

  it('maps non-letters to rest', () => {
    expect(visemeForGrapheme(' ')).toBe('rest');
    expect(visemeForGrapheme('!')).toBe('rest');
  });
});

describe('visemeAt', () => {
  // One word "map" spanning 0.0–1.0s: letters m,a,p evenly fill the duration.
  const words = ['map'];
  const wtimes = [0.0];
  const wdurations = [0.9];

  it('rests before the first word and after the last ends', () => {
    expect(visemeAt(words, wtimes, [-0.1] as never, -0.1)).toBe('rest');
    expect(visemeAt(words, wtimes, wdurations, -0.5)).toBe('rest'); // before start
    expect(visemeAt(words, wtimes, wdurations, 2.0)).toBe('rest'); // after end
  });

  it('walks the graphemes of the word as time advances', () => {
    // 0.9s / 3 letters → m:[0,0.3) a:[0.3,0.6) p:[0.6,0.9)
    expect(visemeAt(words, wtimes, wdurations, 0.05)).toBe('closed'); // m
    expect(visemeAt(words, wtimes, wdurations, 0.45)).toBe('open'); // a
    expect(visemeAt(words, wtimes, wdurations, 0.8)).toBe('closed'); // p
  });

  it('rests in the gap between two words', () => {
    const two = ['ab', 'cd'];
    const starts = [0.0, 1.0];
    const durs = [0.4, 0.4]; // word 1 ends at 0.4, word 2 starts at 1.0 → gap [0.4,1.0)
    expect(visemeAt(two, starts, durs, 0.6)).toBe('rest');
    expect(visemeAt(two, starts, durs, 1.1)).not.toBe('rest'); // into the second word
  });

  it('never throws on empty input or a zero-length duration', () => {
    expect(visemeAt([], [], [], 0.5)).toBe('rest');
    const got: Viseme = visemeAt(['x'], [0], [0], 0.0); // zero duration
    expect(got).toBe('rest');
  });
});
