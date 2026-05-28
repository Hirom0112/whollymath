import { useRef } from 'react';

import './NumberLine.css';

/**
 * The S2 number-line workspace (Slice 2.5): a draggable marker on the 0–1 line that
 * SNAPS to one of `segments` equal ticks. This is the magnitude-exposing surface
 * (ARCHITECTURE.md §7): the learner places the amount rather than typing it.
 *
 * Snapping is a SURFACE concern (verifier.py docstring: "the surface snaps a drag to
 * a candidate Rational before it reaches the domain"). The candidate set is
 * k/segments for k=0..segments; the parent composes "k/segments" as the answer the
 * domain SymPy verifier judges by exact equality (§8.2). `segments` comes from the
 * problem's tick_segments hint, which equals the displayed target's denominator — so
 * the correct placement lands exactly on a tick.
 *
 * Controlled: the parent owns the chosen tick index (or null before first placement).
 * Pointer users tap/drag the track; keyboard users use the start button then arrow
 * the marker (role="slider"). Visual testing is sufficient for the component; the
 * pure snap math is unit-tested.
 */

// SVG viewBox geometry (the track lives inside a fixed coordinate space; CSS scales it).
const VIEW_W = 360;
const VIEW_H = 96;
const AXIS_Y = 52;
const PAD = 28;
const TRACK_START = PAD;
const TRACK_END = VIEW_W - PAD;
const TRACK_LEN = TRACK_END - TRACK_START;

/** Clamp a tick index into [0, segments]. */
export function clampTick(tick: number, segments: number): number {
  if (tick < 0) return 0;
  if (tick > segments) return segments;
  return tick;
}

/** The tick nearest a 0..1 ratio along the track (rounds, then clamps). */
export function nearestTick(ratio: number, segments: number): number {
  return clampTick(Math.round(ratio * segments), segments);
}

export function NumberLine({
  segments,
  value,
  onChange,
  disabled = false,
}: {
  segments: number;
  value: number | null;
  onChange: (tick: number) => void;
  disabled?: boolean;
}): React.JSX.Element {
  const svgRef = useRef<SVGSVGElement>(null);

  function tickFromClientX(clientX: number): number {
    const svg = svgRef.current;
    if (svg === null) return 0;
    const rect = svg.getBoundingClientRect();
    // Map the click into viewBox coords, then onto the track [0, 1] ratio.
    const viewX = ((clientX - rect.left) / rect.width) * VIEW_W;
    const ratio = (viewX - TRACK_START) / TRACK_LEN;
    return nearestTick(ratio, segments);
  }

  function handlePointerDown(event: React.PointerEvent<SVGSVGElement>): void {
    if (disabled) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    onChange(tickFromClientX(event.clientX));
  }

  function handlePointerMove(event: React.PointerEvent<SVGSVGElement>): void {
    if (disabled || event.buttons === 0) return;
    onChange(tickFromClientX(event.clientX));
  }

  function handleKeyDown(event: React.KeyboardEvent<SVGGElement>): void {
    if (disabled) return;
    const current = value ?? 0;
    if (event.key === 'ArrowRight' || event.key === 'ArrowUp') {
      event.preventDefault();
      onChange(clampTick(current + 1, segments));
    } else if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') {
      event.preventDefault();
      onChange(clampTick(current - 1, segments));
    }
  }

  const ticks = Array.from({ length: segments + 1 }, (_, k) => k);
  const markerX = value === null ? null : TRACK_START + (value / segments) * TRACK_LEN;

  return (
    <div className="wm-numline">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${String(VIEW_W)} ${String(VIEW_H)}`}
        width={VIEW_W}
        height={VIEW_H}
        className="wm-numline-svg"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        role="group"
        aria-label="number line from 0 to 1"
      >
        <line x1={TRACK_START} y1={AXIS_Y} x2={TRACK_END} y2={AXIS_Y} className="wm-nl-track" />
        {ticks.map((k) => {
          const x = TRACK_START + (k / segments) * TRACK_LEN;
          const major = k === 0 || k === segments;
          const half = major ? 11 : 6;
          return (
            <line
              key={k}
              x1={x}
              y1={AXIS_Y - half}
              x2={x}
              y2={AXIS_Y + half}
              className="wm-nl-tick"
            />
          );
        })}
        <text x={TRACK_START} y={AXIS_Y + 32} className="wm-nl-end" textAnchor="middle">
          0
        </text>
        <text x={TRACK_END} y={AXIS_Y + 32} className="wm-nl-end" textAnchor="middle">
          1
        </text>
        {markerX !== null ? (
          <g
            className="wm-nl-marker"
            role="slider"
            tabIndex={disabled ? -1 : 0}
            aria-label="number line marker"
            aria-valuemin={0}
            aria-valuemax={segments}
            aria-valuenow={value ?? 0}
            onKeyDown={handleKeyDown}
          >
            <line
              x1={markerX}
              y1={AXIS_Y - 20}
              x2={markerX}
              y2={AXIS_Y + 6}
              className="wm-nl-stem"
            />
            <circle cx={markerX} cy={AXIS_Y - 24} r={10} className="wm-nl-knob" />
          </g>
        ) : null}
      </svg>
      {value === null ? (
        <button
          type="button"
          className="wm-nl-start"
          disabled={disabled}
          onClick={() => {
            onChange(0);
          }}
        >
          Tap the line to place your marker
        </button>
      ) : null}
    </div>
  );
}
