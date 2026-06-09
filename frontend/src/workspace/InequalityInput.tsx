import './InequalityInput.css';

import type { WorkspaceWidgetProps } from './WidgetContract';

/**
 * The one-variable inequality input (the Unit 4-5 inequalities KCs: write/represent an inequality
 * like x > 3, x ≤ −2). Sibling to the ExpressionInput typed widget, but STRUCTURED rather than
 * free-text: a 6th grader picks a relation from a button group and types a number, so a malformed
 * inequality (two operators, a missing side) can't be produced at the surface.
 *
 * Controlled component (the HR.A5 {@link WorkspaceWidgetProps} contract): the parent owns the
 * answer `value` as a STRING and the widget renders / edits it. The string is the wire format the
 * backend SymPy verifier grades — `variable` + relation + number, e.g. "x>3", "x<=-2" — using ASCII
 * "<="/">=" (the backend canonicalizes; the kid-facing buttons show the ≤ / ≥ glyphs). The surface
 * neither normalizes nor grades it (CLAUDE.md §8.2): it only composes the well-formed string.
 *
 * The variable is fixed per item (default "x") and shown as a read-only chip, because a 6th-grade
 * inequality item names the variable in the prompt — the learner chooses the RELATION and the
 * boundary, not the letter. The number field allows a leading minus and digits (a negative boundary
 * like −2 is in scope), nothing else, so a stray character can't reach the verifier.
 *
 * Custom markup, no widget lib (TECH_STACK §2). Class names unique app-wide (global CSS).
 *
 * Routed live: ``selectWidget`` returns ``'inequality'`` for ``widget_id="inequality"`` and the
 * emitted inequality string is graded by the SymPy verifier path, like the expression and
 * coordinate-plane widgets.
 */

/** The relations the learner can pick: kid-facing glyph → the ASCII token written to the value. */
const RELATIONS: readonly { readonly label: string; readonly op: string; readonly aria: string }[] =
  [
    { label: '<', op: '<', aria: 'less than' },
    { label: '≤', op: '<=', aria: 'less than or equal to' },
    { label: '>', op: '>', aria: 'greater than' },
    { label: '≥', op: '>=', aria: 'greater than or equal to' },
  ];

// A signed integer/decimal boundary: an optional leading minus, then digits with an optional single
// decimal point. Anything else is stripped so the verifier never sees a typo. Validity beyond this
// (e.g. a lone "-") is the verifier's call — the surface only keeps the characters legal.
function numberSafe(raw: string): string {
  let out = raw.replace(/[^0-9.-]/g, '');
  // Keep a minus only at the very front.
  out = out[0] === '-' ? '-' + out.slice(1).replace(/-/g, '') : out.replace(/-/g, '');
  // Keep only the first decimal point.
  const dot = out.indexOf('.');
  if (dot !== -1) out = out.slice(0, dot + 1) + out.slice(dot + 1).replace(/\./g, '');
  return out;
}

/** The relation operator currently in `value` (so the picked button can read as selected), or null
 * when none is chosen yet. Checks the two-char ops (<=, >=) before the one-char ones so ">=" isn't
 * misread as ">". */
function relationOf(value: string, variable: string): string | null {
  if (!value.startsWith(variable)) return null;
  const rest = value.slice(variable.length);
  if (rest.startsWith('<=')) return '<=';
  if (rest.startsWith('>=')) return '>=';
  if (rest.startsWith('<')) return '<';
  if (rest.startsWith('>')) return '>';
  return null;
}

/** The number side currently in `value`, or "" when none. */
function numberOf(value: string, variable: string): string {
  const op = relationOf(value, variable);
  if (op === null) return '';
  return value.slice(variable.length + op.length);
}

/** Compose the controlled value from its parts. Persists a PARTIAL once a RELATION is picked so the
 * widget can be built up incrementally in a controlled flow: a relation alone round-trips as "x>"
 * (so the picked button stays selected after onChange→rerender), and the boundary fills it to "x>3"
 * — `relationOf`/`numberOf` read either back. Without a relation there is no anchor for the number
 * (the value must start with the variable), so a number-only state collapses to "". Completeness
 * (a relation AND a real number) is the parent's submit gate via {@link isCompleteInequality}; the
 * SymPy verifier still judges correctness (§8.2). */
export function inequalityToAnswer(variable: string, op: string | null, num: string): string {
  if (op === null) return '';
  const boundary = num === '-' ? '' : num;
  return `${variable}${op}${boundary}`;
}

/** Whether a composed value is a COMPLETE inequality (a relation AND a real numeric boundary) — the
 * parent's submit gate, so a relation-only "x>" partial cannot be submitted. */
export function isCompleteInequality(value: string, variable: string): boolean {
  const op = relationOf(value, variable);
  const num = numberOf(value, variable);
  return op !== null && num !== '' && num !== '-';
}

export function InequalityInput({
  value,
  onChange,
  disabled = false,
  prompt,
  variable = 'x',
}: WorkspaceWidgetProps<string> & {
  /** Optional kid-friendly label above the control. */
  prompt?: string;
  /** The inequality's variable (named by the item; default "x"). Shown read-only. */
  variable?: string;
}): React.JSX.Element {
  const op = relationOf(value, variable);
  const num = numberOf(value, variable);

  function pickRelation(nextOp: string): void {
    if (disabled) return;
    onChange(inequalityToAnswer(variable, nextOp, num));
  }

  function setNumber(raw: string): void {
    if (disabled) return;
    onChange(inequalityToAnswer(variable, op, numberSafe(raw)));
  }

  return (
    <div className="wm-ineq" role="group" aria-label="Build an inequality">
      {prompt !== undefined ? <p className="wm-ineq-prompt">{prompt}</p> : null}
      <div className="wm-ineq-row">
        <span className="wm-ineq-var" aria-label={`variable ${variable}`}>
          {variable}
        </span>
        <div className="wm-ineq-ops" role="radiogroup" aria-label="Choose the relation">
          {RELATIONS.map((relation) => (
            <button
              key={relation.op}
              type="button"
              className={`wm-ineq-op ${op === relation.op ? 'wm-ineq-op--selected' : ''}`}
              role="radio"
              aria-checked={op === relation.op}
              aria-label={relation.aria}
              disabled={disabled}
              onClick={() => {
                pickRelation(relation.op);
              }}
            >
              {relation.label}
            </button>
          ))}
        </div>
        <input
          className="wm-ineq-num"
          type="text"
          inputMode="numeric"
          autoComplete="off"
          aria-label="boundary number"
          placeholder="–"
          value={num}
          disabled={disabled}
          onChange={(event) => {
            setNumber(event.target.value);
          }}
        />
      </div>
    </div>
  );
}
