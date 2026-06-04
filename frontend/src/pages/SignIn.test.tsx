import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { SignIn } from './SignIn';

// The sign-in page is a brand-register UI screen (visual testing is the primary check,
// CLAUDE.md §9). These pin its contract with the App flow: it offers the account ways in
// (Google + a free demo, alongside the inline child username/PIN form), and choosing the
// Google/demo path hands off the chosen method to onContinue after the mascot's roll-out.

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('SignIn', () => {
  it('offers both ways to sign in', () => {
    render(<SignIn onContinue={() => undefined} />);
    expect(screen.getByRole('heading', { name: /welcome back/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sign in with google/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /try a free demo/i })).toBeInTheDocument();
  });

  it('the demo choice hands off only after the mascot rolls out', () => {
    vi.useFakeTimers();
    const onContinue = vi.fn();
    render(<SignIn onContinue={onContinue} />);

    fireEvent.click(screen.getByRole('button', { name: /try a free demo/i }));
    expect(onContinue).not.toHaveBeenCalled(); // the roll-out plays first

    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(onContinue).toHaveBeenCalledWith('demo');
  });

  it('passes the google method through on hand-off', () => {
    vi.useFakeTimers();
    const onContinue = vi.fn();
    render(<SignIn onContinue={onContinue} />);

    fireEvent.click(screen.getByRole('button', { name: /sign in with google/i }));
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(onContinue).toHaveBeenCalledWith('google');
  });
});
