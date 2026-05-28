import { useState } from 'react';

import { ColdStart, type RouteKey } from './pages/ColdStart';
import { Landing } from './pages/Landing';

type View = 'landing' | 'cold_start' | 'calibrating';

// Root view switch. The landing hands off to the cold-start routing screen (Turn 0,
// PROJECT.md decision 0.D.2) once the mascot has rolled away; the cold-start hands
// off to a brief, honest "calibrating" interstitial where the Turn-1 calibration
// problem will mount in a later slice. A plain state toggle (no router dependency
// until there are real routes; CLAUDE.md §8.6).
export function App(): React.JSX.Element {
  const [view, setView] = useState<View>('landing');
  // The route the learner chose at Turn 0. Held in App-scope state so the next slice
  // (Turn-1 calibration mount) can read it from a single source. Null until chosen.
  const [, setRoute] = useState<RouteKey | null>(null);

  if (view === 'calibrating') {
    // Honest placeholder — NOT a faked tutor (CLAUDE.md §5: production-grade or
    // reported partial). The real Turn-1 calibration surface lands in a later slice.
    return (
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'var(--wm-navy)',
          color: 'var(--wm-cream)',
          fontFamily: 'var(--wm-font-serif)',
          fontWeight: 500,
          fontSize: 22,
          letterSpacing: '-0.3px',
          padding: 24,
          textAlign: 'center',
        }}
      >
        Got it. Picking your first problem.
      </div>
    );
  }

  if (view === 'cold_start') {
    return (
      <ColdStart
        onChoose={(route) => {
          setRoute(route);
          setView('calibrating');
        }}
      />
    );
  }

  return <Landing onStart={() => setView('cold_start')} />;
}
