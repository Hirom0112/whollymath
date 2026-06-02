import './ExponentProduct.css';

/**
 * A DISPLAY-ONLY exponent repeated-product view for KC_exponents (CCSS 6.EE.1): the power base^exp
 * shown as its expanded repeated multiplication (e.g. 2^4 = 2 x 2 x 2 x 2), so a 6th grader SEES
 * that the base appears exponent-many times — the definition the multiply slip (base x exp) misses.
 *
 * It shows only the QUESTION INPUT — the base, the exponent, and the expanded product form — never
 * the evaluated value. The "= 16" the student must find is graded server-side by SymPy (CLAUDE.md
 * §8.2); it never appears here. The prompt text stays the accessible fallback.
 *
 * Static (no animation) → reduced-motion safe. Vanilla accessible markup (no charting/asset lib).
 * Class names unique app-wide (prefix `wm-exp-`). Takes explicit typed props (snake_case), not a
 * ProblemView — the component is a pure projection of the domain stimulus shape.
 */

export interface ExponentProductProps {
  /** The base — the repeated factor. */
  base: number;
  /** The exponent — how many times the base is multiplied (the factor count). */
  exponent: number;
  /** The base repeated `exponent` times (e.g. [2, 2, 2, 2] for 2^4) — the expanded input form. */
  factors: readonly number[];
}

function describe(props: ExponentProductProps): string {
  const expanded = props.factors.join(' times ');
  return `The power ${String(props.base)} to the ${String(props.exponent)} ` + `means ${expanded}.`;
}

export function ExponentProduct(props: ExponentProductProps): React.JSX.Element {
  return (
    <figure className="wm-exp" role="img" aria-label={describe(props)}>
      <span className="wm-exp-power" aria-hidden="true">
        <span className="wm-exp-base">{props.base}</span>
        <sup className="wm-exp-exponent">{props.exponent}</sup>
      </span>
      <span className="wm-exp-equals" aria-hidden="true">
        =
      </span>
      <span className="wm-exp-product" aria-hidden="true">
        {props.factors.map((f, i) => (
          // The factors are identical values in fixed positions; index is the only stable key.
          <span className="wm-exp-term" key={i} data-factor={f}>
            {i > 0 && <span className="wm-exp-mul">&times;</span>}
            <span className="wm-exp-factor">{f}</span>
          </span>
        ))}
      </span>
    </figure>
  );
}
