import type { Emotion } from '@whollymath/shared-types';
import { describe, expect, it } from 'vitest';

import { emotionToGuide } from './emotionToGuide';

// The shared emotion→presentation contract is load-bearing: BOTH the 2D mascot and the future 3D
// guide read it, so it must be TOTAL (every Emotion handled), DETERMINISTIC (same input ⇒ same
// output), and its weight must stay bounded in [0,1] regardless of what the backend sends.

const ALL_EMOTIONS: Emotion[] = ['encourage', 'celebrate', 'think', 'reassure', 'neutral'];

describe('emotionToGuide', () => {
  it('is total: returns a complete presentation for every Emotion', () => {
    for (const emotion of ALL_EMOTIONS) {
      const guide = emotionToGuide(emotion, 0.5);
      expect(guide.mascotClass).toBe(`wm-guide-emotion-${emotion}`);
      expect(guide.mood.length).toBeGreaterThan(0);
      expect(guide.gesture.length).toBeGreaterThan(0);
      expect(guide.weight).toBe(0.5);
    }
  });

  it('maps each emotion to its documented forward-looking gesture', () => {
    expect(emotionToGuide('encourage', 1).gesture).toBe('point');
    expect(emotionToGuide('celebrate', 1).gesture).toBe('cheer');
    expect(emotionToGuide('think', 1).gesture).toBe('ponder');
    expect(emotionToGuide('reassure', 1).gesture).toBe('nod');
    expect(emotionToGuide('neutral', 1).gesture).toBe('idle');
  });

  it('is deterministic: same input yields a deep-equal output', () => {
    for (const emotion of ALL_EMOTIONS) {
      expect(emotionToGuide(emotion, 0.3)).toEqual(emotionToGuide(emotion, 0.3));
    }
  });

  it('maps intensity to a bounded [0,1] weight', () => {
    expect(emotionToGuide('celebrate', 0).weight).toBe(0);
    expect(emotionToGuide('celebrate', 0.42).weight).toBe(0.42);
    expect(emotionToGuide('celebrate', 1).weight).toBe(1);
    // Out-of-range inputs clamp to the boundary; non-finite inputs (NaN/±Infinity) collapse to a
    // safe 0 so a missing/garbage intensity reads as "no emotional strength", never unbounded.
    expect(emotionToGuide('celebrate', 5).weight).toBe(1);
    expect(emotionToGuide('celebrate', -3).weight).toBe(0);
    expect(emotionToGuide('celebrate', Number.NaN).weight).toBe(0);
    expect(emotionToGuide('celebrate', Number.POSITIVE_INFINITY).weight).toBe(0);
  });
});
