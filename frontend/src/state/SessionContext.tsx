// Session hand-off context for the router migration.
//
// When a learner clicks a lesson, the click handler kicks off POST /session and then
// navigates to `/lesson/:kc`. The started StartSessionResponse can't ride on the URL,
// so it's stashed here ("pendingSession") for the LessonRoute to pick up on mount. This
// keeps the cold-start case (where we DO pre-start) fast, while a fresh deep-load/refresh
// of `/lesson/:kc` simply finds no pending session and starts one itself — identical
// behavior either way (the URL is the source of truth for WHICH lesson; the context is a
// transient hand-off, never the source of truth).
//
// `lastSessionId` is the most recent session id, threaded to the units/unit/course-map/
// homework pages exactly as the old useState did (an anonymous demo learner's progress).
//
// `proactive` is the demo / A/B switch read ONCE from `?proactive=1` (Slice 4.5); default
// OFF = observe-only (RESEARCH.md §7.5). Not a learner-facing control.

import { createContext, useContext, useMemo, useRef, useState } from 'react';

import type { KnowledgeComponentId, StartSessionResponse } from '../api';

interface SessionContextValue {
  /** The most recent session id (anonymous demo progress), or null before any session. */
  lastSessionId: string | null;
  /** Whether this run opted into the proactive HelpNeed arm (`?proactive=1`). */
  proactive: boolean;
  /** Record a freshly started session: updates lastSessionId AND stashes it for hand-off. */
  setStarted: (resp: StartSessionResponse) => void;
  /**
   * Claim a stashed session iff it is the one for `kc` (its first problem's goal KC).
   * Clears the stash on a match (single-use hand-off); returns null otherwise.
   */
  takePending: (kc: KnowledgeComponentId) => StartSessionResponse | null;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({
  proactive,
  children,
}: {
  proactive: boolean;
  children: React.ReactNode;
}): React.JSX.Element {
  const [lastSessionId, setLastSessionId] = useState<string | null>(null);
  // A ref, not state: stashing/claiming the hand-off must not trigger a re-render, and a
  // claim during the LessonRoute's mount effect must read the value set synchronously by
  // the cold-start click that navigated here.
  const pendingSession = useRef<StartSessionResponse | null>(null);

  const value = useMemo<SessionContextValue>(
    () => ({
      lastSessionId,
      proactive,
      setStarted: (resp: StartSessionResponse): void => {
        setLastSessionId(resp.session_id);
        pendingSession.current = resp;
      },
      takePending: (kc: KnowledgeComponentId): StartSessionResponse | null => {
        const pending = pendingSession.current;
        if (pending !== null && pending.problem.kc === kc) {
          pendingSession.current = null;
          return pending;
        }
        return null;
      },
    }),
    [lastSessionId, proactive],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const value = useContext(SessionContext);
  if (value === null) {
    throw new Error('useSession must be used within a SessionProvider');
  }
  return value;
}
