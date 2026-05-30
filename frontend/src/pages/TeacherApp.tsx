import { useState } from 'react';

import { setTeacherToken } from '../api/teacher';

import { TeacherDashboard } from './TeacherDashboard';
import { TeacherSignIn } from './TeacherSignIn';
import { TeacherStudentView } from './TeacherStudentView';

/**
 * The teacher surface container (TODO TCH.F0). Reached at `?teacher=1` (the same zero-router,
 * query-param convention App.tsx uses for the eval / theater / homework-upload views) and from
 * the "I'm a teacher" link on the landing page.
 *
 * It gates on a demo-teacher sign-in (TODO TCH.Q1: demo login now, real OIDC role later — the
 * demo path sets a bearer token so the swap to T1's TCH.B2 auth is just wiring a real token),
 * then runs a tiny internal router between the roster (TCH.F2) and a student drill-in (TCH.F3).
 * No real router until there are real teacher routes (CLAUDE.md §8.6), mirroring the learner App.
 */

type TeacherView = { kind: 'roster' } | { kind: 'student'; studentId: string };

export function TeacherApp(): React.JSX.Element {
  const [signedIn, setSignedIn] = useState(false);
  const [view, setView] = useState<TeacherView>({ kind: 'roster' });

  if (!signedIn) {
    return (
      <TeacherSignIn
        onSignIn={() => {
          // Demo teacher: a placeholder bearer until lane T1's real teacher auth (TCH.B2). The
          // /teacher client reads this token; the demo data path ignores it.
          setTeacherToken('demo-teacher');
          setSignedIn(true);
        }}
      />
    );
  }

  if (view.kind === 'student') {
    return (
      <TeacherStudentView
        studentId={view.studentId}
        onBack={() => setView({ kind: 'roster' })}
      />
    );
  }

  return (
    <TeacherDashboard
      onOpenStudent={(studentId) => setView({ kind: 'student', studentId })}
      onExit={() => {
        setTeacherToken(null);
        setSignedIn(false);
      }}
    />
  );
}
