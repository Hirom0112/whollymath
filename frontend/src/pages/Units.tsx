import { useEffect, useState } from 'react';

import { ApiError, fetchUnits, type UnitListView, type UnitView } from '../api';
import { type PathNodeTint } from '../components/LearningPathRail';
import { Mascot } from '../components/Mascot';
import './Units.css';

/**
 * The unit overview — the student "course shelf" (STU.3). Above the CourseMap's per-skill path,
 * this lists the whole Grade 6 curriculum as UNITS (Ratios, Fractions, …), each a card with its
 * status + percent-complete from `GET /units`. Clicking an unlocked unit opens its lesson list
 * (`onOpenUnit`). Add-don't-redesign: this is an ADDED surface; the CourseMap home is untouched
 * (the units-vs-coursemap-as-home call is the owner's, DEC.2). Read-only, off the turn loop.
 *
 * Data source mirrors the course map: a signed-in learner's progress comes from persisted mastery;
 * an anonymous demo learner passes `sessionId` so the list reflects in-session progress; a brand-new
 * visitor gets the fresh default. A teacher-assigned unit (DAT.10) is surfaced as a banner + a star
 * on its card, and is the primary "Keep going" target — absent gracefully for demo learners.
 */

// Per unit-status: a label + a call-to-action. The label always renders (status is never color-only).
const STATUS_META: Record<UnitView['status'], { label: string; cta: string }> = {
  locked: { label: 'Locked', cta: 'Finish the earlier units to unlock' },
  available: { label: 'Ready to start', cta: 'Start' },
  in_progress: { label: 'In progress', cta: 'Keep going' },
  mastered: { label: 'Mastered', cta: 'Review' },
};

// A friendly soft tint per card, cycled by teaching order so the shelf is warm and varied (the
// cold-start / CourseMap palette spirit). Tint is decoration, not status (the badge carries that).
const TINTS: readonly PathNodeTint[] = ['sky', 'mint', 'butter', 'warm', 'lavender'];

function tintFor(order: number): PathNodeTint {
  // order is 1-based in the catalog; fall back to 1 so a missing order still tints stably.
  return TINTS[(Math.max(1, order) - 1) % TINTS.length];
}

function UnitCard({
  unit,
  index,
  assigned,
  onOpen,
}: {
  unit: UnitView;
  index: number;
  assigned: boolean;
  onOpen: (slug: string) => void;
}): React.JSX.Element {
  const locked = unit.status === 'locked';
  const meta = STATUS_META[unit.status];
  const tint = tintFor(unit.order || index + 1);

  return (
    <li className={`wm-units-node wm-units-node--${unit.status}`}>
      <span className="wm-units-rail" aria-hidden="true">
        <span className={`wm-units-dot wm-units-dot--${tint}`}>
          {unit.status === 'mastered' ? '✓' : unit.order || index + 1}
        </span>
      </span>
      <button
        type="button"
        className={`wm-units-card wm-units-card--${tint}${assigned ? ' wm-units-card--assigned' : ''}`}
        disabled={locked}
        aria-disabled={locked}
        onClick={() => {
          if (!locked) onOpen(unit.unit_slug);
        }}
      >
        <span className="wm-units-card-top">
          <span className="wm-units-title">
            {unit.title}
            {assigned ? (
              <span className="wm-units-assigned-star" aria-label="Assigned by your teacher">
                <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                  <path d="M12 0 L14 10 L24 12 L14 14 L12 24 L10 14 L0 12 L10 10 Z" />
                </svg>
              </span>
            ) : null}
          </span>
          <span className={`wm-units-badge wm-units-badge--${unit.status}`}>{meta.label}</span>
        </span>
        <span className="wm-units-desc">{unit.description}</span>
        <span className="wm-units-meta">
          {(unit.ccss_cluster ?? unit.teks_cluster) != null ? (
            <span className="wm-units-codes">
              {[unit.ccss_cluster, unit.teks_cluster].filter(Boolean).join(' · ')}
            </span>
          ) : null}
          <span className="wm-units-lessoncount">
            {unit.lesson_count} {unit.lesson_count === 1 ? 'lesson' : 'lessons'}
          </span>
        </span>
        <span className="wm-units-progress" aria-hidden="true">
          <span className="wm-units-progress-fill" style={{ width: `${String(unit.percent_complete)}%` }} />
        </span>
        <span className="wm-units-cta">{meta.cta}</span>
      </button>
    </li>
  );
}

export function Units({
  sessionId,
  onOpenUnit,
  onBack,
}: {
  sessionId?: string | null;
  onOpenUnit: (slug: string) => void;
  onBack: () => void;
}): React.JSX.Element {
  const [data, setData] = useState<UnitListView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setError(null);
    fetchUnits(sessionId)
      .then((d) => {
        if (live) setData(d);
      })
      .catch((err: unknown) => {
        if (!live) return;
        const message =
          err instanceof ApiError && err.status === 401
            ? 'Please sign in again to see your units.'
            : 'We could not load your units just now. Please try again.';
        setError(message);
      });
    return () => {
      live = false;
    };
  }, [sessionId]);

  const units = data?.units ?? [];
  const assignedSlug = data?.assigned_unit_slug ?? null;
  const assignedUnit = assignedSlug != null ? units.find((u) => u.unit_slug === assignedSlug) : undefined;

  return (
    <main className="wm-units">
      <div className="wm-units-panel">
        <header className="wm-units-head">
          <span className="wm-units-pi" aria-hidden="true">
            <Mascot />
          </span>
          <div className="wm-units-headtext">
            <button type="button" className="wm-units-back" onClick={onBack}>
              ← Back to my path
            </button>
            <h1 className="wm-units-headline">Your units</h1>
            <p className="wm-units-subhead">
              Each unit is a little set of lessons. Pick one to see its lessons — finish a unit to
              unlock the next.
            </p>
          </div>
        </header>

        {assignedUnit !== undefined ? (
          <button
            type="button"
            className="wm-units-assigned-banner"
            onClick={() => {
              onOpenUnit(assignedUnit.unit_slug);
            }}
          >
            <span className="wm-units-assigned-banner-star" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 0 L14 10 L24 12 L14 14 L12 24 L10 14 L0 12 L10 10 Z" />
              </svg>
            </span>
            <span>
              <strong>Your teacher set this:</strong> {assignedUnit.title} — tap to keep going.
            </span>
          </button>
        ) : null}

        {error !== null ? (
          <p className="wm-units-error" role="alert">
            {error}
          </p>
        ) : null}

        {data === null && error === null ? (
          <p className="wm-units-loading">Loading your units…</p>
        ) : null}

        {data !== null && units.length === 0 && error === null ? (
          <p className="wm-units-empty">No units yet — check back soon.</p>
        ) : null}

        {units.length > 0 ? (
          <ol className="wm-units-list">
            {units.map((unit, i) => (
              <UnitCard
                key={unit.unit_slug}
                unit={unit}
                index={i}
                assigned={unit.unit_slug === assignedSlug}
                onOpen={onOpenUnit}
              />
            ))}
          </ol>
        ) : null}
      </div>
    </main>
  );
}
