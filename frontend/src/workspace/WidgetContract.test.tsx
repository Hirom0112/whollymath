import { describe, expect, it } from 'vitest';

import type { ProblemView } from '../api';

import { selectWidget } from './WidgetContract';

// selectWidget is the single source of truth for which answer widget a problem renders (HR.A5).
// These pin the mapping so a future lesson/widget can't silently regress the choice.

function problem(over: Partial<ProblemView>): ProblemView {
  return {
    problem_id: 'p1',
    kc: 'KC_addition_unlike',
    surface_format: 'symbolic',
    statement: '1/3 + 1/4 = ?',
    ...over,
  };
}

describe('selectWidget', () => {
  it('picks the yes/no buttons for a relational judgment', () => {
    expect(selectWidget(problem({ answer_kind: 'yes_no' }))).toBe('yes_no');
  });

  it('picks the number line for a number-line surface with snap intervals', () => {
    expect(
      selectWidget(
        problem({ kc: 'KC_number_line_placement', surface_format: 'number_line', tick_segments: 4 }),
      ),
    ).toBe('number_line');
  });

  it('falls back off the number line when it has no snap intervals', () => {
    expect(
      selectWidget(problem({ surface_format: 'number_line', tick_segments: null })),
    ).toBe('fraction_editor');
  });

  it('picks the one-box number entry for common-denominator (a whole-number answer)', () => {
    expect(selectWidget(problem({ kc: 'KC_common_denominator' }))).toBe('number_entry');
  });

  it('defaults to the fraction editor for symbolic equivalence/add/sub', () => {
    expect(selectWidget(problem({ kc: 'KC_equivalence' }))).toBe('fraction_editor');
    expect(selectWidget(problem({ kc: 'KC_addition_unlike' }))).toBe('fraction_editor');
  });

  it('keeps the fraction editor for the locked-denominator fill-the-top variant', () => {
    expect(selectWidget(problem({ kc: 'KC_equivalence', given_denominator: 8 }))).toBe(
      'fraction_editor',
    );
  });

  it('prioritizes a yes/no answer even on a non-symbolic surface', () => {
    expect(
      selectWidget(problem({ kc: 'KC_number_line_placement', answer_kind: 'yes_no' })),
    ).toBe('yes_no');
  });
});
