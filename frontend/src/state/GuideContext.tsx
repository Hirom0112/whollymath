// The learner's GUIDE preference + the device's guide CAPABILITY (Avatar Phase 0).
//
// Two concerns, one context (both are "what guide does this user get?"):
//
//  (a) Guide id — a pick-once + remember preference (mirrors the `wm-mascot-muted` / theme
//      localStorage pattern). The roster is decided per-learner and changeable later; Phase 0 has
//      exactly one guide, the existing CSS mascot, which is also the default.
//
//  (b) Capability — what runtime the device can drive, from `probeCapability()`. Phase 0 always
//      resolves "2d" (every user gets the mascot). Phase 1 adds the real WebGL2 + perf probe; the
//      context shape does not change when it does.
//
// Mirrors ThemeContext: a provider that owns the state + persistence, a `useGuide()` hook, and a
// safe fallback so components render outside the provider (component tests, embedded previews).

import { createContext, useCallback, useContext, useMemo, useState } from 'react';

import { type GuideCapability, probeCapability } from '../components/avatar/capabilityProbe';

/** The default (and, in Phase 0, only) guide: the existing CSS pie mascot. */
export const DEFAULT_GUIDE_ID = 'mascot';

// Where the picked guide is remembered, so the choice persists across reloads/sessions — same
// best-effort, storage-tolerant pattern as the mute preference and the theme preference.
const GUIDE_STORAGE_KEY = 'wm-guide-id';

interface GuideContextValue {
  /** The learner's chosen guide id (defaults to the mascot). */
  guideId: string;
  /** Pick a guide and remember it (pick-once + remember; changeable later). */
  setGuideId: (id: string) => void;
  /** What guide runtime this device can drive. Phase 0: always "2d". */
  capability: GuideCapability;
}

/** Read the persisted guide id, tolerating storage being unavailable (private mode, SSR). */
function readStoredGuideId(): string {
  try {
    return window.localStorage?.getItem(GUIDE_STORAGE_KEY) ?? DEFAULT_GUIDE_ID;
  } catch {
    return DEFAULT_GUIDE_ID;
  }
}

const GuideContext = createContext<GuideContextValue | null>(null);

export function GuideProvider({ children }: { children: React.ReactNode }): React.JSX.Element {
  const [guideId, setGuideIdState] = useState<string>(() => readStoredGuideId());

  // The device capability is probed ONCE at mount and held stable for the session. Phase 0 is
  // synchronous and always "2d"; Phase 1's perf probe can still resolve here without changing the
  // shape callers see.
  const [capability] = useState<GuideCapability>(() => probeCapability());

  const setGuideId = useCallback((id: string) => {
    setGuideIdState(id);
    try {
      window.localStorage?.setItem(GUIDE_STORAGE_KEY, id);
    } catch {
      // Persistence is best-effort; the in-memory selection still applies this session.
    }
  }, []);

  const value = useMemo<GuideContextValue>(
    () => ({ guideId, setGuideId, capability }),
    [guideId, setGuideId, capability],
  );

  return <GuideContext.Provider value={value}>{children}</GuideContext.Provider>;
}

// A stable fallback for components rendered outside a provider (component tests, embedded previews).
// Defaults to the mascot at "2d" capability with an inert setter — the correct Phase-0 behavior when
// no provider drives the selection.
const FALLBACK: GuideContextValue = {
  guideId: DEFAULT_GUIDE_ID,
  setGuideId: () => {},
  capability: '2d',
};

export function useGuide(): GuideContextValue {
  return useContext(GuideContext) ?? FALLBACK;
}
