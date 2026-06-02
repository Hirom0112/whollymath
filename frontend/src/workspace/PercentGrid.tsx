import './PercentGrid.css';

/**
 * A DISPLAY-ONLY percent hundred-grid for KC_percent (CCSS 6.RP.A.3c): a 10x10 grid of 100 cells
 * with the named percent shaded, drawn as the visual anchor for "what is p% of a quantity?". A
 * percent IS a rate per 100, so a 30% item fills 30 of the 100 little squares — the picture carries
 * the meaning of the percent for a 6th grader.
 *
 * It shows only the QUESTION INPUT (the percent), NEVER the answer: "30% of 60" shades 30 cells, not
 * the computed 18. The correct value is graded server-side by SymPy (CLAUDE.md §8.2). The caption
 * ("30 per 100") and the prompt text stay the accessible fallback.
 *
 * Fully deterministic: cells fill in reading order (left-to-right, top-to-bottom) purely from the
 * `shaded` prop — no `Math.random` / `Date.now`, identical every render (PROJECT.md §4.1). Static
 * (no animation) → reduced-motion safe.
 *
 * Custom SVG, no charting/asset lib (TECH_STACK §2). Class names unique app-wide (prefix
 * `wm-pctgrid-`). Takes explicit typed props (mirroring the `PercentGridStimulus` dataclass), not a
 * ProblemView.
 */

/** Props mirror the backend `PercentGridStimulus` dataclass (snake_case field names). */
export interface PercentGridProps {
  /** The raw percent the prompt names (e.g. 30 for "30% of 60"). Used for the caption/label. */
  percent: number;
  /** How many of the 100 cells to shade — equals `percent` for an integer percent in [0, 100]. */
  shaded: number;
}

const GRID = 10; // 10 x 10 = 100 cells
const TOTAL = GRID * GRID;
const CELL = 24; // cell size in SVG units
const PAD = 6; // outer padding so the border stroke isn't clipped
const SIZE = GRID * CELL;
const VB = SIZE + PAD * 2;

/** Clamp to a whole number of cells in [0, 100] so a stray prop never overflows the grid. */
function clampCells(n: number): number {
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(TOTAL, Math.round(n)));
}

export function PercentGrid({ percent, shaded }: PercentGridProps): React.JSX.Element {
  const filled = clampCells(shaded);
  const label = `A hundred-grid with ${String(filled)} of 100 cells shaded: ${String(percent)} percent, a rate of ${String(percent)} per 100.`;
  // Cells fill in reading order (row 0 left-to-right, then row 1, ...) — deterministic, no shuffle.
  const cells = Array.from({ length: TOTAL }, (_, i) => {
    const row = Math.floor(i / GRID);
    const col = i % GRID;
    const isFilled = i < filled;
    return (
      <rect
        key={i}
        className={isFilled ? 'wm-pctgrid-cell wm-pctgrid-cell--on' : 'wm-pctgrid-cell'}
        data-cell-index={i}
        data-filled={isFilled ? 'true' : 'false'}
        x={PAD + col * CELL}
        y={PAD + row * CELL}
        width={CELL}
        height={CELL}
      />
    );
  });

  return (
    <figure className="wm-pctgrid">
      <svg
        className="wm-pctgrid-svg"
        viewBox={`0 0 ${String(VB)} ${String(VB)}`}
        role="img"
        aria-label={label}
        data-shaded={filled}
        data-percent={percent}
      >
        <g>{cells}</g>
        {/* Heavy outer frame on top of the cell strokes, for a clean navy border. */}
        <rect className="wm-pctgrid-frame" x={PAD} y={PAD} width={SIZE} height={SIZE} />
      </svg>
      <figcaption className="wm-pctgrid-caption">{String(percent)} per 100</figcaption>
    </figure>
  );
}
