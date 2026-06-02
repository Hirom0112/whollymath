import './FractionArea.css';

/**
 * A DISPLAY-ONLY fraction AREA-MODEL stimulus for the four two-operand fraction-arithmetic KCs
 * (KC_addition_unlike, KC_subtraction_unlike, KC_multiply_fractions, KC_divide_fractions): the two
 * OPERAND fractions a problem names, each drawn as a bar partitioned into its denominator with its
 * numerator shaded, so a 6th grader SEES the two amounts they're combining.
 *
 * Layout follows the operation (chosen by the `op` prop, never computed from a hidden result):
 *   - add / subtract  -> the two bars are STACKED, same width, so the unlike denominators line up
 *     and the difference in part-size is visible (the property the area model exists to expose).
 *   - multiply / divide -> an AREA GRID: the first fraction shades columns (across), the second
 *     shades rows (down). The OVERLAP is intentionally NOT highlighted — that would be the product,
 *     the answer the student must find. We draw only the two operand shadings.
 *
 * It shows only the QUESTION INPUT (the two operands), never the answer — the sum / difference /
 * product / quotient is graded server-side by SymPy (CLAUDE.md §8.2). The prompt text stays the
 * accessible fallback.
 *
 * Deterministic and static (no animation, no `Math.random`) -> reduced-motion safe and reproducible
 * (PROJECT.md §4.1). Custom SVG, no charting/asset lib (TECH_STACK §2). Class names unique app-wide
 * (prefix `wm-fracarea-`; plain global CSS — reused names collide, see the NumberLine incident).
 */

export type FractionAreaOp = 'add' | 'subtract' | 'multiply' | 'divide';

export interface FractionAreaOperand {
  numerator: number;
  denominator: number;
}

export interface FractionAreaProps {
  op: FractionAreaOp;
  first: FractionAreaOperand;
  second: FractionAreaOperand;
}

// SVG geometry (fixed coordinate space; CSS scales it).
const BAR_VB_W = 240;
const BAR_W = 224;
const BAR_H = 40;
const BAR_X = 8;
const BAR_GAP = 18;
const LABEL_H = 22;

const GRID_VB = 220; // square area-model grid for multiply/divide

const OP_SIGN: Record<FractionAreaOp, string> = {
  add: '+',
  subtract: '−',
  multiply: '×',
  divide: '÷',
};

const OP_WORD: Record<FractionAreaOp, string> = {
  add: 'plus',
  subtract: 'minus',
  multiply: 'times',
  divide: 'divided by',
};

function fractionText(f: FractionAreaOperand): string {
  return `${String(f.numerator)}/${String(f.denominator)}`;
}

function describe(props: FractionAreaProps): string {
  return `Area model of ${fractionText(props.first)} ${OP_WORD[props.op]} ${fractionText(
    props.second,
  )}.`;
}

/** One partitioned bar: `denominator` equal cells, the first `numerator` shaded with `shadeClass`. */
function PartitionedBar({
  f,
  y,
  shadeClass,
}: {
  f: FractionAreaOperand;
  y: number;
  shadeClass: string;
}): React.JSX.Element {
  const segments = Math.max(1, f.denominator);
  const cellWidth = BAR_W / segments;
  const cells = Array.from({ length: segments }, (_, k) => k);
  return (
    <g data-testid="wm-fracarea-bar" data-numerator={f.numerator} data-denominator={f.denominator}>
      {cells.map((k) => {
        const filled = k < f.numerator;
        return (
          <rect
            key={k}
            className={`wm-fracarea-cell${filled ? ` ${shadeClass}` : ''}`}
            data-filled={filled}
            x={BAR_X + k * cellWidth}
            y={y}
            width={cellWidth}
            height={BAR_H}
          />
        );
      })}
    </g>
  );
}

/** Add / subtract: the two operand bars stacked so unlike denominators line up vertically. */
function StackedBars(props: FractionAreaProps): React.JSX.Element {
  const vbH = BAR_H * 2 + BAR_GAP + LABEL_H * 2;
  const firstY = LABEL_H;
  const secondY = LABEL_H * 2 + BAR_H + BAR_GAP;
  return (
    <svg
      className="wm-fracarea-svg"
      viewBox={`0 0 ${String(BAR_VB_W)} ${String(vbH)}`}
      role="img"
      aria-label={describe(props)}
    >
      <text className="wm-fracarea-label" x={BAR_X} y={firstY - 6}>
        {fractionText(props.first)}
      </text>
      <PartitionedBar f={props.first} y={firstY} shadeClass="wm-fracarea-cell--a" />
      <text className="wm-fracarea-op" x={BAR_VB_W / 2} y={firstY + BAR_H + BAR_GAP / 2 + 5}>
        {OP_SIGN[props.op]}
      </text>
      <text className="wm-fracarea-label" x={BAR_X} y={secondY - 6}>
        {fractionText(props.second)}
      </text>
      <PartitionedBar f={props.second} y={secondY} shadeClass="wm-fracarea-cell--b" />
    </svg>
  );
}

/**
 * Multiply / divide: an area grid. The first fraction shades columns (across), the second shades
 * rows (down). The OVERLAP cell-set is the product and is deliberately left un-highlighted — only
 * the two operand shadings are drawn (no answer leak, §8.2).
 */
function AreaGrid(props: FractionAreaProps): React.JSX.Element {
  const cols = Math.max(1, props.first.denominator);
  const rows = Math.max(1, props.second.denominator);
  const inset = 8;
  const labelPad = LABEL_H;
  const w = GRID_VB - inset * 2;
  const h = GRID_VB - inset * 2;
  const cellW = w / cols;
  const cellH = h / rows;
  const gridX = inset;
  const gridY = inset + labelPad;
  const vbH = GRID_VB + labelPad;

  const cells: React.JSX.Element[] = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const inCol = c < props.first.numerator; // first fraction: across
      const inRow = r < props.second.numerator; // second fraction: down
      // We draw the two operand shadings as translucent column/row bands. We do NOT paint the
      // overlap a third, distinct colour — that overlap is the product (the answer), kept hidden.
      const cls =
        inCol && inRow
          ? 'wm-fracarea-cell--a wm-fracarea-grid-overlap'
          : inCol
            ? 'wm-fracarea-cell--a'
            : inRow
              ? 'wm-fracarea-cell--b'
              : '';
      cells.push(
        <rect
          key={`${String(r)}-${String(c)}`}
          className={`wm-fracarea-cell${cls ? ` ${cls}` : ''}`}
          data-row={r}
          data-col={c}
          data-in-col={inCol}
          data-in-row={inRow}
          x={gridX + c * cellW}
          y={gridY + r * cellH}
          width={cellW}
          height={cellH}
        />,
      );
    }
  }
  return (
    <svg
      className="wm-fracarea-svg"
      viewBox={`0 0 ${String(GRID_VB)} ${String(vbH)}`}
      role="img"
      aria-label={describe(props)}
    >
      <text className="wm-fracarea-label" x={inset} y={labelPad - 8}>
        {fractionText(props.first)} {OP_SIGN[props.op]} {fractionText(props.second)}
      </text>
      {cells}
    </svg>
  );
}

export function FractionArea(props: FractionAreaProps): React.JSX.Element {
  const stacked = props.op === 'add' || props.op === 'subtract';
  return (
    <figure className="wm-fracarea" data-op={props.op}>
      {stacked ? <StackedBars {...props} /> : <AreaGrid {...props} />}
      <figcaption className="wm-fracarea-caption">
        {fractionText(props.first)} {OP_SIGN[props.op]} {fractionText(props.second)}
      </figcaption>
    </figure>
  );
}
