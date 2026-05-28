import './YesNo.css';

/**
 * The yes/no answer control for relational-judgment problems ("Is 2/3 the same
 * amount as 4/6?"). These questions ask the learner to DECIDE, not to type a
 * fraction, so they get two buttons rather than the SymbolicEditor.
 *
 * Controlled component: the parent owns the selection (true = yes, false = no,
 * null = nothing picked yet) and composes the "yes"/"no" answer string the domain
 * SymPy verifier judges (the verifier computes the truth from the operands — the
 * surface never decides correctness, §8.2).
 *
 * Custom markup per TECH_STACK §2. Visual testing is sufficient for components
 * (CLAUDE.md §9).
 */
export function YesNo({
  value,
  onChange,
  disabled = false,
  prompt,
}: {
  value: boolean | null;
  onChange: (next: boolean) => void;
  disabled?: boolean;
  /** Optional kid-friendly label above the control. */
  prompt?: string;
}): React.JSX.Element {
  return (
    <div className="wm-yesno" role="radiogroup" aria-label="Choose yes or no">
      {prompt !== undefined ? <p className="wm-yesno-prompt">{prompt}</p> : null}
      <div className="wm-yesno-options">
        <button
          type="button"
          className={`wm-yesno-option ${value === true ? 'wm-yesno-option--selected' : ''}`}
          role="radio"
          aria-checked={value === true}
          disabled={disabled}
          onClick={() => {
            onChange(true);
          }}
        >
          Yes
        </button>
        <button
          type="button"
          className={`wm-yesno-option ${value === false ? 'wm-yesno-option--selected' : ''}`}
          role="radio"
          aria-checked={value === false}
          disabled={disabled}
          onClick={() => {
            onChange(false);
          }}
        >
          No
        </button>
      </div>
    </div>
  );
}

/** The "yes"/"no" answer string for the verifier, or "" when nothing is picked. */
export function yesNoToAnswer(value: boolean | null): string {
  if (value === null) return '';
  return value ? 'yes' : 'no';
}
