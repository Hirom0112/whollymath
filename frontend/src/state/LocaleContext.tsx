// The learner's HELP-language preference (Slice 3.6 bilingual scaffold, V2_TODO §0.3).
//
// A pick-once + remember preference — which language the avatar's HINTS/NUDGES come back in.
// 'en' (default) or 'es-MX'. This selects the SPOKEN/help surface ONLY: the on-screen problem
// statement stays English (see TurnRequest.locale / StartSessionRequest.locale), and the value
// never reaches verify/mastery/policy on the turn loop (§8.1). Default 'en' keeps the English
// path byte-for-byte unchanged for every existing caller and test.
//
// Mirrors GuideContext exactly (the canonical "pick-once + remember" pattern): a provider that
// owns the state + persistence, a `useHelpLocale()` hook, and a safe fallback so components render
// outside the provider (component tests, embedded previews). localStorage is best-effort with
// try/catch so private mode / SSR degrade to the default rather than throwing.
//
// DEFERRED (NOT this slice): "the avatar reads the whole PROBLEM aloud in Spanish" (Rung-0). That
// needs Spanish problem-statement translation (Slice 3.2b, not built) and es-MX audio rendering
// (Slice 3.5, not done). For now Spanish is CAPTIONS-ONLY for the help text; this context does not
// touch the problem statement.

import { createContext, useCallback, useContext, useMemo, useState } from 'react';

/**
 * The help-language tags the backend accepts. Mirrors the `locale` literal on
 * `TurnRequest` / `StartSessionRequest` in @whollymath/shared-types — kept as a local alias
 * because shared-types exposes no standalone `Locale` export, only the per-field union.
 */
export type HelpLocale = 'en' | 'es-MX';

/** The default (and English) help-language. */
export const DEFAULT_HELP_LOCALE: HelpLocale = 'en';

// Where the picked help-language is remembered, so the choice persists across reloads/sessions —
// same best-effort, storage-tolerant pattern as the guide id and the theme/mute preferences.
const LOCALE_STORAGE_KEY = 'wm-help-locale';

interface LocaleContextValue {
  /** The learner's chosen help-language (defaults to 'en'). */
  locale: HelpLocale;
  /** Pick a help-language and remember it (pick-once + remember; changeable any time). */
  setLocale: (locale: HelpLocale) => void;
}

/** Read the persisted help-language, tolerating storage being unavailable (private mode, SSR). */
function readStoredLocale(): HelpLocale {
  try {
    const stored = window.localStorage?.getItem(LOCALE_STORAGE_KEY);
    // Only the two known tags are honored; anything else (corrupt/legacy) falls back to English.
    return stored === 'es-MX' || stored === 'en' ? stored : DEFAULT_HELP_LOCALE;
  } catch {
    return DEFAULT_HELP_LOCALE;
  }
}

const LocaleContext = createContext<LocaleContextValue | null>(null);

export function LocaleProvider({ children }: { children: React.ReactNode }): React.JSX.Element {
  const [locale, setLocaleState] = useState<HelpLocale>(() => readStoredLocale());

  const setLocale = useCallback((next: HelpLocale) => {
    setLocaleState(next);
    try {
      window.localStorage?.setItem(LOCALE_STORAGE_KEY, next);
    } catch {
      // Persistence is best-effort; the in-memory selection still applies this session.
    }
  }, []);

  const value = useMemo<LocaleContextValue>(() => ({ locale, setLocale }), [locale, setLocale]);

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

// A stable fallback for components rendered outside a provider (component tests, embedded previews).
// Defaults to English with an inert setter — the correct behavior when no provider drives the
// selection, and the reason `useHelpLocale()` never throws.
const FALLBACK: LocaleContextValue = {
  locale: DEFAULT_HELP_LOCALE,
  setLocale: () => {},
};

export function useHelpLocale(): LocaleContextValue {
  return useContext(LocaleContext) ?? FALLBACK;
}
