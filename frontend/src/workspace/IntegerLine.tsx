import './IntegerLine.css';

/**
 * A DISPLAY-ONLY integer number line for the integer-arithmetic family (TEKS 6.3C/D,
 * CCSS 6.NS.5–7): KC_integer_add_subtract, KC_absolute_value, KC_signed_numbers. It draws the
 * horizontal line, the 0 mark, the integer ticks, and the INPUTS the prompt names as positions and
 * moves on the line — so a 6th grader SEES signed numbers as places and jumps.
 *
 * Three scenes, one per KC, chosen by the discriminated `kind`:
 *  - `integer_jump` (add/subtract): mark the START integer and draw an ARROW of length/direction
 *    `delta` (the second operand). The arrow ends where the sum lands — but that landing number is
 *    NOT labelled (the motion is shown, not the stated answer). §8.2.
 *  - `absolute_value`: mark the POINT and draw the span from it to 0 (its distance). The distance
 *    VALUE (the answer) is not labelled.
 *  - `signed_point`: mark the given integer(s). The opposite (the answer) is not marked.
 *
 * Custom SVG, no charting/asset lib. It shows only the QUESTION INPUT, never the answer — the
 * correct value is graded server-side by SymPy (CLAUDE.md §8.2). Static (no animation) →
 * reduced-motion safe. Class names unique app-wide (prefix `wm-intline-`). The whole figure is one
 * labeled region (role="img") whose aria-label reads the marks.
 */

// ── Discriminated props: one variant per KC, all coordinates as snake_case integers. ──

export interface IntegerJumpProps {
  kind: 'integer_jump';
  axis_min: number;
  axis_max: number;
  /** Where the jump starts (the first operand). */
  start: number;
  /** Signed length of the jump (the second operand); the landing `start + delta` is NOT labelled. */
  delta: number;
}

export interface AbsoluteValueProps {
  kind: 'absolute_value';
  axis_min: number;
  axis_max: number;
  /** The point whose distance to 0 the question asks for. */
  point: number;
}

export interface SignedPointProps {
  kind: 'signed_point';
  axis_min: number;
  axis_max: number;
  /** The given integer(s) marked on the line. */
  points: number[];
}

export type IntegerLineProps = IntegerJumpProps | AbsoluteValueProps | SignedPointProps;

// ── SVG geometry (a fixed coordinate space; CSS scales it). ──
const VIEW_W = 560;
const VIEW_H = 150;
const AXIS_Y = 92;
const PAD = 36;
const TRACK_START = PAD;
const TRACK_END = VIEW_W - PAD;
const TRACK_LEN = TRACK_END - TRACK_START;
const ARROW_Y = AXIS_Y - 34; // the add/subtract jump arrow rides above the line
const SPAN_Y = AXIS_Y - 22; // the absolute-value distance bracket rides above the line

/** Map an integer position on [axis_min, axis_max] to its x in the viewBox. */
function xFor(value: number, axisMin: number, axisMax: number): number {
  const span = axisMax - axisMin;
  if (span <= 0) return TRACK_START;
  return TRACK_START + ((value - axisMin) / span) * TRACK_LEN;
}

/** The integer tick positions across the axis, inclusive of both ends. */
function integerTicks(axisMin: number, axisMax: number): number[] {
  const out: number[] = [];
  for (let v = axisMin; v <= axisMax; v++) out.push(v);
  return out;
}

function describe(props: IntegerLineProps): string {
  const range = `Number line from ${String(props.axis_min)} to ${String(props.axis_max)}, zero marked.`;
  switch (props.kind) {
    case 'integer_jump': {
      const dir = props.delta < 0 ? 'left' : 'right';
      const steps = Math.abs(props.delta);
      return `${range} A point at ${String(props.start)} with an arrow jumping ${String(steps)} ${dir}.`;
    }
    case 'absolute_value':
      return `${range} A point at ${String(props.point)} and its distance to zero.`;
    case 'signed_point':
      return `${range} ${props.points.map((p) => `A point at ${String(p)}`).join(', ')}.`;
  }
}

/** A small filled marker dot sitting on the line at `value`. */
function PointMark({
  value,
  axisMin,
  axisMax,
  label,
}: {
  value: number;
  axisMin: number;
  axisMax: number;
  label: number;
}): React.JSX.Element {
  const x = xFor(value, axisMin, axisMax);
  return (
    <g className="wm-intline-point" data-point={value}>
      <circle className="wm-intline-dot" cx={x} cy={AXIS_Y} r={7} />
      <text className="wm-intline-point-label" x={x} y={AXIS_Y - 14} textAnchor="middle">
        {label}
      </text>
    </g>
  );
}

export function IntegerLine(props: IntegerLineProps): React.JSX.Element {
  const { axis_min: axisMin, axis_max: axisMax } = props;
  const ticks = integerTicks(axisMin, axisMax);
  const zeroX = xFor(0, axisMin, axisMax);

  return (
    <figure className="wm-intline">
      <svg
        className="wm-intline-svg"
        viewBox={`0 0 ${String(VIEW_W)} ${String(VIEW_H)}`}
        role="img"
        aria-label={describe(props)}
      >
        <defs>
          {/* Arrowhead for the add/subtract jump; orients with the path so it points the way of travel. */}
          <marker
            id="wm-intline-arrowhead"
            markerWidth="10"
            markerHeight="10"
            refX="7"
            refY="4"
            orient="auto-start-reverse"
            markerUnits="userSpaceOnUse"
          >
            <path className="wm-intline-arrow-tip" d="M0 0 L8 4 L0 8 Z" />
          </marker>
        </defs>

        {/* The axis line. */}
        <line
          className="wm-intline-track"
          x1={TRACK_START}
          y1={AXIS_Y}
          x2={TRACK_END}
          y2={AXIS_Y}
        />

        {/* Integer ticks + labels; the 0 tick is drawn heavier and always labelled. */}
        {ticks.map((v) => {
          const x = xFor(v, axisMin, axisMax);
          const isZero = v === 0;
          const half = isZero ? 16 : 10;
          return (
            <g key={v} data-tick={v}>
              <line
                className={isZero ? 'wm-intline-tick wm-intline-tick-zero' : 'wm-intline-tick'}
                x1={x}
                y1={AXIS_Y - half}
                x2={x}
                y2={AXIS_Y + half}
              />
              <text
                className={isZero ? 'wm-intline-label wm-intline-label-zero' : 'wm-intline-label'}
                x={x}
                y={AXIS_Y + 32}
                textAnchor="middle"
              >
                {v}
              </text>
            </g>
          );
        })}

        {props.kind === 'integer_jump' ? (
          <JumpArrow {...props} />
        ) : props.kind === 'absolute_value' ? (
          <DistanceSpan {...props} zeroX={zeroX} />
        ) : (
          props.points.map((p) => (
            <PointMark key={p} value={p} axisMin={axisMin} axisMax={axisMax} label={p} />
          ))
        )}
      </svg>
    </figure>
  );
}

/** The add/subtract jump: a start dot, then an arrow above the line of signed length `delta`. The
 * arrow's end sits over `start + delta` but is deliberately NOT labelled (the sum is the answer). */
function JumpArrow(props: IntegerJumpProps): React.JSX.Element {
  const { axis_min: axisMin, axis_max: axisMax, start, delta } = props;
  const startX = xFor(start, axisMin, axisMax);
  const endX = xFor(start + delta, axisMin, axisMax);
  return (
    <g className="wm-intline-jump" data-start={start} data-delta={delta}>
      <PointMark value={start} axisMin={axisMin} axisMax={axisMax} label={start} />
      {/* The jump arrow. Drawn even for delta === 0 (degenerate) as a zero-length nub; in practice
          the generator always gives a nonzero second operand. */}
      <line
        className="wm-intline-arrow"
        x1={startX}
        y1={ARROW_Y}
        x2={endX}
        y2={ARROW_Y}
        markerEnd="url(#wm-intline-arrowhead)"
      />
      {/* Small drop lines connecting the arrow to the line at its start (the end is intentionally
          left unconnected so the landing point is not visually called out). */}
      <line className="wm-intline-tie" x1={startX} y1={ARROW_Y} x2={startX} y2={AXIS_Y} />
    </g>
  );
}

/** The absolute-value scene: mark the point and draw the span from it to 0 (the distance). The
 * span's LENGTH (the answer) is not labelled — the picture shows "this far from zero", not the
 * number. */
function DistanceSpan(props: AbsoluteValueProps & { zeroX: number }): React.JSX.Element {
  const { axis_min: axisMin, axis_max: axisMax, point, zeroX } = props;
  const pointX = xFor(point, axisMin, axisMax);
  const left = Math.min(pointX, zeroX);
  const right = Math.max(pointX, zeroX);
  return (
    <g className="wm-intline-absolute" data-point={point}>
      <PointMark value={point} axisMin={axisMin} axisMax={axisMax} label={point} />
      {/* The distance bracket: a horizontal span over [point, 0] with end ticks down to the line. */}
      <line className="wm-intline-span" x1={left} y1={SPAN_Y} x2={right} y2={SPAN_Y} />
      <line className="wm-intline-span-tie" x1={left} y1={SPAN_Y} x2={left} y2={AXIS_Y} />
      <line className="wm-intline-span-tie" x1={right} y1={SPAN_Y} x2={right} y2={AXIS_Y} />
    </g>
  );
}
