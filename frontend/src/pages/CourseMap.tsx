import { useEffect, useState } from 'react';

import {
  ApiError,
  fetchCourse,
  type CourseNodeView,
  type CourseView,
  type KnowledgeComponentId,
} from '../api';
import { LearningPathRail, type PathNode, type PathNodeTint } from '../components/LearningPathRail';
import { Mascot } from '../components/Mascot';
import { PiMenu, type PiMenuItem } from '../components/PiMenu';
import './CourseMap.css';

/**
 * The course map — the post-sign-in / demo HOME (Slice CP.A.2, PROJECT.md §3.13).
 *
 * Renders the learner's whole learning path as a connected sequence of skill nodes, each with a
 * status (locked / available / in-progress / mastered / due-review) the backend derives from the
 * prerequisite graph + mastery + retention (`GET /course`). Clicking an unlocked node launches
 * that skill's lesson (`onStartLesson`). Locked nodes are not startable — their prerequisite is
 * not yet mastered.
 *
 * Data source: a signed-in learner's map comes from persisted mastery (auth token, set app-wide);
 * an anonymous demo learner passes their `sessionId` so the map reflects their in-session
 * progress; a brand-new visitor gets the fresh default path. The page is read-only and off the
 * turn loop.
 */

// A friendly soft tint per skill, by KC (stable — each skill always wears the same color), in
// the cold-start palette spirit. The tint is skill IDENTITY, not status (the badge carries
// status); it just makes the path warm and varied rather than five identical cards.
const KC_TINT: Record<string, PathNodeTint> = {
  KC_number_line_placement: 'sky',
  KC_equivalence: 'mint',
  KC_common_denominator: 'butter',
  KC_addition_unlike: 'warm',
  KC_subtraction_unlike: 'lavender',
};

// Normalize a course KC node into the shared rail's PathNode. Keeps the KC id branded end to end
// so the click handler still receives a KnowledgeComponentId.
function toPathNode(node: CourseNodeView): PathNode<KnowledgeComponentId> {
  return {
    id: node.kc_id,
    title: node.skill_name,
    description: node.description,
    status: node.status,
    tint: KC_TINT[node.kc_id] ?? 'sky',
    progressPct: node.probability != null ? node.probability * 100 : null,
  };
}

export function CourseMap({
  sessionId,
  onStartLesson,
  onBrowseUnits,
  onHomework,
  onExit,
}: {
  sessionId?: string | null;
  onStartLesson: (kc: KnowledgeComponentId) => void;
  /** Optional "go to the unit shelf" affordance for Pi's nav menu (Explore units, STU.3). */
  onBrowseUnits?: () => void;
  onHomework?: () => void;
  /** Optional "leave to home" affordance for Pi's nav menu (Save & exit). */
  onExit?: () => void;
}): React.JSX.Element {
  const [course, setCourse] = useState<CourseView | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Pi's nav menu items on the learning path. This page IS the dashboard (no "Dashboard" item —
  // it would point at itself), and Homework already has its own "Got homework? Tap me" bubble
  // beside Pi, so the menu does NOT repeat it. That leaves only "Save & exit" when a host wires
  // onExit; with no items, Pi is just the friendly mascot (no menu to open).
  const navItems: PiMenuItem[] = [];
  if (onBrowseUnits !== undefined) {
    navItems.push({ id: 'units', label: 'Explore units', icon: 'dashboard', onSelect: onBrowseUnits });
  }
  if (onExit !== undefined) {
    navItems.push({ id: 'exit', label: 'Save & exit', icon: 'exit', onSelect: onExit });
  }

  useEffect(() => {
    let live = true;
    setError(null);
    fetchCourse(sessionId)
      .then((data) => {
        if (live) setCourse(data);
      })
      .catch((err: unknown) => {
        if (!live) return;
        // A 401 means an expired/absent token on the signed-in path; we still want the page to
        // render, so surface a gentle message rather than a crash.
        const message =
          err instanceof ApiError && err.status === 401
            ? 'Please sign in again to see your course.'
            : 'We could not load your course just now. Please try again.';
        setError(message);
      });
    return () => {
      live = false;
    };
  }, [sessionId]);

  return (
    <main className="wm-coursemap">
      <div className="wm-coursemap-panel">
        <header className="wm-coursemap-head">
          {/* Pi on the learning path: just the friendly mascot. There is no "Dashboard" item (this
              page IS the dashboard) and no "Homework" item (the "Got homework? Tap me" bubble beside
              Pi is the homework doorway). Pi only becomes a tappable menu if a host wires extra
              actions (e.g. Save & exit); otherwise it is decorative. */}
          <div className="wm-coursemap-mascot-wrap">
            {navItems.length > 0 ? (
              <PiMenu items={navItems} label="Open the menu" />
            ) : (
              <span className="wm-pimenu-fig wm-coursemap-mascot-solo" aria-hidden="true">
                <Mascot />
              </span>
            )}
            {onHomework !== undefined ? (
              <button
                type="button"
                className="wm-coursemap-hw"
                onClick={onHomework}
                aria-label="Got homework? Scan the paper you worked on and we'll go through it together."
              >
                <span className="wm-coursemap-hw-bubble">
                  Got homework?
                  <span className="wm-coursemap-hw-tap">Tap me</span>
                </span>
              </button>
            ) : null}
          </div>
          <div>
            <h1 className="wm-coursemap-headline">Your learning path</h1>
            <p className="wm-coursemap-subhead">
              From “a fraction is a number” all the way to adding and subtracting. Pick a skill to
              start — each one unlocks the next.
            </p>
          </div>
        </header>

        {error !== null ? (
          <p className="wm-coursemap-error" role="alert">
            {error}
          </p>
        ) : null}

        {course === null && error === null ? (
          <p className="wm-coursemap-loading">Loading your path…</p>
        ) : null}

        {course !== null ? (
          <LearningPathRail
            nodes={(course.nodes ?? []).map(toPathNode)}
            onSelect={onStartLesson}
          />
        ) : null}
      </div>
    </main>
  );
}
