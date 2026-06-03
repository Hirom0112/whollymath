import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { DEFAULT_HELP_LOCALE, LocaleProvider, useHelpLocale } from './LocaleContext';

// LocaleContext holds the learner's pick-once-and-remember HELP-language preference (Slice 3.6).
// Invariants: defaults to English, persists a picked language under the documented key
// `wm-help-locale`, reads a remembered choice on mount, and the out-of-provider fallback is the
// safe English/no-op.

const STORAGE_KEY = 'wm-help-locale';

function wrapper({ children }: { children: React.ReactNode }): React.JSX.Element {
  return <LocaleProvider>{children}</LocaleProvider>;
}

describe('useHelpLocale', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(() => {
    window.localStorage.clear();
  });

  it('defaults to English', () => {
    const { result } = renderHook(() => useHelpLocale(), { wrapper });
    expect(result.current.locale).toBe(DEFAULT_HELP_LOCALE);
    expect(result.current.locale).toBe('en');
  });

  it('setLocale picks a language and persists it to localStorage', () => {
    const { result } = renderHook(() => useHelpLocale(), { wrapper });

    act(() => {
      result.current.setLocale('es-MX');
    });

    expect(result.current.locale).toBe('es-MX');
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe('es-MX');
  });

  it('reads a remembered language on mount (pick-once + remember)', () => {
    window.localStorage.setItem(STORAGE_KEY, 'es-MX');
    const { result } = renderHook(() => useHelpLocale(), { wrapper });
    expect(result.current.locale).toBe('es-MX');
  });

  it('falls back to English for a corrupt/legacy stored value', () => {
    window.localStorage.setItem(STORAGE_KEY, 'fr-FR');
    const { result } = renderHook(() => useHelpLocale(), { wrapper });
    expect(result.current.locale).toBe('en');
  });

  it('outside a provider returns the safe English fallback with an inert setter', () => {
    const { result } = renderHook(() => useHelpLocale());
    expect(result.current.locale).toBe('en');
    act(() => {
      result.current.setLocale('es-MX');
    });
    // The no-op setter neither throws nor changes the locale.
    expect(result.current.locale).toBe('en');
  });
});
