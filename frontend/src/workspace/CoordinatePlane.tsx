import { useRef, useState } from 'react';

import './CoordinatePlane.css';

import type { WorkspaceWidgetProps } from './WidgetContract';

/**
 * The coordinate-plane plotter (the Unit-? expressions-and-geometry KCs: plot a point on the
 * four-quadrant plane — 6.NS.8; read a point off a dependent-variable relationship — 6.EE.9; place
 * the vertices of a polygon — 6.G.3). The learner places point(s) on a grid rather than typing
 * coordinates, so the answer is a placed LOCATION, the magnitude-and-sign made visible the way the
 * number line does it for fractions.
 *
 * Controlled component (the HR.A5 {@link WorkspaceWidgetProps} contract): the parent owns the
 * answer `value` as a STRING and the widget renders / edits it. The string is the wire format —
 * a single point `"(2,-1)"`, or a comma-joined list for a polygon `"(0,0),(3,0),(3,2)"` — built to
 * be parsed + graded by the backend (point-set equality for a polygon, exact coords for a point);
 * the surface neither orders-normalizes nor grades it (CLAUDE.md §8.2). `maxPoints` is how many the
 * KC wants: 1 for a plot-a-point item, N for an N-gon. Placing beyond the cap rolls the oldest
 * point off (FIFO), so a learner can always correct without a separate clear.
 *
 * Interaction: click/tap a lattice point to place; a focusable keyboard CURSOR (role="application")
 * arrows around the grid and Enter/Space places at the cursor — so the widget is operable without a
 * pointer. Coordinates snap to integer lattice points (a surface concern; the verifier compares
 * exact integers). Reduced-motion safe: the place "pop" is withheld under prefers-reduced-motion.
 *
 * Custom SVG, no charting/graph lib (TECH_STACK §2). Class names unique app-wide (global CSS).
 *
 * Routed live: ``selectWidget`` returns ``'coordinate_plane'`` for ``widget_id="coordinate_plane"``
 * and the emitted point string is graded by the point-set SymPy verifier path, like the expression
 * widget.
 */

/** A placed lattice point. */
export interface GridPoint {
  x: number;
  y: number;
}

/** Whether the viewer asked for reduced motion. Guarded for non-browser/jsdom callers (matches the
 * NumberLine pattern): when set, the place "pop" is shown instantly with no scale animation. */
function prefersReducedMotion(): boolean {
  const mq = window.matchMedia?.('(prefers-reduced-motion: reduce)');
  return mq?.matches ?? false;
}

/** Render one point to its wire form, e.g. `(2,-1)`. No internal spaces — the canonical token the
 * backend contract will parse. */
function pointToToken(point: GridPoint): string {
  return `(${String(point.x)},${String(point.y)})`;
}

/** The answer string for a list of placed points: comma-joined point tokens, e.g.
 * `(0,0),(3,0),(3,2)`, or "" when nothing is placed. */
export function pointsToAnswer(points: readonly GridPoint[]): string {
  return points.map(pointToToken).join(',');
}

/** Parse a controlled answer string back into points. Tolerant of optional whitespace; ignores any
 * malformed token (a half-typed value can never crash the render — validity is the verifier's call,
 * §8.2). */
export function answerToPoints(answer: string): GridPoint[] {
  const points: GridPoint[] = [];
  const re = /\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(answer)) !== null) {
    points.push({ x: Number(match[1]), y: Number(match[2]) });
  }
  return points;
}

// SVG viewBox geometry: a square plane with padding for the axis-end labels.
const VIEW = 480;
const PAD = 28;
const PLOT = VIEW - PAD * 2;

export function CoordinatePlane({
  value,
  onChange,
  disabled = false,
  min = -10,
  max = 10,
  maxPoints = 1,
}: WorkspaceWidgetProps<string> & {
  /** Integer left/bottom end of both axes (6th-grade default −10). */
  min?: number;
  /** Integer right/top end of both axes (default 10). */
  max?: number;
  /** How many points the item wants placed: 1 for plot-a-point, N for an N-gon polygon. */
  maxPoints?: number;
}): React.JSX.Element {
  const svgRef = useRef<SVGSVGElement>(null);
  const points = answerToPoints(value);
  // The keyboard cursor's grid position (origin until the learner moves it). Pointer users never
  // see it; it only renders while the grid has keyboard focus.
  const [cursor, setCursor] = useState<GridPoint>({ x: 0, y: 0 });
  const [focused, setFocused] = useState(false);

  const span = max - min;
  // Map a grid coord to an SVG x/y. Y is flipped (SVG y grows downward; the plane's y grows up).
  const sx = (gx: number): number => PAD + ((gx - min) / span) * PLOT;
  const sy = (gy: number): number => PAD + ((max - gy) / span) * PLOT;

  // The nearest integer lattice point to a client pixel (for click/tap placement).
  function gridFromClient(clientX: number, clientY: number): GridPoint {
    const svg = svgRef.current;
    if (svg === null) return { x: 0, y: 0 };
    const rect = svg.getBoundingClientRect();
    const viewX = ((clientX - rect.left) / rect.width) * VIEW;
    const viewY = ((clientY - rect.top) / rect.height) * VIEW;
    const gx = min + ((viewX - PAD) / PLOT) * span;
    const gy = max - ((viewY - PAD) / PLOT) * span;
    return { x: clamp(Math.round(gx)), y: clamp(Math.round(gy)) };
  }

  function clamp(v: number): number {
    if (v < min) return min;
    if (v > max) return max;
    return v;
  }

  // Place a point, enforcing the maxPoints cap with FIFO eviction so a learner can always re-place
  // without a separate clear. A repeat tap on an already-placed point removes it (a toggle), which
  // is the natural "undo" for a misplaced vertex.
  function placePoint(point: GridPoint): void {
    if (disabled) return;
    const existing = points.findIndex((p) => p.x === point.x && p.y === point.y);
    let next: GridPoint[];
    if (existing !== -1) {
      next = points.filter((_, i) => i !== existing);
    } else {
      next = [...points, point];
      if (next.length > maxPoints) next = next.slice(next.length - maxPoints);
    }
    onChange(pointsToAnswer(next));
  }

  function handlePointerDown(event: React.PointerEvent<SVGSVGElement>): void {
    if (disabled) return;
    placePoint(gridFromClient(event.clientX, event.clientY));
  }

  function handleKeyDown(event: React.KeyboardEvent<SVGSVGElement>): void {
    if (disabled) return;
    if (event.key === 'ArrowRight') {
      event.preventDefault();
      setCursor((c) => ({ ...c, x: clamp(c.x + 1) }));
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault();
      setCursor((c) => ({ ...c, x: clamp(c.x - 1) }));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setCursor((c) => ({ ...c, y: clamp(c.y + 1) }));
    } else if (event.key === 'ArrowDown') {
      event.preventDefault();
      setCursor((c) => ({ ...c, y: clamp(c.y - 1) }));
    } else if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      placePoint(cursor);
    }
  }

  // Integer gridlines. We draw every line but emphasize the two axes (x=0, y=0). For a wide range
  // the minor lines stay light so the axes read as the frame.
  const lines = Array.from({ length: span + 1 }, (_, k) => min + k);
  const pop = !prefersReducedMotion();

  return (
    <div className="wm-coord">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${String(VIEW)} ${String(VIEW)}`}
        width={VIEW}
        height={VIEW}
        className="wm-coord-svg"
        role="application"
        aria-label={`coordinate plane from ${String(min)} to ${String(max)} on both axes; arrow keys move the cursor, Enter places a point`}
        tabIndex={disabled ? -1 : 0}
        onPointerDown={handlePointerDown}
        onKeyDown={handleKeyDown}
        onFocus={() => {
          setFocused(true);
        }}
        onBlur={() => {
          setFocused(false);
        }}
      >
        {lines.map((g) => {
          const major = g === 0;
          return (
            <g key={g}>
              <line
                x1={sx(g)}
                y1={PAD}
                x2={sx(g)}
                y2={VIEW - PAD}
                className={major ? 'wm-coord-axis' : 'wm-coord-grid'}
              />
              <line
                x1={PAD}
                y1={sy(g)}
                x2={VIEW - PAD}
                y2={sy(g)}
                className={major ? 'wm-coord-axis' : 'wm-coord-grid'}
              />
            </g>
          );
        })}
        {/* Axis-end labels (min/max) so the range is readable without counting gridlines. */}
        <text x={sx(max)} y={sy(0) - 6} className="wm-coord-label" textAnchor="middle">
          {max}
        </text>
        <text x={sx(0) + 8} y={sy(max) + 4} className="wm-coord-label" textAnchor="start">
          {max}
        </text>
        {/* A connecting outline for a polygon (maxPoints > 1) so the placed shape reads as a shape;
            closed once all the vertices are down. Decorative — the answer is the point set. */}
        {maxPoints > 1 && points.length > 1 ? (
          <polygon
            points={points.map((p) => `${String(sx(p.x))},${String(sy(p.y))}`).join(' ')}
            className="wm-coord-poly"
            aria-hidden="true"
          />
        ) : null}
        {/* The keyboard cursor — a hollow ring at the cursor coord, shown only while the grid has
            keyboard focus, so pointer users never see it. */}
        {focused && !disabled ? (
          <circle
            cx={sx(cursor.x)}
            cy={sy(cursor.y)}
            r={9}
            className="wm-coord-cursor"
            aria-hidden="true"
          />
        ) : null}
        {points.map((p, i) => (
          <g key={`${String(p.x)}:${String(p.y)}`}>
            <circle
              cx={sx(p.x)}
              cy={sy(p.y)}
              r={7}
              className={`wm-coord-point${pop ? ' wm-coord-point--pop' : ''}`}
            />
            <text x={sx(p.x) + 11} y={sy(p.y) - 9} className="wm-coord-coord" textAnchor="start">
              {pointToToken(p)}
            </text>
            {/* A hidden live label so a screen-reader user hears each placed point. */}
            <desc>{`Point ${String(i + 1)} at ${pointToToken(p)}`}</desc>
          </g>
        ))}
      </svg>
      <p className="wm-coord-readout" role="status">
        {points.length === 0
          ? maxPoints > 1
            ? `Place ${String(maxPoints)} points to draw the shape.`
            : 'Tap the grid to place your point.'
          : `Placed: ${pointsToAnswer(points)}`}
      </p>
    </div>
  );
}
