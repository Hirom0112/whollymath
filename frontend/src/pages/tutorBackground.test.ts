import { describe, expect, it } from 'vitest';

import { lessonBackground, TUTOR_BACKGROUNDS } from './Tutor';

// The per-lesson backdrop picker (lessonBackground) must be STABLE within a lesson (same KC →
// same backdrop every render/problem) and pick a real in-range image. These pin that contract.

describe('lessonBackground', () => {
  it('is stable for the same KC (no reshuffle between problems in a lesson)', () => {
    const a = lessonBackground('KC_number_line_placement');
    const b = lessonBackground('KC_number_line_placement');
    expect(a).toBe(b);
  });

  it('returns a css url() pointing at one of the real backdrops', () => {
    const bg = lessonBackground('KC_equivalence');
    const match = /^url\('(\/tutor-bg-\d+\.jpg)'\)$/.exec(bg);
    expect(match).not.toBeNull();
    expect(TUTOR_BACKGROUNDS).toContain(match?.[1]);
  });

  it('always resolves to an in-range backdrop across many KC ids', () => {
    for (const kc of [
      'KC_number_line_placement',
      'KC_equivalence',
      'KC_common_denominator',
      'KC_addition_unlike',
      'KC_subtraction_unlike',
      'KC_ratio_meaning',
      'KC_unit_rate',
      'KC_integer_add_sub',
      '',
    ]) {
      const match = /^url\('(\/tutor-bg-\d+\.jpg)'\)$/.exec(lessonBackground(kc));
      expect(TUTOR_BACKGROUNDS).toContain(match?.[1]);
    }
  });

  it('varies the backdrop across different lessons (not all identical)', () => {
    const picks = new Set(
      ['KC_equivalence', 'KC_unit_rate', 'KC_integer_add_sub', 'KC_absolute_value'].map(
        lessonBackground,
      ),
    );
    expect(picks.size).toBeGreaterThan(1);
  });
});
