import { useState } from 'react';

import { Landing } from './pages/Landing';
import { Starting } from './pages/Starting';

type View = 'landing' | 'starting';

// Root view switch. The landing hands off to the "starting" seam once the mascot has
// rolled away; the tutor surfaces (S1–S5) mount on top of this in later slices. A plain
// state toggle for now (no router dependency until there are real routes; CLAUDE.md §8.6).
export function App(): React.JSX.Element {
  const [view, setView] = useState<View>('landing');

  if (view === 'starting') {
    return <Starting />;
  }
  return <Landing onStart={() => setView('starting')} />;
}
