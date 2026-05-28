import './SymbolicEditor.css';

/**
 * The S1 symbolic workspace (Slice 2.5): a stacked numerator / fraction-bar /
 * denominator entry control. This is the direct-manipulation surface for the
 * default fluent state (S1, ARCHITECTURE.md §7) — the learner enters a fraction
 * answer in its real two-part form rather than typing a free-text "a/b".
 *
 * Controlled component: the parent owns `numerator` / `denominator` as strings and
 * composes the "n/d" answer the domain SymPy verifier parses (it never decides
 * correctness here — §8.2). Input is constrained to digits so a stray character can
 * never reach the verifier as a typo; emptiness/validity is the parent's call.
 *
 * Custom SVG/markup per TECH_STACK §2 (own the three manipulatives; no third-party
 * math-widget lib). Visual testing is sufficient for components (CLAUDE.md §9); the
 * digit-filtering behavior is unit-tested.
 */

export interface FractionValue {
  numerator: string;
  denominator: string;
}

// Keep only digits — the verifier wants clean integers; a learner can never submit a
// letter or symbol that would be read as a typo (verifier returns "wrong", but we
// prevent the confusing path at the surface).
function digitsOnly(raw: string): string {
  return raw.replace(/[^0-9]/g, '');
}

export function SymbolicEditor({
  value,
  onChange,
  disabled = false,
  prompt,
  lockDenominator = false,
}: {
  value: FractionValue;
  onChange: (next: FractionValue) => void;
  disabled?: boolean;
  /** Optional kid-friendly label above the control (e.g. the problem statement). */
  prompt?: string;
  /**
   * When true the denominator is GIVEN by the question (an equivalence "fill the top"
   * item, "3/4 is the same as ?/8"): the bottom field shows the value and is not
   * editable, so the learner enters only the numerator the statement asks for. The
   * parent seeds `value.denominator` with the given number.
   */
  lockDenominator?: boolean;
}): React.JSX.Element {
  return (
    <div className="wm-symbolic" role="group" aria-label="Enter your fraction answer">
      {prompt !== undefined ? <p className="wm-symbolic-prompt">{prompt}</p> : null}
      <div className="wm-symbolic-stack">
        <input
          className="wm-symbolic-field"
          type="text"
          inputMode="numeric"
          autoComplete="off"
          aria-label="numerator"
          placeholder="–"
          value={value.numerator}
          disabled={disabled}
          onChange={(event) => {
            onChange({ ...value, numerator: digitsOnly(event.target.value) });
          }}
        />
        <span className="wm-symbolic-bar" aria-hidden="true" />
        <input
          className={`wm-symbolic-field ${lockDenominator ? 'wm-symbolic-field--given' : ''}`}
          type="text"
          inputMode="numeric"
          autoComplete="off"
          aria-label="denominator"
          placeholder="–"
          value={value.denominator}
          disabled={disabled}
          readOnly={lockDenominator}
          aria-readonly={lockDenominator}
          onChange={(event) => {
            if (lockDenominator) return;
            onChange({ ...value, denominator: digitsOnly(event.target.value) });
          }}
        />
      </div>
    </div>
  );
}

/** The "n/d" answer string for the verifier, or "" when either part is empty. */
export function fractionToAnswer(value: FractionValue): string {
  if (value.numerator === '' || value.denominator === '') return '';
  return `${value.numerator}/${value.denominator}`;
}
