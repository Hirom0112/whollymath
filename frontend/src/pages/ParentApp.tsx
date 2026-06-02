import { useState } from 'react';

import { fetchHousehold, parentDemoLogin, setParentToken } from '../api/parent';
import { ThemeProvider } from '../state/ThemeContext';

import { ParentChildView } from './ParentChildView';
import { ParentCreateChild } from './ParentCreateChild';
import { ParentDashboard } from './ParentDashboard';
import { ParentSignIn } from './ParentSignIn';

/**
 * The parent surface container, mirroring TeacherApp. Reached at the real `/parent` route (single
 * route mounting this app with internal state — exactly like `/teacher` mounts TeacherApp). There is
 * deliberately NO `/parent/*` vite proxy, so the route stays a clean client-side deep link.
 *
 * Sign-in is the one-click demo-parent login: `parentDemoLogin()` mints the bearer token the client
 * echoes on every /api/parent/* call (stubbed for later), then `fetchHousehold()` loads the header
 * (parent name + household label) for the shell. Once in, a tiny internal router toggles the
 * household dashboard, a child drill-in, and the add-child form — no real router until there are
 * real parent routes (CLAUDE.md §8.6), mirroring TeacherApp.
 */

type ParentView = { kind: 'household' } | { kind: 'child'; childId: string } | { kind: 'addChild' };

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
  const [signingIn, setSigningIn] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [view, setView] = useState<ParentView>({ kind: 'household' });
  // Household header (parent name + label) for the shell side-nav across all views. Re-fetched after
  // adding a child so a refreshed household propagates (the dashboard fetches its own copy too).
  const [header, setHeader] = useState<{ parent: string; household: string } | null>(null);
  // Bumped to force the dashboard to remount and re-fetch after a child is added.
  const [refreshKey, setRefreshKey] = useState(0);

  function loadHeader(): void {
    fetchHousehold()
      .then((h) => {
        setHeader({ parent: h.parent_name, household: h.household_label });
      })
      .catch(() => {
        // Non-fatal: the shell falls back to a generic family label.
      });
  }

  async function handleSignIn(): Promise<void> {
    if (signingIn) return;
    setSigningIn(true);
    setAuthError(null);
    try {
      const handle = await parentDemoLogin();
      setParentToken(handle.token);
      setSignedIn(true);
      loadHeader();
    } catch {
      setAuthError('We could not start the parent demo. Please make sure the server is running.');
    } finally {
      setSigningIn(false);
    }
  }

  function handleSignOut(): void {
    setParentToken(null);
    setHeader(null);
    setSignedIn(false);
    setView({ kind: 'household' });
  }

  if (!signedIn) {
    return (
      <ParentSignIn
        busy={signingIn}
        error={authError}
        onSignIn={() => {
          void handleSignIn();
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

  return (
    <ParentDashboard
      key={refreshKey}
      onOpenChild={(childId) => setView({ kind: 'child', childId })}
      onAddChild={() => setView({ kind: 'addChild' })}
      onExit={handleSignOut}
    />
  );
}
