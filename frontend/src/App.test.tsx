import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { App } from './App';

// Smoke test: proves the toolchain (vitest + RTL + jsdom) is wired and green.
// Real component/state-machine tests are built on top of this (CLAUDE.md §9).
describe('App', () => {
  it('renders the app title', () => {
    render(<App />);
    expect(screen.getByRole('heading', { name: 'WhollyMath' })).toBeInTheDocument();
  });
});
