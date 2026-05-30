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
    // widget_id is required on the wire type (T1, 78b4f85) but selectWidget intentionally does NOT
    // read it yet — it's representation-only, missing yes_no/number_entry (HANDOFF_T3 §2a / B1), so
    // the frontend keeps choosing by answer_kind/kc. Present here only to satisfy the type.
    widget_id: 'fraction_editor',
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

  it('picks the one-box number entry for the Grade-6 whole-number-answer KCs', () => {
    // A unit rate ("2 mph") and an equivalent-ratio missing term answer with a single whole number,
    // so they get number entry, not the two-box fraction editor — even though both read as
    // symbolic+numeric on the wire (see the WidgetContract TODO).
    expect(selectWidget(problem({ kc: 'KC_unit_rate' }))).toBe('number_entry');
    expect(selectWidget(problem({ kc: 'KC_equivalent_ratios' }))).toBe('number_entry');
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
