import { useState } from 'react';

import {
  startLesson,
  startSession,
  type KnowledgeComponentId,
  type StartSessionResponse,
} from './api';
import { BenchmarkTheater } from './pages/BenchmarkTheater';
import { ColdStart, type RouteKey } from './pages/ColdStart';
import { CourseMap } from './pages/CourseMap';
import { EvalComparison } from './pages/EvalComparison';
import { Homework } from './pages/Homework';
import { HomeworkUpload } from './pages/HomeworkUpload';
import { Landing } from './pages/Landing';
import { SignIn } from './pages/SignIn';
import { TeacherApp } from './pages/TeacherApp';
import { Tutor } from './pages/Tutor';

// Researcher/demo view: ?eval=1 shows the Slice 5.3 three-arm comparison dashboard,
// outside the student flow (no router; a query-param check keeps it zero-cost to wire).
const SHOW_EVAL = new URLSearchParams(window.location.search).get('eval') === '1';

// Teaching view: ?theater=1 shows the same comparison run step-by-step (the "benchmark
// theater") — one persona through all three arms, turn by turn. Same zero-router wiring.
const SHOW_THEATER = new URLSearchParams(window.location.search).get('theater') === '1';

// Teacher surface: ?teacher=1 opens the teacher dashboard (roster + per-student drill-in),
// the #1-priority visibility lane (TODO TCH.F0). Outside the student flow; same zero-router,
// query-param wiring as the eval / theater views, and the "I'm a teacher" link on the landing
// deep-links here.
const SHOW_TEACHER = new URLSearchParams(window.location.search).get('teacher') === '1';

// Mobile homework capture: ?hwupload=<token> is the URL the desktop's QR encodes (PROJECT.md
// §3.4 two-star model). On a phone it opens the camera/upload screen; the token pairs the photos
// to the desktop's run. Same zero-router query-param wiring as the views above.
const HW_UPLOAD_TOKEN = new URLSearchParams(window.location.search).get('hwupload');

// The skill the homework screen anchors to when entered from the home. Homework starts at
// LESSON 2 (equivalent fractions): Lesson 1 is number-line placement, whose answer is a mark on a
// line — nothing written for the scanner to read — so it has no scannable homework.
const HOMEWORK_KC: KnowledgeComponentId = 'KC_equivalence';

// Demo / A/B switch: ?proactive=1 opts into the proactive HelpNeed arm (Slice 4.5).
// Default OFF = observe-only (RESEARCH.md §7.5); not a learner-facing control.
const PROACTIVE = new URLSearchParams(window.location.search).get('proactive') === '1';

type View = 'landing' | 'sign_in' | 'home' | 'homework' | 'cold_start' | 'starting' | 'session';

// Root view switch. Landing → sign-in → the COURSE MAP home (Slice CP.A.2): the learner sees their
// whole learning path and clicks a skill to start its lesson, which calls POST /session and runs
// the Tutor turn loop (ARCHITECTURE.md §10). "Not sure where to start?" routes to the kid-friendly
// Turn-0 cold start (0.D.2). A plain state toggle (no router until there are real routes;
// CLAUDE.md §8.6).
export function App(): React.JSX.Element {
  const [view, setView] = useState<View>('landing');
  const [session, setSession] = useState<StartSessionResponse | null>(null);
  // The most recent session id, passed to the course map so an anonymous demo learner's map
  // reflects their in-session progress (a signed-in learner's map comes from persisted mastery).
  const [lastSessionId, setLastSessionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (HW_UPLOAD_TOKEN !== null && HW_UPLOAD_TOKEN !== '') {
    return <HomeworkUpload token={HW_UPLOAD_TOKEN} />;
  }

  if (SHOW_TEACHER) {
    return <TeacherApp />;
  }

  if (SHOW_THEATER) {
    return <BenchmarkTheater />;
  }

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
      setView('home');
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
          setView('home');
        }}
        onHomework={() => {
          setView('homework');
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
    return <SignIn onContinue={() => setView('home')} />;
  }

  if (view === 'home') {
    return (
      <>
        <CourseMap
          sessionId={lastSessionId}
          onStartLesson={(kc) => {
            void handleStartLesson(kc);
          }}
          onHomework={() => setView('homework')}
        />
        {error !== null ? <FloatingError message={error} /> : null}
      </>
    );
  }

  if (view === 'homework') {
    return <Homework kc={HOMEWORK_KC} sessionId={lastSessionId} onBack={() => setView('home')} />;
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
