import './DecimalPlaceValue.css';

/**
 * A DISPLAY-ONLY place-value chart for KC_decimal_operations (CCSS 6.NS.B.3): the operand decimals
 * dropped into aligned, labelled place columns (ones · tenths · hundredths …) with the decimal
 * points lined up. It's the representation that makes decimal placement obvious — a 6th grader SEES
 * which digit sits in which place before they multiply, which is exactly the move the misconception
 * (misplacing the point by a power of ten) gets wrong.
 *
 * It shows only the QUESTION INPUT — the two FACTOR rows — never the product (CLAUDE.md §8.2). The
 * answer (where the product's point lands) lives only in the server-side SymPy verifier; nothing in
 * this chart computes or hints it. Grading is unchanged.
 *
 * Rendered as a real, accessible HTML <table>: a <caption> reads the whole chart, the place labels
 * are a <thead> row of <th scope="col">, each operand row leads with a <th scope="row"> naming the
 * decimal, and the aligned decimal point is a thin marker column. No charting lib, no LLM in the
 * turn loop (§8.1). Pure function of its props → reproducible (PROJECT.md §4.1).
 *
 * Takes EXPLICIT typed props (snake_case) mirroring the backend `DecimalPlaceValueStimulus`
 * dataclass — it is not coupled to ProblemView, so it composes anywhere. Class names unique app-wide
 * (prefix `wm-placeval-`). Cream/navy/serif aesthetic via design tokens.
 */

export interface DecimalPlaceValueRowProps {
  /** The operand exactly as the chart labels it, e.g. "0.50" (grid form, trailing zeros kept). */
  decimal_text: string;
  /** One digit ("0".."9") per column, parallel to `columns`; padded with "0" outside the operand. */
  digits: readonly string[];
}

export interface DecimalPlaceValueProps {
  kind: 'decimal_place_value';
  /** Place labels left-to-right, highest magnitude first, e.g. ["ones","tenths","hundredths"]. */
  columns: readonly string[];
  /** 0-based index of the last integer column ("ones"); the decimal point is drawn after it. */
  point_after: number;
  /** One row per operand, in the order the prompt names them. */
  rows: readonly DecimalPlaceValueRowProps[];
}

/** Build the accessible caption that reads the whole chart as a sentence. */
function describe(props: DecimalPlaceValueProps): string {
  const places = props.columns.join(', ');
  const rows = props.rows.map((r) => r.decimal_text).join(' and ');
  return `Place-value chart. Columns: ${places}. Decimals lined up on the decimal point: ${rows}.`;
}

/** A row of digit cells with a thin decimal-point marker cell after the ones column. */
function DigitCells({
  digits,
  point_after,
  rowKey,
}: {
  digits: readonly string[];
  point_after: number;
  rowKey: string;
}): React.JSX.Element {
  const cells: React.JSX.Element[] = [];
  digits.forEach((digit, i) => {
    cells.push(
      <td key={`${rowKey}-d-${String(i)}`} className="wm-placeval-cell">
        {digit}
      </td>,
    );
    if (i === point_after) {
      // The aligned decimal point sits between the ones column and the tenths column.
      cells.push(
        <td
          key={`${rowKey}-pt`}
          className="wm-placeval-point"
          aria-hidden="true"
          data-testid="wm-placeval-point"
        >
          .
        </td>,
      );
    }
  });
  return <>{cells}</>;
}

export function DecimalPlaceValue(props: DecimalPlaceValueProps): React.JSX.Element {
  const { columns, point_after, rows } = props;
  return (
    <figure className="wm-placeval">
      <table className="wm-placeval-table" data-testid="wm-placeval">
        <caption className="wm-placeval-caption">{describe(props)}</caption>
        <thead>
          <tr className="wm-placeval-head">
            {/* Empty corner above the row-label column. */}
            <th scope="col" className="wm-placeval-corner" aria-hidden="true" />
            {columns.flatMap((col, i) => {
              const head = (
                <th key={`h-${col}`} scope="col" className="wm-placeval-place">
                  {col}
                </th>
              );
              if (i !== point_after) return [head];
              return [
                head,
                <th
                  key={`h-${col}-pt`}
                  scope="col"
                  className="wm-placeval-place-point"
                  aria-hidden="true"
                />,
              ];
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, r) => (
            <tr key={`row-${String(r)}`} className="wm-placeval-row">
              <th scope="row" className="wm-placeval-rowhead">
                {row.decimal_text}
              </th>
              <DigitCells
                digits={row.digits}
                point_after={point_after}
                rowKey={`row-${String(r)}`}
              />
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
