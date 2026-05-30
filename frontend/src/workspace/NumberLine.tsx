import { useRef } from 'react';

import './NumberLine.css';

/**
 * The verdict the parent has reached for the placed marker (Slice AR.1). `null` while the
 * learner is still answering; `'correct'` / `'incorrect'` once the turn has been judged.
 *
 * On `'correct'` the widget makes the right answer FELT, not just stated: it draws the segment
 * from 0 to the placed tick and animates the marker travelling along it (the magnitude the
 * learner placed, now confirmed). On `'incorrect'` the widget shows NOTHING extra — no segment,
 * no snap to the right answer — so a wrong attempt is never silently corrected for them (the
 * neutral "let's look together" framing lives with the mascot in the parent).
 */
export type NumberLineVerdict = 'correct' | 'incorrect' | null;

/** Whether the viewer asked for reduced motion. Guarded for non-browser/jsdom callers
 * (matches the pattern in Landing.tsx): when set, the correct-answer reveal is shown instantly
 * with no marker travel or segment draw (honors prefers-reduced-motion). */
function prefersReducedMotion(): boolean {
  const mq = window.matchMedia?.('(prefers-reduced-motion: reduce)');
  return mq?.matches ?? false;
}

/**
 * The S2 number-line workspace (Slice 2.5): a draggable marker on a line that SNAPS to one of
 * `segments` equal ticks. This is the magnitude-exposing surface (ARCHITECTURE.md §7): the
 * learner places the amount rather than typing it.
 *
 * The axis is configurable (CP.B / CCSS 6.NS.6): by default it is the 0–1 unit interval, but a
 * lesson can stretch it RIGHT for an improper target (place 5/4 on 0–2) or LEFT of zero for a
 * negative target (place −3/4 on −1…1). `axisMin`/`axisMax` are the integer ends; `unitSegments`
 * is the ticks-per-whole (the target's denominator); `segments` is the TOTAL ticks across the
 * whole axis (= (axisMax − axisMin) × unitSegments). The marker `value` is a tick index in
 * 0…`segments`, so the placed amount is `axisMin + value / unitSegments`.
 *
 * Snapping is a SURFACE concern (verifier.py docstring). The parent composes the placed amount
 * as the fraction `(axisMin·unitSegments + value) / unitSegments` and the SymPy verifier judges
 * it by exact equality (§8.2) — so the displayed target lands exactly on a tick.
 *
 * Controlled: the parent owns the chosen tick index (or null before first placement). Pointer
 * users tap/drag the track; keyboard users use the start button then arrow the marker
 * (role="slider"). The pure snap math is unit-tested; the rest is visual.
 */

// SVG viewBox geometry (the track lives inside a fixed coordinate space; CSS scales it).
const VIEW_W = 560;
const VIEW_H = 180;
const AXIS_Y = 120;
const PAD = 44;
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

/** The signed fraction a tick index represents on an axis starting at `axisMin`, with
 * `unitSegments` ticks per whole: numerator = axisMin·unitSegments + tick, over unitSegments.
 * Returned unreduced — the verifier compares by exact Rational equality, and the chip reads
 * fine either way (e.g. "5/4", "-3/4"). */
export function tickFraction(
  tick: number,
  axisMin: number,
  unitSegments: number,
): { numerator: number; denominator: number } {
  return { numerator: axisMin * unitSegments + tick, denominator: unitSegments };
}

export function NumberLine({
  segments,
  value,
  onChange,
  axisMin = 0,
  axisMax = 1,
  unitSegments,
  disabled = false,
  verdict = null,
}: {
  /** TOTAL ticks across the whole axis (= (axisMax − axisMin) × unitSegments). */
  segments: number;
  value: number | null;
  onChange: (tick: number) => void;
  /** Integer left end of the axis (0 by default; negative to place a negative fraction). */
  axisMin?: number;
  /** Integer right end of the axis (1 by default; 2+ to place an improper fraction). */
  axisMax?: number;
  /** Ticks per whole (the target's denominator). Defaults to `segments` (the 0–1 case). */
  unitSegments?: number;
  disabled?: boolean;
  /** The judged verdict for the placed marker (Slice AR.1); see {@link NumberLineVerdict}. */
  verdict?: NumberLineVerdict;
}): React.JSX.Element {
  const svgRef = useRef<SVGSVGElement>(null);
  const perUnit = unitSegments ?? segments;

  function tickFromClientX(clientX: number): number {
    const svg = svgRef.current;
    if (svg === null) return 0;
    const rect = svg.getBoundingClientRect();
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

  // Integer landmarks (0, 1, 2, −1 …): a tick whose placed amount is a whole number. They get a
  // major tick and a label, so an extended/signed axis is readable ("the marker is past 1").
  function wholeLabelAt(k: number): number | null {
    const numerator = axisMin * perUnit + k;
    return numerator % perUnit === 0 ? numerator / perUnit : null;
  }

  const frac = value === null ? null : tickFraction(value, axisMin, perUnit);
  const chipLabel = frac === null ? null : `${String(frac.numerator)}/${String(frac.denominator)}`;
  const CHIP_HALF_W = 26;
  const chipX =
    markerX === null ? 0 : Math.min(Math.max(markerX, CHIP_HALF_W + 4), VIEW_W - CHIP_HALF_W - 4);
  const CHIP_Y = AXIS_Y - 64;

  // On a CORRECT verdict we draw the segment from 0 to the placed tick and animate the marker
  // travelling along it (the magnitude made felt — Slice AR.1). The zero point is wherever the
  // axis's 0 falls on the track: on a 0–1 axis it's the left end, but a signed axis (−1…1) has 0
  // in the middle, so we map the tick index of zero through the same geometry as the marker.
  const showCorrect = verdict === 'correct' && markerX !== null;
  const zeroTick = -axisMin * perUnit; // tick index whose placed amount is 0
  const zeroX = TRACK_START + (zeroTick / segments) * TRACK_LEN;
  // Reduced motion: render the final state instantly (no marker travel, no segment draw-on).
  const animate = showCorrect && !prefersReducedMotion();

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
        aria-label={`number line from ${String(axisMin)} to ${String(axisMax)}`}
      >
        <line x1={TRACK_START} y1={AXIS_Y} x2={TRACK_END} y2={AXIS_Y} className="wm-nl-track" />
        {ticks.map((k) => {
          const x = TRACK_START + (k / segments) * TRACK_LEN;
          const whole = wholeLabelAt(k);
          const major = whole !== null;
          const half = major ? 18 : 11;
          return (
            <g key={k}>
              <line
                x1={x}
                y1={AXIS_Y - half}
                x2={x}
                y2={AXIS_Y + half}
                className={major ? 'wm-nl-tick wm-nl-tick-major' : 'wm-nl-tick'}
              />
              {whole !== null ? (
                <text x={x} y={AXIS_Y + 46} className="wm-nl-end" textAnchor="middle">
                  {whole}
                </text>
              ) : null}
            </g>
          );
        })}
        {/* Correct-answer segment: emphasize 0 → placed tick (the amount the learner placed,
            now confirmed). Drawn only on a correct verdict; the draw-on is animated unless the
            viewer asked for reduced motion (then it appears at full length instantly). */}
        {showCorrect ? (
          <line
            x1={zeroX}
            y1={AXIS_Y}
            x2={markerX}
            y2={AXIS_Y}
            className={`wm-nl-segment${animate ? ' wm-nl-segment--draw' : ''}`}
            aria-hidden="true"
          />
        ) : null}
        {markerX !== null ? (
          <g
            className={`wm-nl-marker${showCorrect ? ' wm-nl-marker--correct' : ''}`}
            role="slider"
            tabIndex={disabled ? -1 : 0}
            aria-label="number line marker"
            aria-valuemin={0}
            aria-valuemax={segments}
            aria-valuenow={value ?? 0}
            aria-valuetext={chipLabel ?? undefined}
            onKeyDown={handleKeyDown}
          >
            <g className="wm-nl-chip" aria-hidden="true">
              <rect
                x={chipX - CHIP_HALF_W}
                y={CHIP_Y - 16}
                width={CHIP_HALF_W * 2}
                height={32}
                rx={11}
                className="wm-nl-chip-box"
              />
              <text x={chipX} y={CHIP_Y + 6} className="wm-nl-chip-text" textAnchor="middle">
                {chipLabel}
              </text>
            </g>
            {/* The red map-style pin the learner drops: its TIP sits exactly on the line at the
                chosen tick. The value chip above states the placed fraction. On a correct verdict
                (and unless reduced motion is requested) the pin TRAVELS from 0 to the placed tick
                — the keyframe interpolates the translate-x from `--wm-nl-from-x` to its resting X. */}
            <g
              className={`wm-nl-pin${animate ? ' wm-nl-pin--travel' : ''}`}
              transform={`translate(${String(markerX)}, ${String(AXIS_Y)})`}
              style={
                animate
                  ? ({
                      '--wm-nl-from-x': `${String(zeroX - markerX)}px`,
                    } as React.CSSProperties)
                  : undefined
              }
            >
              <path className="wm-nl-pin-body" d="M0 0 L-9 -21 A12 12 0 1 1 9 -21 Z" />
              <circle className="wm-nl-pin-dot" cx={0} cy={-27} r={4.5} />
            </g>
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
