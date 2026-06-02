import { useEffect, useRef, useState } from 'react';
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from 'react-router-dom';

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
import { ParentApp } from './pages/ParentApp';
import { RoleSelect } from './pages/RoleSelect';
import { SignIn } from './pages/SignIn';
import { TeacherApp } from './pages/TeacherApp';
import { Tutor } from './pages/Tutor';
import { Unit } from './pages/Unit';
import { Units } from './pages/Units';
import { GuideProvider } from './state/GuideContext';
import { SessionProvider, useSession } from './state/SessionContext';

// The skill the homework screen anchors to when entered from the home. Homework starts at
// LESSON 2 (equivalent fractions): Lesson 1 is number-line placement, whose answer is a mark on a
// line — nothing written for the scanner to read — so it has no scannable homework.
const HOMEWORK_KC: KnowledgeComponentId = 'KC_equivalence';

// Demo / A/B switch: ?proactive=1 opts into the proactive HelpNeed arm (Slice 4.5).
// Default OFF = observe-only (RESEARCH.md §7.5); not a learner-facing control. Read once at
// module load so it's a stable value for the whole run (the URL changes as the learner navigates).
const PROACTIVE = new URLSearchParams(window.location.search).get('proactive') === '1';

// The app entry. The router lives INSIDE App (App.tsx stays self-contained, and tests that render
// <App/> keep working) and is wrapped in the SessionProvider so every route shares the lesson
// hand-off + lastSessionId. The learner flow: Landing → sign-in → the UNITS page (units-first,
// DEC.2); a unit's lesson list launches the Tutor turn loop (ARCHITECTURE.md §10); the CourseMap
// "foundation work" and the Turn-0 cold start are reachable from there. Real URLs give the learner
// working browser back/forward and shareable deep links.
export function App(): React.JSX.Element {
  return (
    <SessionProvider proactive={PROACTIVE}>
      <GuideProvider>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </GuideProvider>
    </SessionProvider>
  );
}

// The route table, exported so route-specific tests can mount it inside a <MemoryRouter>
// (the App wrapper supplies a <BrowserRouter> for the real app).
export function AppRoutes(): React.JSX.Element {
  return (
    <Routes>
      <Route path="/" element={<LandingRoute />} />
      <Route path="/signin" element={<SignInRoute />} />
      <Route path="/units" element={<UnitsRoute />} />
      <Route path="/unit/:slug" element={<UnitRoute />} />
      <Route path="/foundation" element={<FoundationRoute />} />
      <Route path="/homework" element={<HomeworkRoute />} />
      <Route path="/start" element={<ColdStartRoute />} />
      <Route path="/lesson/:kc" element={<LessonRoute />} />
      <Route path="/teacher" element={<TeacherApp />} />
      <Route path="/welcome" element={<RoleSelect />} />
      <Route path="/parent" element={<ParentApp />} />
      <Route path="/eval" element={<EvalComparison />} />
      <Route path="/theater" element={<BenchmarkTheater />} />
      <Route path="/hw/upload" element={<HomeworkUploadRoute />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

// Where a lesson returns to when exited: the unit page it launched from, or the foundation map,
// stashed in nav state. A direct deep-load of /lesson/:kc has no such state; we fall back to /units.
interface LessonNavState {
  from?: string;
}

function readFrom(state: unknown, fallback: string): string {
  if (state !== null && typeof state === 'object' && 'from' in state) {
    const from = (state as LessonNavState).from;
    if (typeof from === 'string' && from !== '') return from;
  }
  return fallback;
}

// The Landing route also absorbs the legacy query-param entry points (existing links / printed QR
// codes may still use ?teacher=1, ?eval=1, ?theater=1, ?hwupload=<token>). We redirect them to the
// new paths once, preserving ?proactive=1, before rendering the landing for a plain visit.
function LandingRoute(): React.JSX.Element {
  const navigate = useNavigate();
  const [params] = useSearchParams();

  const teacher = params.get('teacher') === '1';
  const parent = params.get('parent') === '1';
  const evalArm = params.get('eval') === '1';
  const theater = params.get('theater') === '1';
  const hwUpload = params.get('hwupload');
  const proactive = params.get('proactive') === '1';

  const legacyTarget = ((): string | null => {
    const suffix = proactive ? '?proactive=1' : '';
    if (teacher) return `/teacher${suffix}`;
    if (parent) return `/parent${suffix}`;
    if (evalArm) return `/eval${suffix}`;
    if (theater) return `/theater${suffix}`;
    if (hwUpload !== null && hwUpload !== '') {
      const sep = proactive ? '&proactive=1' : '';
      return `/hw/upload?token=${encodeURIComponent(hwUpload)}${sep}`;
    }
    return null;
  })();

  if (legacyTarget !== null) {
    return <Navigate to={legacyTarget} replace />;
  }

  return <Landing onStart={() => navigate('/signin')} />;
}

// After sign-in the student lands on the UNITS page (the owner-approved units-first flow, DEC.2).
function SignInRoute(): React.JSX.Element {
  const navigate = useNavigate();
  return <SignIn onContinue={() => navigate('/units')} />;
}

// The unit overview — the student's HOME after sign-in (units-first flow, DEC.2). Lists the Grade-6
// units in teaching order; opening one shows its lessons. The CourseMap "foundation work" is one tap
// away via onFoundation.
function UnitsRoute(): React.JSX.Element {
  const navigate = useNavigate();
  const { lastSessionId } = useSession();
  return (
    <Units
      sessionId={lastSessionId}
      onOpenUnit={(slug) => navigate(`/unit/${slug}`)}
      onFoundation={() => navigate('/foundation')}
    />
  );
}

// One unit's lesson list (STU.4). A lesson navigates to /lesson/:kc with return-to-this-unit nav
// state (STU.5); the LessonRoute starts the session so refresh / deep-link behaves identically.
function UnitRoute(): React.JSX.Element {
  const navigate = useNavigate();
  const { slug = '' } = useParams();
  const { lastSessionId } = useSession();
  return (
    <Unit
      slug={slug}
      sessionId={lastSessionId}
      onStartLesson={(kc) => navigate(`/lesson/${kc}`, { state: { from: `/unit/${slug}` } })}
      onBack={() => navigate('/units')}
      onFoundation={() => navigate('/foundation')}
    />
  );
}

// The CourseMap "foundation work" (Slice CP.A.2): the whole learning path, with each skill node
// launching its own lesson. Reached from the units/unit pages (DEC.2).
function FoundationRoute(): React.JSX.Element {
  const navigate = useNavigate();
  const { lastSessionId } = useSession();
  return (
    <CourseMap
      sessionId={lastSessionId}
      onStartLesson={(kc) => navigate(`/lesson/${kc}`, { state: { from: '/foundation' } })}
      onBrowseUnits={() => navigate('/units')}
      onHomework={() => navigate('/homework')}
    />
  );
}

function HomeworkRoute(): React.JSX.Element {
  const navigate = useNavigate();
  const { lastSessionId } = useSession();
  return <Homework kc={HOMEWORK_KC} sessionId={lastSessionId} onBack={() => navigate(-1)} />;
}

// The Turn-0 cold-start path (0.D.2), reached from the foundation map's "not sure where to start?".
// Unlike a lesson click, cold start DOES pre-start here: the chosen route maps to a KC only after
// POST /session returns, so we start, stash the session, then navigate to its lesson URL.
function ColdStartRoute(): React.JSX.Element {
  const navigate = useNavigate();
  const { proactive, setStarted } = useSession();
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleChoose(route: RouteKey): Promise<void> {
    setStarting(true);
    setError(null);
    try {
      const resp = await startSession(route, proactive);
      setStarted(resp);
      navigate(`/lesson/${resp.problem.kc}`, { state: { from: '/start' } });
    } catch {
      setError('We could not start your session. Please try again.');
      setStarting(false);
    }
  }

  if (starting && error === null) {
    return <StartingScreen />;
  }

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

// The lesson route — the crux of the migration. On mount it first tries to claim a session the
// cold-start click already stashed (takePending); a refresh / deep-link finds none and starts one
// itself via startLesson. Either way the URL (/lesson/:kc) is the source of truth for WHICH lesson.
// A ref guards against StrictMode's deliberate double-invoke starting two sessions.
function LessonRoute(): React.JSX.Element {
  const navigate = useNavigate();
  const location = useLocation();
  const { kc = '' } = useParams();
  const { proactive, setStarted, takePending } = useSession();

  const [session, setSession] = useState<StartSessionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Guard so the start runs once per kc even under StrictMode's double mount. Keyed by kc so
  // navigating between lessons (a different :kc) starts the new one.
  const startedForKc = useRef<string | null>(null);

  useEffect(() => {
    if (kc === '') return;
    if (startedForKc.current === kc) return;
    startedForKc.current = kc;

    const kcId = kc as KnowledgeComponentId;
    const pending = takePending(kcId);
    if (pending !== null) {
      setSession(pending);
      return;
    }

    void (async (): Promise<void> => {
      try {
        const resp = await startLesson(kcId, proactive);
        // Apply only if this is still the active lesson. `startedForKc` is the single source
        // of truth: it survives StrictMode's mount→unmount→remount (so we neither double-start
        // nor hang waiting on a cancelled request), and it ignores a stale resolution after the
        // learner has navigated to a different :kc.
        if (startedForKc.current !== kcId) return;
        setStarted(resp);
        setSession(resp);
      } catch {
        if (startedForKc.current !== kcId) return;
        setError('We could not start that lesson. Please try again.');
      }
    })();
  }, [kc, proactive, setStarted, takePending]);

  if (error !== null) {
    return (
      <>
        <div className="wm-starting">
          <button
            type="button"
            onClick={() => navigate(readFrom(location.state, '/units'))}
            style={{
              padding: '12px 24px',
              background: 'var(--wm-cream)',
              color: 'var(--wm-navy)',
              border: 'none',
              borderRadius: 12,
              fontFamily: 'var(--wm-font-sans)',
              fontSize: 16,
              cursor: 'pointer',
            }}
          >
            Go back
          </button>
          <style>{STARTING_STYLE}</style>
        </div>
        <FloatingError message={error} />
      </>
    );
  }

  if (session === null) {
    return <StartingScreen />;
  }

  return (
    <Tutor
      session={session}
      onExit={() => navigate(readFrom(location.state, '/units'))}
      onHomework={() => navigate('/homework')}
    />
  );
}

function HomeworkUploadRoute(): React.JSX.Element {
  const [params] = useSearchParams();
  const token = params.get('token');
  if (token === null || token === '') {
    return <InvalidUploadLink />;
  }
  return <HomeworkUpload token={token} />;
}

/** The mobile-capture entry with a missing/empty token (mirrors the old fall-through to landing). */
function InvalidUploadLink(): React.JSX.Element {
  return (
    <div className="wm-starting">
      That homework link is invalid.
      <style>{STARTING_STYLE}</style>
    </div>
  );
}

const STARTING_STYLE = `
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
`;

/** The "Getting your first problem ready…" loading screen, shared by cold start + lesson start. */
function StartingScreen(): React.JSX.Element {
  return (
    <div className="wm-starting">
      Getting your first problem ready…
      <style>{STARTING_STYLE}</style>
    </div>
  );
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
