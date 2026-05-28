import './FractionBar.css';

/**
 * The S3 fraction-bar workspace (Slice 2.5): an area model where the learner
 * partitions a bar into equal parts and shades some. This is the operation-exposing
 * surface (ARCHITECTURE.md §7, PROJECT.md §3.5) — reached when a learner runs the
 * wrong procedure, so they can rebuild the amount by manipulating parts.
 *
 * Controlled: the parent owns `{ segments, shaded }` and composes the "shaded/segments"
 * answer the domain SymPy verifier judges (correctness stays server-side, §8.2). The
 * value is unreduced on purpose — 2/4 and 1/2 are the same magnitude and the verifier
 * accepts either (it judges value, not lowest terms).
 *
 * Custom SVG per TECH_STACK §2. Class prefix `wm-fbar` is unique app-wide (plain
 * global CSS — reused names collide; see the NumberLine `.wm-numberline` incident).
 */

export interface BarValue {
  segments: number;
  shaded: number;
}

export const MIN_SEGMENTS = 1;
export const MAX_SEGMENTS = 12;

// SVG geometry (fixed coordinate space; CSS scales it).
const VIEW_W = 360;
const VIEW_H = 72;
const BAR_X = 8;
const BAR_Y = 14;
const BAR_W = VIEW_W - BAR_X * 2;
const BAR_H = 44;

/** The "shaded/segments" answer, or "" when nothing is shaded yet (incomplete). */
export function barToAnswer(value: BarValue): string {
  if (value.shaded <= 0) return '';
  return `${String(value.shaded)}/${String(value.segments)}`;
}

export function FractionBar({
  value,
  onChange,
  disabled = false,
}: {
  value: BarValue;
  onChange: (next: BarValue) => void;
  disabled?: boolean;
}): React.JSX.Element {
  const { segments, shaded } = value;
  const cellWidth = BAR_W / segments;

  function setSegments(next: number): void {
    if (disabled) return;
    const clamped = Math.max(MIN_SEGMENTS, Math.min(MAX_SEGMENTS, next));
    // Shrinking the partition can leave more shaded than exist — clamp it down.
    onChange({ segments: clamped, shaded: Math.min(shaded, clamped) });
  }

  function toggleTo(part: number): void {
    if (disabled) return;
    // Click fills from the left up to `part`; clicking the current edge unfills it.
    onChange({ segments, shaded: part === shaded ? part - 1 : part });
  }

  const cells = Array.from({ length: segments }, (_, k) => k);

  return (
    <div className="wm-fbar">
      <div className="wm-fbar-partition">
        <span className="wm-fbar-partition-label">Parts</span>
        <button
          type="button"
          className="wm-fbar-step"
          aria-label="fewer parts"
          disabled={disabled || segments <= MIN_SEGMENTS}
          onClick={() => {
            setSegments(segments - 1);
          }}
        >
          –
        </button>
        <span className="wm-fbar-count" aria-live="polite">
          {segments}
        </span>
        <button
          type="button"
          className="wm-fbar-step"
          aria-label="more parts"
          disabled={disabled || segments >= MAX_SEGMENTS}
          onClick={() => {
            setSegments(segments + 1);
          }}
        >
          +
        </button>
      </div>

      <svg
        viewBox={`0 0 ${String(VIEW_W)} ${String(VIEW_H)}`}
        width={VIEW_W}
        height={VIEW_H}
        className="wm-fbar-svg"
        role="group"
        aria-label="fraction bar"
      >
        {cells.map((k) => {
          const filled = k < shaded;
          return (
            <rect
              key={k}
              x={BAR_X + k * cellWidth}
              y={BAR_Y}
              width={cellWidth}
              height={BAR_H}
              className={`wm-fbar-cell${filled ? ' wm-fbar-cell--filled' : ''}`}
              role="button"
              tabIndex={disabled ? -1 : 0}
              aria-label={`part ${String(k + 1)} of ${String(segments)}`}
              aria-pressed={filled}
              onClick={() => {
                toggleTo(k + 1);
              }}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  toggleTo(k + 1);
                }
              }}
            />
          );
        })}
      </svg>
    </div>
  );
}
