import './GcfFactors.css';

/**
 * A DISPLAY-ONLY GCF/LCM factor view for KC_gcf_lcm (CCSS 6.NS.4 / TEKS 6.7A): the two given whole
 * numbers, each with its full factor list, laid out as two labelled rows so a 6th grader SEES the
 * shared factors (for a GCF) or can line up the common multiples (for an LCM).
 *
 * The factors shown are the divisors of the GIVEN numbers — that is QUESTION INPUT, the natural way
 * to make the relationship concrete. It shows only the input, never the answer: it does NOT mark
 * which factor is the greatest-common one, nor which multiple is least-common. The correct GCF/LCM
 * is graded server-side by SymPy (CLAUDE.md §8.2). The prompt text stays the accessible fallback.
 *
 * Static (no animation) → reduced-motion safe. Vanilla accessible markup (no charting/asset lib).
 * Class names unique app-wide (prefix `wm-gcf-`). Takes explicit typed props (snake_case), not a
 * ProblemView — the component is a pure projection of the domain stimulus shape.
 */

export interface GcfFactorsProps {
  /** "gcf" or "lcm" — frames the view (shared factors vs common multiples); not the answer. */
  mode: 'gcf' | 'lcm';
  /** The first given whole number the prompt names. */
  first: number;
  /** The second given whole number the prompt names. */
  second: number;
  /** Ascending factor (divisor) list of `first`. */
  first_factors: readonly number[];
  /** Ascending factor (divisor) list of `second`. */
  second_factors: readonly number[];
}

function describe(props: GcfFactorsProps): string {
  const relationship = props.mode === 'gcf' ? 'greatest common factor' : 'least common multiple';
  return (
    `Factor view for the ${relationship} of ${String(props.first)} and ${String(props.second)}. ` +
    `Factors of ${String(props.first)}: ${props.first_factors.join(', ')}. ` +
    `Factors of ${String(props.second)}: ${props.second_factors.join(', ')}.`
  );
}

function FactorRow({
  value,
  factors,
}: {
  value: number;
  factors: readonly number[];
}): React.JSX.Element {
  return (
    <div className="wm-gcf-row" data-number={value}>
      <span className="wm-gcf-number">{value}</span>
      <span className="wm-gcf-colon" aria-hidden="true">
        :
      </span>
      <ol className="wm-gcf-factors">
        {factors.map((f) => (
          <li className="wm-gcf-factor" key={f} data-factor={f}>
            {f}
          </li>
        ))}
      </ol>
    </div>
  );
}

export function GcfFactors(props: GcfFactorsProps): React.JSX.Element {
  const heading = props.mode === 'gcf' ? 'Shared factors' : 'Common multiples';
  return (
    <figure className="wm-gcf" role="img" aria-label={describe(props)} data-mode={props.mode}>
      <figcaption className="wm-gcf-heading">{heading}</figcaption>
      <FactorRow value={props.first} factors={props.first_factors} />
      <FactorRow value={props.second} factors={props.second_factors} />
    </figure>
  );
}
