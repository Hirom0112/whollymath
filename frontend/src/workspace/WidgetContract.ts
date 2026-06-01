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
  | 'number_entry' // NumberEntry — a single scalar value (integer / decimal / negative / a/b)
  | 'expression' // ExpressionInput — a typed algebra string (write/equivalent expressions)
  | 'inequality' // InequalityInput — a one-variable inequality (relation + boundary; 6.EE.8)
  | 'coordinate_plane' // CoordinatePlane — plotted integer point(s) (6.NS.8 / 6.EE.9 / 6.G.3)
  | 'classify_sets' // ClassifySets — the number-set classification (TEKS 6.2A)
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
 * The whole-number / scalar branch is now driven by the authoritative `widget_id` the backend emits
 * (HR.A1 extended `WidgetId` with 'number_entry'): a SYMBOLIC scalar KC (percent, gcf/lcm, an
 * integer sum, an exponent, an area/volume, a summary statistic, …) carries widget_id
 * 'number_entry'; a SYMBOLIC fraction KC carries 'fraction_editor'. The old hardcoded KC-name list
 * (common_denominator / unit_rate / equivalent_ratios) is gone — the backend decides per KC, so
 * adding a scalar lesson needs no frontend change.
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

  // The other widget-id-routed answers, on the same authoritative-widget_id contract as expression
  // above (HR.A5): a one-variable inequality (relation + boundary), plotted coordinate point(s) on
  // the four-quadrant plane, and the nested number-set classification. Each is a plain answer string
  // the backend grades (SymPy relational equivalence / point-set equality / set membership — §8.2).
  if (problem.widget_id === 'inequality') return 'inequality';
  if (problem.widget_id === 'coordinate_plane') return 'coordinate_plane';
  if (problem.widget_id === 'classify_sets') return 'classify_sets';

  // A number-line surface with snap intervals → the draggable marker (placement, or an arithmetic
  // result that lands on the line).
  if (problem.surface_format === 'number_line' && problem.tick_segments != null) {
    return 'number_line';
  }

  // A SYMBOLIC scalar answer (a plain integer, decimal, or negative — a percent amount, a GCF/LCM,
  // an integer sum, an exponent, an area/volume, a summary statistic, …) gets the one-box entry, not
  // the two-box fraction editor. The backend marks these with widget_id 'number_entry' per KC (its
  // `_FRACTION_ANSWER_KCS` tie-break), so we route on the authoritative widget_id — no KC list.
  if (problem.widget_id === 'number_entry') return 'number_entry';

  // Everything else (symbolic equivalence/add/sub and the other fraction-answer KCs, incl. the
  // locked-denominator fill-the-top variant signalled by `given_denominator`) is the fraction editor
  // — the backend emits widget_id 'fraction_editor' for them, and it is also the safe default.
  return 'fraction_editor';
}
