import { useState } from 'react';

import {
  startLesson,
  startSession,
  type KnowledgeComponentId,
  type StartSessionResponse,
} from './api';
import { ColdStart, type RouteKey } from './pages/ColdStart';
import { CourseMap } from './pages/CourseMap';
import { EvalComparison } from './pages/EvalComparison';
import { Landing } from './pages/Landing';
import { SignIn } from './pages/SignIn';
import { Tutor } from './pages/Tutor';

// Researcher/demo view: ?eval=1 shows the Slice 5.3 three-arm comparison dashboard,
// outside the student flow (no router; a query-param check keeps it zero-cost to wire).
const SHOW_EVAL = new URLSearchParams(window.location.search).get('eval') === '1';

// Demo / A/B switch: ?proactive=1 opts into the proactive HelpNeed arm (Slice 4.5).
// Default OFF = observe-only (RESEARCH.md §7.5); not a learner-facing control.
const PROACTIVE = new URLSearchParams(window.location.search).get('proactive') === '1';

type View = 'landing' | 'sign_in' | 'course_map' | 'cold_start' | 'starting' | 'session';

// Root view switch. Landing → sign-in → the COURSE MAP (the home, Slice CP.A.2): the learner
// sees their whole learning path and clicks a skill to start its lesson, which calls POST
// /session and runs the Tutor turn loop (ARCHITECTURE.md §10). "Not sure where to start?" still
// routes to the kid-friendly Turn-0 cold start (0.D.2). A plain state toggle (no router until
// there are real routes; CLAUDE.md §8.6).
export function App(): React.JSX.Element {
  const [view, setView] = useState<View>('landing');
  const [session, setSession] = useState<StartSessionResponse | null>(null);
  // The most recent session id, passed to the course map so an anonymous demo learner's map
  // reflects their in-session progress (a signed-in learner's map comes from persisted mastery).
  const [lastSessionId, setLastSessionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (SHOW_EVAL) {
    return <EvalComparison />;
  }

  function enterSession(started: StartSessionResponse): void {
    setSession(started);
    setLastSessionId(started.session_id);
    setView('session');
  }

  // Launch a lesson directly for a course-map skill node (Slice CP.A.2).
  async function handleStartLesson(kc: KnowledgeComponentId): Promise<void> {
    setView('starting');
    setError(null);
    try {
      enterSession(await startLesson(kc, PROACTIVE));
    } catch {
      setError('We could not start that lesson. Please try again.');
      setView('course_map');
    }
  }

  // The Turn-0 cold-start path (0.D.2), reached from the map's "not sure where to start?".
  async function handleChoose(route: RouteKey): Promise<void> {
    setView('starting');
    setError(null);
    try {
      enterSession(await startSession(route, PROACTIVE));
    } catch {
      setError('We could not start your session. Please try again.');
      setView('cold_start');
    }
  }

  if (view === 'session' && session !== null) {
    return (
      <Tutor
        session={session}
        onExit={() => {
          setView('course_map');
        }}
      />
    );
  }

  if (view === 'starting') {
    return (
      <div className="wm-starting">
        Getting your first problem ready…
        <style>{`
          .wm-starting {
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            background: var(--wm-navy);
            color: var(--wm-cream);
            font-family: var(--wm-font-serif);
            font-weight: 500;
            font-size: 22px;
            letter-spacing: -0.3px;
            padding: 24px;
            text-align: center;
          }
        `}</style>
      </div>
    );
  }

  if (view === 'sign_in') {
    return <SignIn onContinue={() => setView('course_map')} />;
  }

  if (view === 'course_map') {
    return (
      <>
        <CourseMap
          sessionId={lastSessionId}
          onStartLesson={(kc) => {
            void handleStartLesson(kc);
          }}
        />
        {error !== null ? <FloatingError message={error} /> : null}
      </>
    );
  }

  if (view === 'cold_start') {
    return (
      <>
        <ColdStart
          onChoose={(route) => {
            void handleChoose(route);
          }}
        />
        {error !== null ? <FloatingError message={error} /> : null}
      </>
    );
  }

  return <Landing onStart={() => setView('sign_in')} />;
}

/** A small fixed toast for a start/launch failure (shared by the map + cold-start views). */
function FloatingError({ message }: { message: string }): React.JSX.Element {
  return (
    <p
      role="alert"
      style={{
        position: 'fixed',
        bottom: 16,
        left: '50%',
        transform: 'translateX(-50%)',
        margin: 0,
        padding: '10px 18px',
        background: 'var(--wm-coral)',
        color: 'var(--wm-cream)',
        fontFamily: 'var(--wm-font-sans)',
        fontSize: 15,
        borderRadius: 12,
      }}
    >
      {message}
    </p>
  );
}
