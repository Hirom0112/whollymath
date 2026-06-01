import './NumberEntry.css';

/**
 * A single SCALAR-value entry control (the number_entry widget — the non-fraction symbolic answer).
 *
 * The SYMBOLIC scalar KCs answer with ONE value that is not a numerator-over-denominator fraction:
 * a whole number (a common-denominator piece-size 12; a GCF; an area), a NEGATIVE (an integer sum
 * −1; the opposite of a number), a DECIMAL (a 0.04 product), or — for the mixed stats KCs — an
 * exact fraction a/b (a mean 11/3, "what fraction surveyed" 8/19). None of these belong on the
 * two-box fraction editor (the construct-irrelevant difficulty the §3.4.1 learning-science panel
 * flagged), so they get this single field. The optional unit word after it ("equal pieces") lets a
 * count read as a count.
 *
 * Controlled component: the parent owns the string value and composes the answer the SymPy verifier
 * checks (correctness is never decided here — §8.2). Input is constrained to the scalar-numeric
 * character set the verifier parses (digits, a leading '-', one '.', a single '/'), so a learner can
 * enter a negative / decimal / exact fraction but a letter or stray symbol can never reach the
 * verifier as a typo. Custom markup, no widget lib (TECH_STACK §2); visual testing is sufficient
 * (CLAUDE.md §9).
 */

// Constrain to the scalar-numeric shapes the domain verifier accepts (verifier._parse_to_rational):
// a bare integer, a negative, a decimal literal, or an exact "a/b" — so a single box covers every
// scalar KC (the integer/decimal/negative producers AND the mixed-fraction stats KCs) without ever
// letting a letter or other symbol through. We strip disallowed characters, keep only the FIRST '-'
// and only when leading, the FIRST '.', and the FIRST '/', so the field can never compose a token
// the verifier would silently reject as a typo.
function scalarOnly(raw: string): string {
  let seenDot = false;
  let seenSlash = false;
  let out = '';
  for (const ch of raw) {
    if (ch >= '0' && ch <= '9') {
      out += ch;
    } else if (ch === '-' && out === '') {
      out += ch; // a single leading minus only
    } else if (ch === '.' && !seenDot && !seenSlash) {
      seenDot = true;
      out += ch;
    } else if (ch === '/' && !seenSlash && !seenDot && out.replace('-', '') !== '') {
      seenSlash = true;
      out += ch; // a single '/' for an exact fraction, after a numerator, before any decimal point
    }
  }
  return out;
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
    <div className="wm-numentry" role="group" aria-label="Enter a number">
      {prompt !== undefined ? <p className="wm-numentry-prompt">{prompt}</p> : null}
      <div className="wm-numentry-row">
        <input
          className="wm-numentry-field"
          type="text"
          // 'text' (not 'decimal'/'numeric') so the negative sign and the fraction slash are typable
          // on a mobile keypad; scalarOnly() enforces the allowed character set on every change.
          inputMode="text"
          autoComplete="off"
          aria-label="your number"
          placeholder="–"
          value={value}
          disabled={disabled}
          onChange={(event) => {
            onChange(scalarOnly(event.target.value));
          }}
        />
        {unit !== undefined ? <span className="wm-numentry-unit">{unit}</span> : null}
      </div>
    </div>
  );
}
