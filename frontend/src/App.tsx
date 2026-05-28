import { useState } from 'react';

import { startSession, type StartSessionResponse } from './api';
import { ColdStart, type RouteKey } from './pages/ColdStart';
import { Landing } from './pages/Landing';
import { Tutor } from './pages/Tutor';

type View = 'landing' | 'cold_start' | 'starting' | 'session';

// Root view switch. Landing → cold-start routing (Turn 0, decision 0.D.2) → a real
// session: choosing a route calls POST /session, then the Tutor surface drives the
// reactive turn loop (ARCHITECTURE.md §10). A plain state toggle (no router until
// there are real routes; CLAUDE.md §8.6).
export function App(): React.JSX.Element {
  const [view, setView] = useState<View>('landing');
  const [session, setSession] = useState<StartSessionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleChoose(route: RouteKey): Promise<void> {
    setView('starting');
    setError(null);
    try {
      const started = await startSession(route);
      setSession(started);
      setView('session');
    } catch {
      setError('We could not start your session. Please try again.');
      setView('cold_start');
    }
  }

  if (view === 'session' && session !== null) {
    return <Tutor session={session} />;
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

  if (view === 'cold_start') {
    return (
      <>
        <ColdStart
          onChoose={(route) => {
            void handleChoose(route);
          }}
        />
        {error !== null ? (
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
            {error}
          </p>
        ) : null}
      </>
    );
  }

  return <Landing onStart={() => setView('cold_start')} />;
}
