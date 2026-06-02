import { act, render, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { ThemeProvider, useTheme } from './ThemeContext';

// ThemeContext is the teacher-only light/dark switch. The load-bearing invariants tested here:
// toggle flips the theme, persists the choice to localStorage under the documented key, and the
// provider applies/clears the <html> data-theme attribute so dark mode never leaks past the
// teacher surface lifecycle.

const STORAGE_KEY = 'wm-theme-preference';

function wrapper({ children }: { children: React.ReactNode }): React.JSX.Element {
  return <ThemeProvider>{children}</ThemeProvider>;
}

describe('useTheme', () => {
  beforeEach(() => {
    window.localStorage.clear();
    delete document.documentElement.dataset.theme;
  });
  afterEach(() => {
    window.localStorage.clear();
    delete document.documentElement.dataset.theme;
  });

  it('defaults to light and applies data-theme="light" on mount', () => {
    const { result } = renderHook(() => useTheme(), { wrapper });
    expect(result.current.theme).toBe('light');
    expect(document.documentElement.dataset.theme).toBe('light');
  });

  it('toggle flips light → dark and persists the preference to localStorage', () => {
    const { result } = renderHook(() => useTheme(), { wrapper });

    act(() => {
      result.current.toggle();
    });

    expect(result.current.theme).toBe('dark');
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe('dark');
    expect(document.documentElement.dataset.theme).toBe('dark');
  });

  it('toggle flips back dark → light and re-persists', () => {
    const { result } = renderHook(() => useTheme(), { wrapper });

    act(() => {
      result.current.toggle();
    });
    act(() => {
      result.current.toggle();
    });

    expect(result.current.theme).toBe('light');
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe('light');
    expect(document.documentElement.dataset.theme).toBe('light');
  });

  it('reads a persisted "dark" preference on mount', () => {
    window.localStorage.setItem(STORAGE_KEY, 'dark');
    const { result } = renderHook(() => useTheme(), { wrapper });
    expect(result.current.theme).toBe('dark');
    expect(document.documentElement.dataset.theme).toBe('dark');
  });

  it('clears data-theme on unmount so dark mode does not leak to learner pages', () => {
    window.localStorage.setItem(STORAGE_KEY, 'dark');
    const view = render(
      <ThemeProvider>
        <div />
      </ThemeProvider>,
    );
    expect(document.documentElement.dataset.theme).toBe('dark');

    view.unmount();
    expect(document.documentElement.dataset.theme).toBeUndefined();
  });

  it('outside a provider returns a safe light default with an inert toggle', () => {
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe('light');
    act(() => {
      result.current.toggle();
    });
    expect(result.current.theme).toBe('light');
  });
});
