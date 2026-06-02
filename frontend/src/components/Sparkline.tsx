import './Sparkline.css';

/**
 * Tone → meaning-layer color token. We resolve to a `var(--wm-*)` so the mark
 * adapts to light/dark automatically (the tokens are redefined per theme) and we
 * never hardcode a hex. `blue` reuses the primary/structure hue.
 */
export type SparklineTone = 'red' | 'amber' | 'green' | 'blue';

const TONE_VAR: Record<SparklineTone, string> = {
  red: 'var(--wm-mean-wrong)',
  amber: 'var(--wm-mean-attention)',
  green: 'var(--wm-mean-correct)',
  blue: 'var(--wm-blue)',
};

export interface SparklineProps {
  /** The series to plot, oldest → newest. Empty or single-point is handled gracefully. */
  data: number[];
  /** Meaning tone; maps to a `--wm-*` token so it follows the theme. Default `blue`. */
  tone?: SparklineTone;
  /** Intrinsic SVG width in px (the viewBox width). Default 64. */
  width?: number;
  /** Intrinsic SVG height in px (the viewBox height). Default 20. */
  height?: number;
  /** Accessible label; the SVG is exposed as role="img". */
  ariaLabel?: string;
}

// Inner padding so the stroke (and its cap) never clips at the viewBox edge.
const PAD = 2;

/**
 * A small inline trend mark: a stroked line with a soft filled area underneath.
 * Used both in the status-strip pills and on each student card. Purely
 * presentational — the caller hands it the already-computed series.
 *
 * Coloring is entirely token-driven via `currentColor`: the wrapper sets
 * `color` from the tone token, and the stroke/fill inherit it. That keeps the
 * mark correct in both themes with no JS branching.
 */
export function Sparkline({
  data,
  tone = 'blue',
  width = 64,
  height = 20,
  ariaLabel,
}: SparklineProps): React.JSX.Element {
  const points = buildPoints(data, width, height);
  const linePath = toLinePath(points);
  const areaPath = toAreaPath(points, height);
  const label = ariaLabel ?? 'trend';

  return (
    <svg
      className="wm-spark"
      viewBox={`0 0 ${String(width)} ${String(height)}`}
      width={width}
      height={height}
      preserveAspectRatio="none"
      role="img"
      aria-label={label}
      style={{ color: TONE_VAR[tone] }}
    >
      {areaPath !== null && <path className="wm-spark-area" d={areaPath} />}
      {linePath !== null && <path className="wm-spark-line" d={linePath} />}
      {points.length === 1 && (
        <circle className="wm-spark-dot" cx={points[0].x} cy={points[0].y} r={1.6} />
      )}
    </svg>
  );
}

interface Point {
  x: number;
  y: number;
}

/**
 * Map the series into viewBox coordinates. A flat or single-value series is
 * pinned to the vertical middle so it reads as "steady" rather than collapsing
 * to the floor. Returns [] for empty data (nothing is drawn).
 */
function buildPoints(data: number[], width: number, height: number): Point[] {
  if (data.length === 0) return [];

  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min;
  const innerW = width - PAD * 2;
  const innerH = height - PAD * 2;

  return data.map((value, i) => {
    const x = data.length === 1 ? width / 2 : PAD + (i / (data.length - 1)) * innerW;
    // SVG y grows downward, so a higher value sits nearer the top.
    const t = span === 0 ? 0.5 : (value - min) / span;
    const y = PAD + (1 - t) * innerH;
    return { x, y };
  });
}

function toLinePath(points: Point[]): string | null {
  if (points.length < 2) return null;
  return points.map((p, i) => `${i === 0 ? 'M' : 'L'}${fmt(p.x)} ${fmt(p.y)}`).join(' ');
}

function toAreaPath(points: Point[], height: number): string | null {
  if (points.length < 2) return null;
  const top = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${fmt(p.x)} ${fmt(p.y)}`).join(' ');
  const first = points[0];
  const last = points[points.length - 1];
  return `${top} L${fmt(last.x)} ${fmt(height)} L${fmt(first.x)} ${fmt(height)} Z`;
}

// Trim to 2dp so the path strings stay compact and stable across renders.
function fmt(n: number): string {
  return Number(n.toFixed(2)).toString();
}
