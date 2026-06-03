import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { LocaleProvider } from '../state/LocaleContext';

import { HelpLanguageToggle } from './HelpLanguageToggle';

// The toggle's STATE POLICY (CLAUDE.md §2: state-transition logic gets tests). Visual styling is
// not asserted here. We verify: default reflects English, clicking flips to es-MX and persists to
// localStorage['wm-help-locale'], a re-mount reads the stored value, and the control is an
// accessible button whose aria-pressed tracks "Spanish active".

const STORAGE_KEY = 'wm-help-locale';

function renderToggle(): void {
  render(
    <LocaleProvider>
      <HelpLanguageToggle />
    </LocaleProvider>,
  );
}

describe('HelpLanguageToggle', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(() => {
    window.localStorage.clear();
  });

  it('renders an accessible button defaulting to English (not pressed)', () => {
    renderToggle();
    const button = screen.getByRole('button', { name: /switch hints to spanish/i });
    expect(button).toHaveAttribute('aria-pressed', 'false');
  });

  it('clicking flips to es-MX, persists to localStorage, and flips aria-pressed', () => {
    renderToggle();

    fireEvent.click(screen.getByRole('button', { name: /switch hints to spanish/i }));

    expect(window.localStorage.getItem(STORAGE_KEY)).toBe('es-MX');
    const button = screen.getByRole('button', { name: /switch hints to english/i });
    expect(button).toHaveAttribute('aria-pressed', 'true');
  });

  it('clicking again flips back to English and persists', () => {
    renderToggle();

    fireEvent.click(screen.getByRole('button', { name: /switch hints to spanish/i }));
    fireEvent.click(screen.getByRole('button', { name: /switch hints to english/i }));

    expect(window.localStorage.getItem(STORAGE_KEY)).toBe('en');
    expect(screen.getByRole('button', { name: /switch hints to spanish/i })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
  });

  it('re-mounts reading the stored es-MX value (pick-once + remember)', () => {
    window.localStorage.setItem(STORAGE_KEY, 'es-MX');
    renderToggle();
    expect(screen.getByRole('button', { name: /switch hints to english/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });
});
