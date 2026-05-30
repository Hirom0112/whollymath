import './FigureStimulus.css';

/**
 * A display-only geometry figure renderer for the Unit-6 area / volume KC problem statements
 * (rectangle / triangle / parallelogram area; right-rectangular-prism volume). It draws a labeled
 * figure from STRUCTURED props so a problem statement can show "find the area of THIS rectangle"
 * with its base and height marked — the dimensions the learner computes with.
 *
 * This is a STIMULUS, not an answer input: it renders in the problem-statement area and is NOT a
 * WorkspaceWidget. Geometry answers stay numeric and are entered through the existing number_entry
 * widget. So this component takes no value/onChange and never touches selectWidget / the answer
 * contract — it only displays.
 *
 * Accessibility: the figure is one labeled image (role="img") with an aria-label that reads the
 * shape and its measurements ("rectangle, base 8 cm, height 3 cm"), so a screen-reader user gets the
 * same information the drawing carries. The SVG is static (no animation), so it is inherently
 * reduced-motion safe.
 *
 * Custom SVG, no charting/geometry lib (TECH_STACK §2). Class names unique app-wide (global CSS).
 */

/** The figures a problem statement can show, with the labeled dimensions each needs. Discriminated
 * on `shape` so the labels are type-checked per shape. Label values are strings (e.g. "8 cm") so the
 * item owns the units. */
export type FigureSpec =
  | { shape: 'rectangle'; labels: { base: string; height: string } }
  | { shape: 'triangle'; labels: { base: string; height: string } }
  | { shape: 'parallelogram'; labels: { base: string; height: string } }
  | { shape: 'prism'; labels: { length: string; width: string; height: string } };

/** The screen-reader description of a figure — the shape and its measurements, in reading order. */
export function describeFigure(spec: FigureSpec): string {
  switch (spec.shape) {
    case 'rectangle':
      return `Rectangle, base ${spec.labels.base}, height ${spec.labels.height}`;
    case 'triangle':
      return `Triangle, base ${spec.labels.base}, height ${spec.labels.height}`;
    case 'parallelogram':
      return `Parallelogram, base ${spec.labels.base}, height ${spec.labels.height}`;
    case 'prism':
      return `Right rectangular prism, length ${spec.labels.length}, width ${spec.labels.width}, height ${spec.labels.height}`;
  }
}

// SVG viewBox geometry (a fixed coordinate space; CSS scales it).
const VIEW_W = 360;
const VIEW_H = 280;

function Rectangle({ base, height }: { base: string; height: string }): React.JSX.Element {
  return (
    <>
      <rect x={70} y={70} width={220} height={120} className="wm-fig-shape" />
      {/* base label below the bottom edge, height label outside the left edge */}
      <text x={180} y={210} textAnchor="middle" className="wm-fig-dim">
        {base}
      </text>
      <text x={52} y={130} textAnchor="end" className="wm-fig-dim">
        {height}
      </text>
    </>
  );
}

function Triangle({ base, height }: { base: string; height: string }): React.JSX.Element {
  return (
    <>
      <polygon points="70,190 290,190 150,70" className="wm-fig-shape" />
      {/* dashed height altitude from the apex to the base */}
      <line x1={150} y1={70} x2={150} y2={190} className="wm-fig-aux" />
      <text x={180} y={210} textAnchor="middle" className="wm-fig-dim">
        {base}
      </text>
      <text x={138} y={134} textAnchor="end" className="wm-fig-dim">
        {height}
      </text>
    </>
  );
}

function Parallelogram({ base, height }: { base: string; height: string }): React.JSX.Element {
  return (
    <>
      <polygon points="110,190 310,190 250,70 50,70" className="wm-fig-shape" />
      {/* dashed perpendicular height between the two parallel sides */}
      <line x1={110} y1={190} x2={110} y2={70} className="wm-fig-aux" />
      <text x={210} y={210} textAnchor="middle" className="wm-fig-dim">
        {base}
      </text>
      <text x={98} y={134} textAnchor="end" className="wm-fig-dim">
        {height}
      </text>
    </>
  );
}

function Prism({
  length,
  width,
  height,
}: {
  length: string;
  width: string;
  height: string;
}): React.JSX.Element {
  // A right rectangular prism drawn in oblique projection: a front face plus a top and side offset.
  const dx = 50;
  const dy = -34;
  return (
    <>
      {/* front face */}
      <rect x={70} y={120} width={180} height={110} className="wm-fig-shape" />
      {/* top face */}
      <polygon
        points={`70,120 ${String(70 + dx)},${String(120 + dy)} ${String(250 + dx)},${String(120 + dy)} 250,120`}
        className="wm-fig-shape wm-fig-shape--back"
      />
      {/* right face */}
      <polygon
        points={`250,120 ${String(250 + dx)},${String(120 + dy)} ${String(250 + dx)},${String(230 + dy)} 250,230`}
        className="wm-fig-shape wm-fig-shape--back"
      />
      {/* length along the front-bottom edge, height up the front-right edge, width along the top */}
      <text x={160} y={250} textAnchor="middle" className="wm-fig-dim">
        {length}
      </text>
      <text x={262} y={180} textAnchor="start" className="wm-fig-dim">
        {height}
      </text>
      <text x={String(250 + dx + 6)} y={String(120 + dy / 2)} textAnchor="start" className="wm-fig-dim">
        {width}
      </text>
    </>
  );
}

export function FigureStimulus({ spec }: { spec: FigureSpec }): React.JSX.Element {
  return (
    <div className="wm-fig">
      <svg
        viewBox={`0 0 ${String(VIEW_W)} ${String(VIEW_H)}`}
        width={VIEW_W}
        height={VIEW_H}
        className="wm-fig-svg"
        role="img"
        aria-label={describeFigure(spec)}
      >
        {spec.shape === 'rectangle' ? <Rectangle {...spec.labels} /> : null}
        {spec.shape === 'triangle' ? <Triangle {...spec.labels} /> : null}
        {spec.shape === 'parallelogram' ? <Parallelogram {...spec.labels} /> : null}
        {spec.shape === 'prism' ? <Prism {...spec.labels} /> : null}
      </svg>
    </div>
  );
}
