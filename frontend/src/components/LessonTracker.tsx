import './LessonTracker.css';

/**
 * The lesson-progress tracker (replaces the old S1–S5 surface stepper). It reflects the
 * REDESIGNED curriculum (CURRICULUM_DRAFT.md §1.1): one skill = a ramp of practice problems
 * ending in the transfer probe as the mastery gate, then completion. So the arc a learner
 * actually travels is three stages, not five adaptive surfaces:
 *
 *   Practice  ─────▶  Final check  ─────▶  Got it!
 *
 * The Practice→Final-check rail FILLS with `progress` — the learner's position in the practice
 * ramp (problem N of ~length), so the climb is visible. The Final-check node lights during the
 * probe; Got it! lights when mastery is CONFIRMED.
 *
 * Read-only: lesson flow is engine-driven, not free navigation, so nothing here is clickable.
 * State is never carried by colour alone — each stage pairs colour with a glyph + label + the
 * fill width + aria-current (CLAUDE.md Principle 1). Plain global CSS, wm- prefixed.
 */

export type LessonPhase = 'practice' | 'check' | 'done';

const STAR_PATH = 'M12 0 L14 10 L24 12 L14 14 L12 24 L10 14 L0 12 L10 10 Z';

export function LessonTracker({
  /** How far through the practice ramp the learner is: 0–1 (problem N / lesson length). */
  progress,
  /** Which stage of the lesson arc the learner is in. */
  phase,
}: {
  progress: number;
  phase: LessonPhase;
}): React.JSX.Element {
  const pct = Math.max(0, Math.min(1, progress)) * 100;
  // The Practice→Final-check rail is full once practice is behind us (in the probe or done).
  const railPct = phase === 'practice' ? pct : 100;

  const practiceState = phase === 'practice' ? 'active' : 'done';
  const checkState = phase === 'check' ? 'active' : phase === 'done' ? 'done' : 'upcoming';
  const doneState = phase === 'done' ? 'active' : 'upcoming';

  return (
    <ol className="wm-lt" aria-label="Lesson progress">
      <li
        className={`wm-lt-step wm-lt-step--${practiceState}`}
        aria-current={phase === 'practice' ? 'step' : undefined}
      >
        <span className="wm-lt-dot" aria-hidden="true">
          {practiceState === 'done' ? <span className="wm-lt-check">✓</span> : null}
        </span>
        <span className="wm-lt-label">Practice</span>
      </li>

      {/* The climb: a rail that fills with readiness during practice, then stays full. */}
      <li className="wm-lt-rail" aria-hidden="true">
        <span className="wm-lt-rail-fill" style={{ width: `${String(railPct)}%` }} />
      </li>

      <li
        className={`wm-lt-step wm-lt-step--${checkState}`}
        aria-current={phase === 'check' ? 'step' : undefined}
      >
        <span className="wm-lt-dot wm-lt-dot--flag" aria-hidden="true">
          <span className="wm-lt-check">✓</span>
        </span>
        <span className="wm-lt-label">Final check</span>
      </li>

      <li className="wm-lt-rail wm-lt-rail--last" aria-hidden="true">
        <span className="wm-lt-rail-fill" style={{ width: phase === 'done' ? '100%' : '0%' }} />
      </li>

      <li
        className={`wm-lt-step wm-lt-step--${doneState}`}
        aria-current={phase === 'done' ? 'step' : undefined}
      >
        <span className="wm-lt-dot wm-lt-dot--star" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d={STAR_PATH} />
          </svg>
        </span>
        <span className="wm-lt-label">Got it!</span>
      </li>
    </ol>
  );
}
