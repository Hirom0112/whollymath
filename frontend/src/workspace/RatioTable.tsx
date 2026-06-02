import './RatioTable.css';

/**
 * A DISPLAY-ONLY ratio table for KC_unit_rate (CCSS 6.RP.A.3a) and KC_equivalent_ratios
 * (CCSS 6.RP.A.2): two labelled rows whose columns are the SAME ratio, scaled. It draws the GIVEN
 * ratio next to the column the question asks about, with the scale step (e.g. ×3 / ÷4) as an arrow
 * between them — the canonical ratio-reasoning scaffold a 6th grader reads off the table.
 *
 * It shows only the QUESTION INPUT and the scaffold STRUCTURE, never the answer: the asked cell is
 * rendered BLANK (a "?" placeholder), and the value the student must find never appears as a number
 * (CLAUDE.md §8.2). The scale label is the multiplicative step, NOT the answer (for equivalent
 * ratios the answer is a*k, not k). Grading stays server-side in SymPy; this changes nothing there.
 *
 * Rendered as a real, accessible HTML <table>: a <caption> reads the whole table, each row leads
 * with a <th scope="row">, and the blank cell carries aria-label="unknown value". No charting lib,
 * no LLM in the turn loop (§8.1). Pure function of its props → reproducible (PROJECT.md §4.1).
 *
 * Takes EXPLICIT typed props (snake_case) mirroring the backend `RatioTableStimulus` dataclass — it
 * is not coupled to ProblemView, so it composes anywhere. Class names unique app-wide
 * (prefix `wm-ratiotbl-`). Cream/navy/serif aesthetic via design tokens.
 */

export interface RatioTableColumnProps {
  /** Top-row value for this column, or null for the blank (asked) cell. */
  top: number | null;
  /** Bottom-row value for this column, or null for the blank (asked) cell. */
  bottom: number | null;
}

export interface RatioTableProps {
  /** Heading for the top row (e.g. "Amount" or "Top"). */
  top_label: string;
  /** Heading for the bottom row (e.g. "Units" or "Bottom"). */
  bottom_label: string;
  /** Columns left-to-right; exactly one cell across the table is null (the asked cell). */
  columns: readonly RatioTableColumnProps[];
  /** The multiplicative step between the two columns, e.g. "×3" or "÷4" — scaffold, not the answer. */
  scale_label: string;
}

/** One value cell <td>: a number, or a "?" placeholder for the blank cell the student must find. */
function ValueCell({ value, idx }: { value: number | null; idx: number }): React.JSX.Element {
  if (value == null) {
    return (
      <td
        key={`c-${String(idx)}`}
        className="wm-ratiotbl-cell wm-ratiotbl-cell-blank"
        aria-label="unknown value"
      >
        <span className="wm-ratiotbl-q" aria-hidden="true">
          ?
        </span>
      </td>
    );
  }
  return (
    <td key={`c-${String(idx)}`} className="wm-ratiotbl-cell">
      {value}
    </td>
  );
}

/** Build the accessible caption that reads the table as a sentence. */
function describe(props: RatioTableProps): string {
  const cols = props.columns
    .map((c) => {
      const top = c.top == null ? 'unknown' : String(c.top);
      const bottom = c.bottom == null ? 'unknown' : String(c.bottom);
      return `${top} to ${bottom}`;
    })
    .join(', then ');
  return `Ratio table. ${props.top_label} over ${props.bottom_label}. Columns: ${cols}. Scale step ${props.scale_label}.`;
}

export function RatioTable(props: RatioTableProps): React.JSX.Element {
  const { top_label, bottom_label, columns, scale_label } = props;
  // The scale arrow sits between column 0 and column 1, so it spans the gap once (two-column table).
  const hasArrow = columns.length >= 2;
  return (
    <figure className="wm-ratiotbl">
      <table className="wm-ratiotbl-table" data-testid="wm-ratiotbl">
        <caption className="wm-ratiotbl-caption">{describe(props)}</caption>
        <tbody>
          <tr className="wm-ratiotbl-row wm-ratiotbl-row-top">
            <th scope="row" className="wm-ratiotbl-rowhead">
              {top_label}
            </th>
            {columns.map((c, i) => (
              <ValueCell key={`top-${String(i)}`} value={c.top} idx={i} />
            ))}
          </tr>
          <tr className="wm-ratiotbl-row">
            <th scope="row" className="wm-ratiotbl-rowhead">
              {bottom_label}
            </th>
            {columns.map((c, i) => (
              <ValueCell key={`bottom-${String(i)}`} value={c.bottom} idx={i} />
            ))}
          </tr>
        </tbody>
      </table>
      {hasArrow && (
        <div className="wm-ratiotbl-scale" data-testid="wm-ratiotbl-scale" aria-hidden="true">
          <span className="wm-ratiotbl-scale-label">{scale_label}</span>
        </div>
      )}
    </figure>
  );
}
