import { useRef } from 'react';

import './ExpressionInput.css';

import type { WorkspaceWidgetProps } from './WidgetContract';

/**
 * The algebra expression / equation input (the Unit 4–5 KCs: write / evaluate / equivalent
 * expressions). Unlike the fraction editor or the number entry, the answer here is a typed
 * algebraic STRING — `n + 5`, `2*x - 3`, `x/4` — not a single magnitude, so it needs a free-text
 * field rather than a two-box or one-box numeric control.
 *
 * Controlled component (the HR.A5 {@link WorkspaceWidgetProps} contract): the parent owns the
 * string `value` and submits it through `/turn`, where the domain SymPy verifier grades it by
 * algebraic equivalence (`n+5` ≡ `5+n` ≡ `n + 5`). Correctness is NEVER decided here (CLAUDE.md
 * §8.2) — the surface only collects the expression and keeps it SymPy-parseable.
 *
 * The value is the wire contract T1 froze: `answer_kind = "expression"`, `widget_id = "expression"`,
 * a SymPy-parseable string. Both literals are a Wave-5 backend dependency — the expression KC will
 * add "expression" to `AnswerKind` (today "numeric"|"yes_no") and emit `widget_id = "expression"`;
 * this widget is built AHEAD of that and unit-tested in isolation against mock props.
 *
 * Input is sanitized to a SymPy-friendly character set (letters for variables, digits, the four
 * operators, parentheses, a caret for powers, decimal points, spaces) so a stray character can't
 * reach the verifier as a typo — but unlike the numeric widgets it deliberately ALLOWS letters,
 * since a variable is the whole point. Validity beyond that (a balanced, parseable expression) is
 * SymPy's call on the backend, not the surface's.
 *
 * Custom markup, no third-party math-input lib (TECH_STACK §2). The kid-facing palette inserts the
 * familiar ×/÷ glyphs but writes the SymPy operators `*`/`/` into the value, so what the learner
 * sees reads like math class while what ships parses. Class names unique app-wide (global CSS).
 */

// Keep only characters that can appear in a SymPy-parseable elementary-algebra expression: variable
// letters, digits, the four operators, grouping, a power caret, decimal points, and spaces. This
// blocks accidental punctuation/symbols at the surface; it does NOT judge whether the expression is
// well-formed — that is the verifier's job (§8.2).
const SYMPY_SAFE = /[^a-zA-Z0-9+\-*/().^ ]/g;

function expressionSafe(raw: string): string {
  return raw.replace(SYMPY_SAFE, '');
}

/** The operator palette: kid-facing glyph → the SymPy token it inserts into the value. */
const PALETTE: readonly { readonly label: string; readonly insert: string; readonly aria: string }[] =
  [
    { label: '×', insert: '*', aria: 'multiply' },
    { label: '÷', insert: '/', aria: 'divide' },
    { label: '( )', insert: '()', aria: 'parentheses' },
  ];

export function ExpressionInput({
  value,
  onChange,
  disabled = false,
  prompt,
}: WorkspaceWidgetProps<string> & {
  /** Optional kid-friendly label above the field (e.g. "Write the expression"). */
  prompt?: string;
}): React.JSX.Element {
  // Keep a handle on the field so a palette tap inserts at the caret and returns focus, rather than
  // always appending — so a learner can fix the middle of an expression without retyping it.
  const fieldRef = useRef<HTMLInputElement>(null);

  function insertToken(token: string): void {
    if (disabled) return;
    const field = fieldRef.current;
    // Fall back to an append when we somehow have no caret (e.g. the field is not yet focused).
    const start = field?.selectionStart ?? value.length;
    const end = field?.selectionEnd ?? value.length;
    const next = expressionSafe(value.slice(0, start) + token + value.slice(end));
    onChange(next);
    // Restore focus and drop the caret just after the inserted token (between the parens for "()").
    if (field !== null) {
      const caret = start + (token === '()' ? 1 : token.length);
      requestAnimationFrame(() => {
        field.focus();
        field.setSelectionRange(caret, caret);
      });
    }
  }

  return (
    <div className="wm-expr" role="group" aria-label="Enter a math expression">
      {prompt !== undefined ? <p className="wm-expr-prompt">{prompt}</p> : null}
      <input
        ref={fieldRef}
        className="wm-expr-field"
        type="text"
        inputMode="text"
        autoComplete="off"
        autoCapitalize="off"
        autoCorrect="off"
        spellCheck={false}
        aria-label="your expression"
        placeholder="e.g. n + 5"
        value={value}
        disabled={disabled}
        onChange={(event) => {
          onChange(expressionSafe(event.target.value));
        }}
      />
      <div className="wm-expr-palette" role="group" aria-label="Insert a math symbol">
        {PALETTE.map((key) => (
          <button
            key={key.insert}
            type="button"
            className="wm-expr-key"
            aria-label={key.aria}
            disabled={disabled}
            // A palette tap must not submit the surrounding form; it only edits the value.
            onClick={() => {
              insertToken(key.insert);
            }}
          >
            {key.label}
          </button>
        ))}
      </div>
    </div>
  );
}
