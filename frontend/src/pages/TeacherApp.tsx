import { useState } from 'react';

import { demoLogin, fetchRoster, setTeacherToken } from '../api/teacher';

import { TeacherDashboard } from './TeacherDashboard';
import { TeacherSignIn } from './TeacherSignIn';
import { TeacherStudentView } from './TeacherStudentView';

/**
 * The teacher surface container (TODO TCH.F0). Reached at `?teacher=1` (the same zero-router,
 * query-param convention App.tsx uses for the eval / theater / homework-upload views) and from
 * the "I'm a teacher" link on the landing page.
 *
 * Sign-in is the one-click demo-teacher login (TCH.B2/TCH.Q1): `POST /teacher/demo-login` seeds-or-
 * returns the durable demo teacher + its class and mints the bearer token the client then echoes
 * on every /teacher/* call. (Real Google/OIDC teacher login is the later swap; both buttons use
 * the demo login for now since that's the only teacher auth wired.) Once in, a tiny internal
 * router toggles the roster (TCH.F2) and a student drill-in (TCH.F3) — no real router until there
 * are real teacher routes (CLAUDE.md §8.6), mirroring the learner App.
 */

type TeacherView = { kind: 'roster' } | { kind: 'student'; studentId: string };

export function TeacherApp(): React.JSX.Element {
  const [signedIn, setSignedIn] = useState(false);
  const [signingIn, setSigningIn] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [view, setView] = useState<TeacherView>({ kind: 'roster' });
  // Class header (teacher + class name) for the shell side-nav. The dashboard fetches its own
  // roster; this fetch makes the same header available to the student drill-in's shell too.
  const [header, setHeader] = useState<{ teacher: string; klass: string } | null>(null);

  async function handleSignIn(): Promise<void> {
    if (signingIn) return;
    setSigningIn(true);
    setAuthError(null);
    try {
      const handle = await demoLogin();
      setTeacherToken(handle.token);
      setSignedIn(true);
      fetchRoster()
        .then((roster) => {
          setHeader({ teacher: roster.teacher_name, klass: roster.class_name });
        })
        .catch(() => {
          // Non-fatal: the shell falls back to a generic class label.
        });
    } catch {
      setAuthError('We could not start the teacher demo. Please make sure the server is running.');
    } finally {
      setSigningIn(false);
    }
  }

  function handleSignOut(): void {
    setTeacherToken(null);
    setHeader(null);
    setSignedIn(false);
    setView({ kind: 'roster' });
  }

  if (!signedIn) {
    return (
      <TeacherSignIn
        busy={signingIn}
        error={authError}
        onSignIn={() => {
          void handleSignIn();
        }}
      />
    );
  }

  if (view.kind === 'student') {
    return (
      <TeacherStudentView
        studentId={view.studentId}
        onBack={() => setView({ kind: 'roster' })}
        onExit={handleSignOut}
        teacherName={header?.teacher ?? null}
        klassName={header?.klass ?? null}
      />
    );
  }

  return (
    <TeacherDashboard
      onOpenStudent={(studentId) => setView({ kind: 'student', studentId })}
      onExit={handleSignOut}
    />
  );
}
