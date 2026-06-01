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
    // widget_id is now the AUTHORITATIVE signal for the fraction-vs-scalar split: the backend emits
    // 'fraction_editor' for a fraction-answer KC and 'number_entry' for a SYMBOLIC scalar KC, and
    // selectWidget routes on it (no KC-name list). Default to the fraction editor here.
    widget_id: 'fraction_editor',
    ...over,
  };
}

describe('selectWidget', () => {
  it('picks the yes/no buttons for a relational judgment', () => {
    expect(selectWidget(problem({ answer_kind: 'yes_no' }))).toBe('yes_no');
  });

  it('picks the expression input when the backend emits widget_id "expression"', () => {
    // The first widget chosen by the authoritative widget_id (not the kc): KC_write_expressions
    // renders on the EXPRESSION surface, whose widget_id is "expression" + answer_kind "expression".
    expect(
      selectWidget(
        problem({
          kc: 'KC_write_expressions',
          surface_format: 'expression',
          answer_kind: 'expression',
          widget_id: 'expression',
        }),
      ),
    ).toBe('expression');
  });

  it('picks the number line for a number-line surface with snap intervals', () => {
    expect(
      selectWidget(
        problem({
          kc: 'KC_number_line_placement',
          surface_format: 'number_line',
          tick_segments: 4,
        }),
      ),
    ).toBe('number_line');
  });

  it('falls back off the number line when it has no snap intervals', () => {
    expect(selectWidget(problem({ surface_format: 'number_line', tick_segments: null }))).toBe(
      'fraction_editor',
    );
  });

  it('picks the one-box number entry when the backend emits widget_id "number_entry"', () => {
    // A SYMBOLIC scalar KC (percent, an integer sum, a polygon area, …) answers with a plain
    // integer / decimal / negative, so the backend marks it 'number_entry' and we route on that —
    // NO KC-name list. The kc is incidental; the authoritative signal is widget_id.
    expect(selectWidget(problem({ kc: 'KC_percent', widget_id: 'number_entry' }))).toBe(
      'number_entry',
    );
    expect(
      selectWidget(problem({ kc: 'KC_integer_add_subtract', widget_id: 'number_entry' })),
    ).toBe('number_entry');
  });

  it('routes by widget_id, not a hardcoded KC list (the old common_denominator/unit_rate path)', () => {
    // The former KC-name branch is gone: these KCs now reach number entry only via the backend's
    // widget_id, exactly like every other scalar KC. With widget_id 'number_entry' they route there;
    // the KC string alone no longer drives the choice.
    expect(selectWidget(problem({ kc: 'KC_common_denominator', widget_id: 'number_entry' }))).toBe(
      'number_entry',
    );
    expect(selectWidget(problem({ kc: 'KC_unit_rate', widget_id: 'number_entry' }))).toBe(
      'number_entry',
    );
  });

  it('defaults to the fraction editor for a symbolic fraction KC (widget_id "fraction_editor")', () => {
    expect(selectWidget(problem({ kc: 'KC_equivalence', widget_id: 'fraction_editor' }))).toBe(
      'fraction_editor',
    );
    expect(selectWidget(problem({ kc: 'KC_addition_unlike', widget_id: 'fraction_editor' }))).toBe(
      'fraction_editor',
    );
  });

  it('keeps the fraction editor for the locked-denominator fill-the-top variant', () => {
    expect(
      selectWidget(
        problem({ kc: 'KC_equivalence', widget_id: 'fraction_editor', given_denominator: 8 }),
      ),
    ).toBe('fraction_editor');
  });

  it('prioritizes a yes/no answer even on a non-symbolic surface', () => {
    expect(selectWidget(problem({ kc: 'KC_number_line_placement', answer_kind: 'yes_no' }))).toBe(
      'yes_no',
    );
  });
});
