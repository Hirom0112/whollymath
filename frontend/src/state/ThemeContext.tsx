// Light/dark theme context, scoped to the TEACHER surface (2026-06-01).
//
// Why this is teacher-only by construction: the dark palette lives behind the
// `[data-theme="dark"]` selector in styles/tokens.css. The ThemeProvider sets
// `document.documentElement.dataset.theme` ONLY while it is mounted — i.e. only while the
// teacher surface (TeacherApp) is on screen — and CLEARS it on unmount. The learner pages
// never mount this provider, so they never carry the attribute and never see dark mode.
// Even if a teacher signs out and lands on a learner page, the provider unmounts and the
// cleanup runs, returning <html> to its default (light) state.
//
// This is deliberately NOT a wrapper-element scope: the teacher chrome reads theme tokens
// via `:root`-level custom properties consumed across TeacherShell + the dashboard CSS, and
// CSS custom properties cascade from the documentElement. Scoping the attribute to <html>
// (with strict mount/unmount lifecycle) keeps the token override at the cascade root where
// those files already read it, while the lifecycle guarantees the teacher-only invariant.

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'wm-theme-preference';
const DEFAULT_THEME: Theme = 'light';

interface ThemeContextValue {
  /** The active theme for the teacher surface. */
  theme: Theme;
  /** Flip light ↔ dark, persist to localStorage, and update the <html> attribute. */
  toggle: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

/** Read the persisted preference, tolerating storage being unavailable (private mode, SSR). */
function readStoredTheme(): Theme {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === 'dark' ? 'dark' : DEFAULT_THEME;
  } catch {
    return DEFAULT_THEME;
  }
}

export function ThemeProvider({ children }: { children: React.ReactNode }): React.JSX.Element {
  const [theme, setTheme] = useState<Theme>(() => readStoredTheme());

  // Apply the theme to <html> while mounted; clear it on unmount so dark mode is teacher-only
  // and never leaks to learner pages.
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    return () => {
      delete document.documentElement.dataset.theme;
    };
  }, [theme]);

  const toggle = useCallback(() => {
    setTheme((prev) => {
      const next: Theme = prev === 'dark' ? 'light' : 'dark';
      try {
        window.localStorage.setItem(STORAGE_KEY, next);
      } catch {
        // Persistence is best-effort; the in-memory + applied state still flips.
      }
      return next;
    });
  }, []);

  const value = useMemo<ThemeContextValue>(() => ({ theme, toggle }), [theme, toggle]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

// A stable no-op fallback used when useTheme runs outside a ThemeProvider. TeacherShell —
// which lives under the provider in the real app — is also rendered standalone in component
// tests (TeacherDashboard.test, TeacherStudentView.test). Returning a safe light default there
// (rather than throwing) keeps the shell renderable in isolation while the real app always
// supplies the provider. The toggle is inert without a provider, which is correct: there is no
// teacher surface lifecycle to drive.
const FALLBACK: ThemeContextValue = { theme: DEFAULT_THEME, toggle: () => {} };

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext) ?? FALLBACK;
}
