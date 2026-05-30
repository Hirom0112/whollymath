import type { ProblemView } from '../api';

/**
 * The workspace-widget contract (Slice HR.A5).
 *
 * One place decides which answer widget renders a problem — so the live tutor (`Tutor.tsx`) and any
 * future surface share a single, tested source of truth instead of scattering `kc === ...` and
 * format checks inline. This is the frontend half of the backend `WidgetId` mapping in
 * `domain/lesson_spec.py` (HR.A1): when a new lesson declares its representations + widgets there,
 * the surface picks the matching widget here for free.
 *
 * Two exports:
 *  - {@link WorkspaceWidgetProps} — the common shape every answer widget conforms to (a controlled
 *    input: a value, an onChange, and a disabled flag). Per-widget extras (axis bounds, a locked
 *    denominator, …) are layered on top by each widget.
 *  - {@link selectWidget} — given a problem, returns which widget kind to render.
 */

/** The answer widgets the workspace can render, aligned to the backend `WidgetId` vocabulary. */
export type WidgetKind =
  | 'number_line' // NumberLine — drag a marker (placement / a 0–1 arithmetic result)
  | 'yes_no' // YesNo — a relational judgment ("same amount?", "is a > b?")
  | 'number_entry' // NumberEntry — a single whole number (a shared piece-size; §3.4.1)
  | 'expression' // ExpressionInput — a typed algebra string (write/equivalent expressions)
  | 'fraction_editor'; // SymbolicEditor — the two-box fraction input (the default)

/** The controlled-input contract every answer widget satisfies (HR.A5). */
export interface WorkspaceWidgetProps<TValue> {
  /** The current answer value (widget-specific: a tick, a fraction, a string, a boolean…). */
  value: TValue;
  /** Report a new value as the learner manipulates the widget. */
  onChange: (next: TValue) => void;
  /** When true, the widget is read-only (e.g. while a verdict is showing). */
  disabled?: boolean;
}

/**
 * Choose the answer widget for a problem — the single source of truth (HR.A5).
 *
 * Selection is driven by what the problem ASKS (its answer/format fields), never by page-level
 * state, so the same KC can be answered in more than one representation (mastery rule 2). Order
 * matters: the most specific signal wins.
 *
 * TODO(T3→T1, HR.A5): the whole-number-answer branch below is the one case the wire contract can't
 * yet express. These KCs' answers are a single whole number, but `surface_format`/`answer_kind` read
 * exactly like the fraction editor ('symbolic' + 'numeric'), and the backend `widget_id` is derived
 * from representation alone (SYMBOLIC → 'fraction_editor'), so it can't distinguish them. Flagged to
 * T1 to extend the HR.A1 `WidgetId` to carry 'number_entry'; once it does, this branch reads
 * `problem.widget_id` and the kc references drop.
 */
export function selectWidget(problem: ProblemView): WidgetKind {
  // A relational yes/no judgment is answered with the buttons, never a fraction input — the server
  // signals it via `answer_kind` so a yes/no question can't land on a typing surface.
  if (problem.answer_kind === 'yes_no') return 'yes_no';

  // A typed algebra expression (write/equivalent expressions): the backend derives widget_id
  // "expression" from the EXPRESSION representation (HR.A5), so we route on the widget_id string
  // directly — no kc branch. This is the first widget chosen by widget_id, the contract the rest
  // collapse onto once every KC carries an authoritative widget_id.
  if (problem.widget_id === 'expression') return 'expression';

  // A number-line surface with snap intervals → the draggable marker (placement, or an arithmetic
  // result that lands on the line).
  if (problem.surface_format === 'number_line' && problem.tick_segments != null) {
    return 'number_line';
  }

  // A handful of symbolic KCs answer with a single whole number, not a fraction, so they get the
  // one-box entry rather than the two-box fraction editor: common-denominator's shared piece-size
  // (§3.4.1), a unit rate ("2 mph"), and an equivalent-ratio missing term. The only kc-keyed case —
  // see the TODO above; it collapses into the widget-id path when T1 surfaces 'number_entry'.
  if (
    problem.kc === 'KC_common_denominator' ||
    problem.kc === 'KC_unit_rate' ||
    problem.kc === 'KC_equivalent_ratios'
  ) {
    return 'number_entry';
  }

  // Everything else (symbolic equivalence/add/sub, incl. the locked-denominator fill-the-top variant
  // signalled by `given_denominator`) is the fraction editor.
  return 'fraction_editor';
}
