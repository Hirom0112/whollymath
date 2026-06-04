import { useEffect, useState } from 'react';

import { ApiError } from '../api/index';
import { fetchHousehold } from '../api/parent';
import { parentGoogle, parentLogin, parentLogout, parentMe } from '../api/parentAuth';
import { promptGoogleSignIn } from '../auth/google';
import { ThemeProvider } from '../state/ThemeContext';

import { ParentChildPicker } from './parent/ParentChildPicker';
import { ParentSignupWizard } from './parent/ParentSignupWizard';
import { ParentChildView } from './ParentChildView';
import { ParentCreateChild } from './ParentCreateChild';
import { ParentDashboard } from './ParentDashboard';
import { ParentSignIn } from './ParentSignIn';

/**
 * The parent surface container, mirroring TeacherApp. Reached at the real `/parent` route (single
 * route mounting this app with internal state — exactly like `/teacher`). There is deliberately NO
 * `/parent/*` SPA router: a tiny view state machine toggles every screen.
 *
 * Auth is now REAL (cookie session via api/parentAuth.ts): on mount we check `GET /parent/me`; if a
 * session exists we land on the dashboard, otherwise the sign-in gate. The gate's three ways in —
 * sign-up wizard, Google, email+password — and the secondary child sign-in are all driven from here.
 * Once signed in, the internal router toggles the dashboard, a child drill-in, the add-child form,
 * and the "who's practicing?" picker.
 */

type ParentView =
  | { kind: 'household' }
  | { kind: 'child'; childId: string }
  | { kind: 'addChild' }
  | { kind: 'picker' };

// Pre-auth screens shown when there is no parent session. (Child sign-in is NOT here — a
// child signs in on the student /signin page; the parent gate just links there.)
type GateView = 'signin' | 'wizard';

export function ParentApp(): React.JSX.Element {
  // The whole parent surface is wrapped in ThemeProvider so dark mode is set on <html> the entire
  // time the parent is on screen and cleared the moment the surface unmounts — never leaking to
  // learner pages (the same teacher-only invariant ThemeContext documents).
  return (
    <ThemeProvider>
      <ParentSurface />
    </ThemeProvider>
  );
}

function ParentSurface(): React.JSX.Element {
  const [signedIn, setSignedIn] = useState(false);
  // null = still checking the existing session (GET /parent/me).
  const [checking, setChecking] = useState(true);
  const [gate, setGate] = useState<GateView>('signin');
  const [signingIn, setSigningIn] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [view, setView] = useState<ParentView>({ kind: 'household' });
  // Household header (parent name + label) for the shell side-nav across all views.
  const [header, setHeader] = useState<{ parent: string; household: string } | null>(null);
  // Bumped to force the dashboard to remount and re-fetch after a child is added.
  const [refreshKey, setRefreshKey] = useState(0);

  // Resume an existing parent session on mount, so a returning, already-signed-in parent lands on
  // the dashboard without re-entering credentials.
  useEffect(() => {
    let live = true;
    parentMe()
      .then(() => {
        if (!live) return;
        setSignedIn(true);
        loadHeader();
      })
      .catch(() => {
        /* 401 (or offline) — stay on the sign-in gate */
      })
      .finally(() => {
        if (live) setChecking(false);
      });
    return () => {
      live = false;
    };
  }, []);

  function loadHeader(): void {
    fetchHousehold()
      .then((h) => {
        setHeader({ parent: h.parent_name, household: h.household_label });
      })
      .catch(() => {
        // Non-fatal: the shell falls back to a generic family label.
      });
  }

  function enterDashboard(): void {
    setSignedIn(true);
    setView({ kind: 'household' });
    loadHeader();
  }

  async function handleEmailLogin(email: string, password: string): Promise<void> {
    if (signingIn) return;
    if (email === '' || password === '') {
      setAuthError('Please enter your email and password.');
      return;
    }
    setSigningIn(true);
    setAuthError(null);
    try {
      await parentLogin({ email, password });
      enterDashboard();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setAuthError('That email or password did not match. Please try again.');
      } else {
        setAuthError('We could not sign you in. Please make sure the server is running.');
      }
    } finally {
      setSigningIn(false);
    }
  }

  async function handleGoogle(): Promise<void> {
    if (signingIn) return;
    setAuthError(null);
    const idToken = await promptGoogleSignIn();
    if (idToken === null) {
      setAuthError(
        'Google sign-in is not available right now. Please sign in with email or sign up.',
      );
      return;
    }
    setSigningIn(true);
    try {
      await parentGoogle(idToken);
      enterDashboard();
    } catch {
      setAuthError('We could not sign you in with Google. Please try email instead.');
    } finally {
      setSigningIn(false);
    }
  }

  function handleSignOut(): void {
    // Revoke the session SERVER-side (and clear the cookies) — not just forget it locally —
    // so a leaked/cached cookie is dead. Best-effort: we reset the UI regardless of the result.
    void parentLogout().catch(() => {
      /* already-invalid session / offline: the local reset below still signs the user out */
    });
    setHeader(null);
    setSignedIn(false);
    setGate('signin');
    setView({ kind: 'household' });
  }

  if (checking) {
    return <div className="wm-psignin" aria-busy="true" />;
  }

  if (!signedIn) {
    if (gate === 'wizard') {
      return (
        <ParentSignupWizard onComplete={enterDashboard} onBackToSignIn={() => setGate('signin')} />
      );
    }
    return (
      <ParentSignIn
        busy={signingIn}
        error={authError}
        onSignUp={() => {
          setAuthError(null);
          setGate('wizard');
        }}
        onGoogle={() => {
          void handleGoogle();
        }}
        onEmailLogin={(email, password) => {
          void handleEmailLogin(email, password);
        }}
        onChildSignIn={() => {
          // A child signs in on the student /signin page (their own/school device), not in the
          // parent portal — loop the link there per the single student sign-in surface.
          window.location.assign('/signin');
        }}
      />
    );
  }

  if (view.kind === 'child') {
    return (
      <ParentChildView
        childId={view.childId}
        onBack={() => setView({ kind: 'household' })}
        onExit={handleSignOut}
        parentName={header?.parent ?? null}
        householdLabel={header?.household ?? null}
      />
    );
  }

  if (view.kind === 'addChild') {
    return (
      <ParentCreateChild
        onCancel={() => setView({ kind: 'household' })}
        onDone={() => {
          // A new child was added: refresh the header + force the dashboard to re-fetch.
          loadHeader();
          setRefreshKey((k) => k + 1);
          setView({ kind: 'household' });
        }}
        onExit={handleSignOut}
        parentName={header?.parent ?? null}
        householdLabel={header?.household ?? null}
      />
    );
  }

  if (view.kind === 'picker') {
    return (
      <ParentChildPicker
        onBack={() => setView({ kind: 'household' })}
        onExit={handleSignOut}
        parentName={header?.parent ?? null}
        householdLabel={header?.household ?? null}
      />
    );
  }

  return (
    <ParentDashboard
      key={refreshKey}
      onOpenChild={(childId) => setView({ kind: 'child', childId })}
      onAddChild={() => setView({ kind: 'addChild' })}
      onStartPractice={() => setView({ kind: 'picker' })}
      onExit={handleSignOut}
    />
  );
}
