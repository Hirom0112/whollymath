import { useEffect, useLayoutEffect, useState } from 'react';

import './ParentDashboardTour.css';

/**
 * First-run guided tour over the parent dashboard (S6). A lightweight overlay that, on first visit
 * (gated by a localStorage flag), walks the parent through the dashboard in 4-5 steps: the child
 * cards + status pills, the "view progress" drill-in, practicing at home, adding a child, and where
 * to start a child practicing.
 *
 * Each step targets an existing dashboard element by CSS selector and draws a highlight ring around
 * it plus a caption bubble; steps with no on-screen target render a centered caption. The tour never
 * blocks interaction permanently — "Skip" / "Got it" dismiss it and set the flag. Self-contained
 * and on-brand. Unique classes (`.wm-ptour-*`).
 */

export const PARENT_TOUR_FLAG = 'wm_parent_tour_done';

/** Whether the first-run tour should show (flag not yet set). Safe if storage is unavailable. */
export function shouldShowParentTour(): boolean {
  try {
    return window.localStorage.getItem(PARENT_TOUR_FLAG) !== 'done';
  } catch {
    return false;
  }
}

interface TourStep {
  /** CSS selector for the element to highlight; null = a centered, untargeted caption. */
  target: string | null;
  title: string;
  body: string;
}

const STEPS: TourStep[] = [
  {
    target: '.wm-parent-card',
    title: 'Your kids, at a glance',
    body: 'Each card shows one child. The colored pill tells you how they’re doing right now — on track, needs attention, or struggling.',
  },
  {
    target: '.wm-parent-card-cta',
    title: 'Dive into the details',
    body: 'Tap a child’s card to see exactly what they practiced, where they shine, and where to lend a hand.',
  },
  {
    target: '.wm-parent-insights',
    title: 'Practice at home',
    body: 'See how the whole family is doing this week, and use the notes to remember what to ask about at home.',
  },
  {
    target: '.wm-parent-add',
    title: 'Add another child',
    body: 'Got more kids? Create a login for each one here — they each get their own progress.',
  },
  {
    target: null,
    title: 'Hand off the device',
    body: 'When it’s time to practice, use “Let a child practice” to start their session on this device. That’s it — you’re all set!',
  },
];

interface Rect {
  top: number;
  left: number;
  width: number;
  height: number;
}

export function ParentDashboardTour({
  onClose,
}: {
  onClose: () => void;
}): React.JSX.Element | null {
  const [index, setIndex] = useState(0);
  const [rect, setRect] = useState<Rect | null>(null);

  const step = STEPS[index];
  const isLast = index === STEPS.length - 1;

  // Measure the target element each time the step changes (layout effect so the ring is positioned
  // before paint). A missing target falls back to a centered caption (rect = null).
  useLayoutEffect(() => {
    if (step.target === null) {
      setRect(null);
      return;
    }
    const el = document.querySelector(step.target);
    if (el === null) {
      setRect(null);
      return;
    }
    const r = el.getBoundingClientRect();
    setRect({ top: r.top, left: r.left, width: r.width, height: r.height });
    el.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [step.target, index]);

  // Re-measure on resize so the ring tracks the target if the layout shifts.
  useEffect(() => {
    function remeasure(): void {
      if (step.target === null) {
        setRect(null);
        return;
      }
      const el = document.querySelector(step.target);
      if (el === null) {
        setRect(null);
        return;
      }
      const r = el.getBoundingClientRect();
      setRect({ top: r.top, left: r.left, width: r.width, height: r.height });
    }
    window.addEventListener('resize', remeasure);
    return () => window.removeEventListener('resize', remeasure);
  }, [step.target]);

  function finish(): void {
    try {
      window.localStorage.setItem(PARENT_TOUR_FLAG, 'done');
    } catch {
      /* storage unavailable — still dismiss for this session */
    }
    onClose();
  }

  function next(): void {
    if (isLast) {
      finish();
    } else {
      setIndex((i) => i + 1);
    }
  }

  // Position the caption near the highlighted target (below it, clamped), or centered if untargeted.
  const PAD = 8;
  const ringStyle: React.CSSProperties | undefined =
    rect === null
      ? undefined
      : {
          top: rect.top - PAD,
          left: rect.left - PAD,
          width: rect.width + PAD * 2,
          height: rect.height + PAD * 2,
        };

  return (
    <div className="wm-ptour" role="dialog" aria-modal="true" aria-label="Dashboard tour">
      <div className="wm-ptour-scrim" onClick={finish} aria-hidden="true" />

      {ringStyle !== undefined ? <div className="wm-ptour-ring" style={ringStyle} /> : null}

      <div
        className={'wm-ptour-bubble' + (rect === null ? ' wm-ptour-bubble--center' : '')}
        style={
          rect === null
            ? undefined
            : {
                top: Math.min(rect.top + rect.height + 18, window.innerHeight - 220),
                left: Math.max(16, Math.min(rect.left, window.innerWidth - 360)),
              }
        }
      >
        <div className="wm-ptour-count">
          Step {index + 1} of {STEPS.length}
        </div>
        <h2 className="wm-ptour-title">{step.title}</h2>
        <p className="wm-ptour-body">{step.body}</p>
        <div className="wm-ptour-dots" aria-hidden="true">
          {STEPS.map((s, i) => (
            <span
              key={s.title}
              className={'wm-ptour-dot' + (i === index ? ' wm-ptour-dot--on' : '')}
            />
          ))}
        </div>
        <div className="wm-ptour-actions">
          <button type="button" className="wm-ptour-skip" onClick={finish}>
            Skip tour
          </button>
          <button type="button" className="wm-ptour-next" onClick={next}>
            {isLast ? 'Got it' : 'Next'}
          </button>
        </div>
      </div>
    </div>
  );
}
