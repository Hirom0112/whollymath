import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { App } from './App';

// Smoke test: proves the toolchain (vitest + RTL + jsdom) is wired and green, and that
// the landing renders its primary call to action. Richer interaction tests (the roll-off
// hand-off, surface-state machine) are built on top of this (CLAUDE.md §9).
describe('App', () => {
  it('renders the landing call to action', () => {
    render(<App />);
    expect(
      screen.getByRole('button', { name: /start learning as a student/i }),
    ).toBeInTheDocument();
  });

  it('shows the brand name', () => {
    render(<App />);
    expect(screen.getByText('WhollyMath')).toBeInTheDocument();
  });
});
