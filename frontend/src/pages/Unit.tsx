import { useEffect, useState } from 'react';

import {
  ApiError,
  fetchUnit,
  type KnowledgeComponentId,
  type LessonView,
  type UnitDetailView,
} from '../api';
import { LearningPathRail, type PathNode, type PathNodeTint } from '../components/LearningPathRail';
import { Mascot } from '../components/Mascot';
import './Unit.css';

/**
 * Unit detail — one unit's lessons as a learning path (STU.4). Reuses the SAME
 * {@link LearningPathRail} the CourseMap home uses (one rail, no divergence), scoped to this
 * unit's lessons from `GET /unit/{slug}`. Clicking an unlocked, built lesson starts its KC lesson
 * in the Tutor (`onStartLesson`); a lesson with no live KC yet shows a gentle "coming soon" notice
 * (DEC.3). Read-only, off the turn loop. Returning from a lesson remounts this page, which refetches
 * — so a just-completed lesson shows its advanced progress (STU.7).
 *
 * Pi rolls into the header and carries a small "Foundation work" button (owner request) that drops
 * the learner to the CourseMap's basic fraction skills (`onFoundation`).
 */

// A friendly soft tint per lesson, cycled by position so the path is warm and varied (the
// CourseMap palette spirit). Tint is decoration, not status (the badge carries that).
const TINTS: readonly PathNodeTint[] = ['sky', 'mint', 'butter', 'warm', 'lavender'];

// The KCs that actually have a live problem generator today. The unit catalog lists EVERY lesson
// with a kc_id and `available` status, but `POST /session` only returns a problem for the KCs T1's
// content lane has built — the rest 500/422 (no generator yet). Gating clicks on this set turns a
// dead "couldn't start, try again" toast into the honest "coming soon" notice the code already uses
// for an unbuilt lesson. This list must grow as each Grade-6 KC lands on `main` (T1 flags them in
// T1_T2_COORDINATION.md); it's the frontend half of the backend `LIVE_KCS`. STOPGAP: the whole gate
// drops once `widget_id` is authoritative for every lesson. (Verified 2026-05-30: each of these
// generates a problem on its live representation; all other catalog KCs → 500/422.)
const LIVE_KCS: ReadonlySet<string> = new Set([
  // The 5 foundation fraction KCs (CourseMap).
  'KC_equivalence',
  'KC_common_denominator',
  'KC_addition_unlike',
  'KC_subtraction_unlike',
  'KC_number_line_placement',
  // Grade-6 Unit 1 (Ratios & Rates) — committed numeric KCs (f39c6b0, c89c727). Whole-number
  // answers on the symbolic surface; the number-entry routing lives in WidgetContract.selectWidget.
  'KC_unit_rate',
  'KC_equivalent_ratios',
]);

// Show the lesson's standard codes as its one-line description — informative, and it surfaces the
// dual CCSS+TEKS tags in the learner view (the cross-cutting "standard codes in the surface" item).
function lessonCodes(lesson: LessonView): string {
  return [lesson.ccss_code, lesson.teks_code].filter(Boolean).join(' · ');
}

function toPathNode(lesson: LessonView, index: number): PathNode<string> {
  return {
    id: lesson.lesson_slug,
    title: lesson.title,
    description: lessonCodes(lesson),
    status: lesson.status,
    tint: TINTS[index % TINTS.length],
    progressPct: lesson.probability != null ? lesson.probability * 100 : null,
  };
}

export function Unit({
  slug,
  sessionId,
  onStartLesson,
  onBack,
  onFoundation,
}: {
  slug: string;
  sessionId?: string | null;
  onStartLesson: (kc: KnowledgeComponentId) => void;
  onBack: () => void;
  /** Drop to the CourseMap "foundation work" (the basic fraction skills) — Pi's button. */
  onFoundation: () => void;
}): React.JSX.Element {
  const [detail, setDetail] = useState<UnitDetailView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setError(null);
    setNotice(null);
    fetchUnit(slug, sessionId)
      .then((d) => {
        if (live) setDetail(d);
      })
      .catch((err: unknown) => {
        if (!live) return;
        const message =
          err instanceof ApiError && err.status === 404
            ? "We couldn't find that unit."
            : err instanceof ApiError && err.status === 401
              ? 'Please sign in again to see this unit.'
              : 'We could not load this unit just now. Please try again.';
        setError(message);
      });
    return () => {
      live = false;
    };
  }, [slug, sessionId]);

  const lessons = detail?.lessons ?? [];

  function handleSelect(lessonSlug: string): void {
    const lesson = lessons.find((l) => l.lesson_slug === lessonSlug);
    if (lesson === undefined) return;
    // Only KCs with a live problem generator actually start (LIVE_KCS). The catalog tags every
    // lesson with a kc_id and `available` status, but `POST /session` only serves the 5 fraction
    // KCs today — the rest 422/500. So we show the honest "coming soon" notice rather than letting
    // the host throw a confusing "couldn't start that lesson" toast (DEC.3). Drop this check when
    // T1 ships the remaining generators.
    if (lesson.kc_id != null && LIVE_KCS.has(lesson.kc_id)) {
      // Safe cast: membership in LIVE_KCS guarantees the value is a real KnowledgeComponentId.
      onStartLesson(lesson.kc_id as KnowledgeComponentId);
    } else {
      setNotice(`“${lesson.title}” is coming soon — its lessons aren't built yet.`);
    }
  }

  return (
    <main className="wm-unit">
      <div className="wm-unit-panel">
        <header className="wm-unit-head">
          <div className="wm-unit-head-row">
            <button type="button" className="wm-unit-back" onClick={onBack}>
              ← All units
            </button>
            {/* Pi rolls in and IS the foundation-work button (owner request): tap it to drop to the
                CourseMap's basic fraction skills. The roll is dropped under reduced-motion (CSS). */}
            <button
              type="button"
              className="wm-unit-foundation"
              onClick={onFoundation}
              aria-label="Go to foundation work — the basic fraction skills"
            >
              <span className="wm-unit-foundation-pi" aria-hidden="true">
                <Mascot />
              </span>
              <span className="wm-unit-foundation-label">Foundation work</span>
            </button>
          </div>
          {detail !== null ? (
            <>
              <h1 className="wm-unit-headline">{detail.title}</h1>
              {(detail.ccss_cluster ?? detail.teks_cluster) != null ? (
                <p className="wm-unit-codes">
                  {[detail.ccss_cluster, detail.teks_cluster].filter(Boolean).join(' · ')}
                </p>
              ) : null}
              <p className="wm-unit-subhead">{detail.description}</p>
              <p className="wm-unit-progress-summary">
                {detail.percent_complete}% complete · {detail.lesson_count}{' '}
                {detail.lesson_count === 1 ? 'lesson' : 'lessons'}
              </p>
            </>
          ) : null}
        </header>

        {error !== null ? (
          <p className="wm-unit-error" role="alert">
            {error}
          </p>
        ) : null}

        {detail === null && error === null ? (
          <p className="wm-unit-loading">Loading this unit…</p>
        ) : null}

        {detail !== null && lessons.length === 0 && error === null ? (
          <p className="wm-unit-empty">This unit's lessons are coming soon.</p>
        ) : null}

        {lessons.length > 0 ? (
          <LearningPathRail
            nodes={lessons.map(toPathNode)}
            onSelect={handleSelect}
            lockedCta="Finish the earlier lessons to unlock"
          />
        ) : null}

        {notice !== null ? (
          <p className="wm-unit-notice" role="status">
            {notice}
          </p>
        ) : null}
      </div>
    </main>
  );
}
