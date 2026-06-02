import { useId } from 'react';

import './AreaChart.css';

import type { SparklineTone } from './Sparkline';

/** Reuse the Sparkline tone vocabulary so the two charts stay color-consistent. */
export type AreaChartTone = SparklineTone;

const TONE_VAR: Record<AreaChartTone, string> = {
  red: 'var(--wm-mean-wrong)',
  amber: 'var(--wm-mean-attention)',
  green: 'var(--wm-mean-correct)',
  blue: 'var(--wm-blue)',
};

export interface AreaChartProps {
  /** The series to plot, oldest → newest. Empty or single-point degrades gracefully. */
  data: number[];
  /** Meaning tone; maps to a `--wm-*` token so it follows the theme. Default `blue`. */
  tone?: AreaChartTone;
  /** Intrinsic SVG height in px (width is responsive via the viewBox). Default 96. */
  height?: number;
  /** Accessible label; the SVG is exposed as role="img". */
  ariaLabel?: string;
}

// The viewBox is a fixed coordinate space; the SVG scales to its container width.
const VIEW_W = 320;
const PAD = 3;

/**
 * A larger filled area chart for the "Student Insights" aggregate card. Draws a
 * stroked top line over a gradient fill that fades from the tone color to
 * transparent. Same token-driven coloring as Sparkline: the gradient stops and
 * the stroke use `currentColor`, set from the tone token on the wrapper, so it
 * is correct in light and dark with no hardcoded hex.
 */
export function AreaChart({
  data,
  tone = 'blue',
  height = 96,
  ariaLabel,
}: AreaChartProps): React.JSX.Element {
  // Unique, SSR-safe gradient id so multiple charts on a page don't collide.
  const gradientId = `wm-areachart-grad-${useId()}`;
  const points = buildPoints(data, height);
  const linePath = toLinePath(points);
  const areaPath = toAreaPath(points, height);
  const label = ariaLabel ?? 'trend over time';

  return (
    <svg
      className="wm-areachart"
      viewBox={`0 0 ${String(VIEW_W)} ${String(height)}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={label}
      style={{ color: TONE_VAR[tone] }}
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop className="wm-areachart-stop-top" offset="0%" />
          <stop className="wm-areachart-stop-bottom" offset="100%" />
        </linearGradient>
      </defs>
      {areaPath !== null && (
        <path className="wm-areachart-area" d={areaPath} fill={`url(#${gradientId})`} />
      )}
      {linePath !== null && <path className="wm-areachart-line" d={linePath} />}
      {points.length === 1 && (
        <circle className="wm-areachart-dot" cx={points[0].x} cy={points[0].y} r={3} />
      )}
    </svg>
  );
}

interface Point {
  x: number;
  y: number;
}

function buildPoints(data: number[], height: number): Point[] {
  if (data.length === 0) return [];

  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min;
  const innerW = VIEW_W - PAD * 2;
  const innerH = height - PAD * 2;

  return data.map((value, i) => {
    const x = data.length === 1 ? VIEW_W / 2 : PAD + (i / (data.length - 1)) * innerW;
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

function fmt(n: number): string {
  return Number(n.toFixed(2)).toString();
}
