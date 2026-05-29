import './NumberEntry.css';

/**
 * A single whole-number entry control (Slice CP.A.2 — the common-denominator answer).
 *
 * Common denominator's answer is a single whole number (a shared piece-size, e.g. 12), NOT a
 * fraction — so it must NOT land on the two-box fraction editor (the construct-irrelevant
 * difficulty the §3.4.1 learning-science panel flagged). This is the right-shaped input: one
 * digits-only field, with an optional unit word after it ("equal pieces") so the answer reads
 * as a count, not a fraction.
 *
 * Controlled component: the parent owns the string value and composes the answer the SymPy
 * verifier checks (correctness is never decided here — §8.2). Input is constrained to digits so
 * a stray character can never reach the verifier as a typo. Custom markup, no widget lib
 * (TECH_STACK §2); visual testing is sufficient (CLAUDE.md §9).
 */

// Keep only digits — a common denominator is a positive whole number; the verifier wants a
// clean integer, and the surface should never let a letter/symbol through as a typo.
function digitsOnly(raw: string): string {
  return raw.replace(/[^0-9]/g, '');
}

export function NumberEntry({
  value,
  onChange,
  disabled = false,
  prompt,
  unit,
}: {
  value: string;
  onChange: (next: string) => void;
  disabled?: boolean;
  /** Optional kid-friendly label above the control. */
  prompt?: string;
  /** Optional unit word shown after the field (e.g. "equal pieces"), so it reads as a count. */
  unit?: string;
}): React.JSX.Element {
  return (
    <div className="wm-numentry" role="group" aria-label="Enter a whole number">
      {prompt !== undefined ? <p className="wm-numentry-prompt">{prompt}</p> : null}
      <div className="wm-numentry-row">
        <input
          className="wm-numentry-field"
          type="text"
          inputMode="numeric"
          autoComplete="off"
          aria-label="your number"
          placeholder="–"
          value={value}
          disabled={disabled}
          onChange={(event) => {
            onChange(digitsOnly(event.target.value));
          }}
        />
        {unit !== undefined ? <span className="wm-numentry-unit">{unit}</span> : null}
      </div>
    </div>
  );
}
