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
    // Only lessons the backend reports as `playable` actually start — `playable` is true exactly
    // when the lesson's KC is CONTENT-COMPLETE (in the backend `LIVE_KCS`: generator + spec +
    // hints), so `POST /session` can serve it. The catalog tags every lesson with a kc_id and an
    // `available` status, but an unbuilt KC 422/500s — so for those we show the honest "coming
    // soon" notice rather than a confusing "couldn't start that lesson" toast (DEC.3). The backend
    // is authoritative here (it owns `LIVE_KCS`); the frontend no longer keeps a parallel list to
    // drift.
    if (lesson.playable) {
      // Safe cast: a playable lesson's kc_id is, by the backend contract, a real built KC id (a
      // member of `LIVE_KCS`), hence a real KnowledgeComponentId. A playable lesson always carries
      // a non-null kc_id (a null kc_id is never playable), but we guard for type-narrowing.
      if (lesson.kc_id != null) onStartLesson(lesson.kc_id as KnowledgeComponentId);
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
