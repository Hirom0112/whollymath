import { useEffect, useRef, useState } from 'react';

import './SparkCount.css';

/** The four-point spark mark — drawn (never an emoji) to match the brand sparkle
 *  in Landing.tsx, tinted with the reward hue (--wm-mean-spark). Decorative. */
const SparkMark = (): React.JSX.Element => (
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M12 0 L14 10 L24 12 L14 14 L12 24 L10 14 L0 12 L10 10 Z" />
  </svg>
);

/**
 * The "sparks" reward pill for the top-right of the lesson screen. Purely
 * presentational: the parent computes `total` (sparks are earned only for real
 * learning, never for guessing — PRODUCT.md anti-reference: no slot-machine
 * points-spam), and this component just shows it.
 *
 * When `total` increases between renders it plays ONE restrained flourish — the
 * number pulses and a single small star lifts and fades (--wm-motion-spark,
 * ~600ms). No confetti, no sound, no looping, no combo meter. Under
 * prefers-reduced-motion the number updates instantly with no movement (the CSS
 * animations are disabled in a media query, so the JS need not branch).
 *
 * Accessibility: the count is plain readable text in an aria-live="polite"
 * region so increases are announced; the lifting star is aria-hidden.
 */
export function SparkCount({ total }: { total: number }): React.JSX.Element {
  const prevTotal = useRef(total);
  // A monotonically-bumped key so each increase restarts the one-shot animation
  // even on consecutive increments (React reuses the node otherwise).
  const [flourishKey, setFlourishKey] = useState(0);

  useEffect(() => {
    if (total > prevTotal.current) {
      setFlourishKey((k) => k + 1);
    }
    prevTotal.current = total;
  }, [total]);

  return (
    <div className="wm-sparks-pill">
      <span className="wm-sparks-star" aria-hidden="true">
        <SparkMark />
      </span>
      <span className="wm-sparks-count" aria-live="polite">
        <span
          key={flourishKey}
          className={flourishKey > 0 ? 'wm-sparks-num wm-sparks-num--pulse' : 'wm-sparks-num'}
        >
          {total}
        </span>{' '}
        sparks
      </span>
      {flourishKey > 0 && (
        <span key={flourishKey} className="wm-sparks-lift" aria-hidden="true">
          <SparkMark />
        </span>
      )}
    </div>
  );
}
