import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { StartSessionResponse, TurnResponse } from '../api';

import { Tutor } from './Tutor';

// These pin the surface's contract with the turn-loop API (src/api): a started
// session renders its problem; a submitted answer shows the verdict + the next
// problem; a hint request surfaces the nudge. `fetch` is mocked so the test stays
// a pure component test (CLAUDE.md §9 — don't reach the real server here).

const SESSION: StartSessionResponse = {
  session_id: 'sess-1',
  surface_state: 'S1_symbolic_focus',
  problem: {
    problem_id: 'CALIB-ADD-1_3+1_4',
    kc: 'KC_addition_unlike',
    surface_format: 'symbolic',
    statement: '1/3 + 1/4 = ?',
  },
};

const CORRECT_TURN: TurnResponse = {
  correct: true,
  error_type: 'none',
  next_surface_state: 'S1_symbolic_focus',
  feedback: 'Correct — nice work.',
  hint: null,
  mastery: [{ kc_id: 'KC_addition_unlike', probability: 0.6, mastered: false }],
  next_problem: {
    problem_id: 'gen-1',
    kc: 'KC_addition_unlike',
    surface_format: 'symbolic',
    statement: '1/2 + 1/5 = ?',
  },
};

const HINT_TURN: TurnResponse = {
  ...CORRECT_TURN,
  correct: false,
  feedback: "Here's something to think about.",
  hint: 'Before you add, are the pieces the same size?',
  mastery: [],
};

function jsonResponse(data: unknown): Response {
  return { ok: true, status: 200, json: () => Promise.resolve(data) } as Response;
}

function mockFetch(): void {
  vi.stubGlobal(
    'fetch',
    vi.fn((_url: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body)) as { action: string };
      return Promise.resolve(
        jsonResponse(body.action === 'request_hint' ? HINT_TURN : CORRECT_TURN),
      );
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('Tutor', () => {
  it('renders the started session problem', () => {
    mockFetch();
    render(<Tutor session={SESSION} />);
    expect(screen.getByRole('heading', { name: /1\/3 \+ 1\/4/i })).toBeInTheDocument();
  });

  it('submitting an answer shows the verdict and a next problem', async () => {
    mockFetch();
    render(<Tutor session={SESSION} />);

    // The calibration problem is symbolic → the stacked fraction editor is shown.
    fireEvent.change(screen.getByLabelText(/numerator/i), { target: { value: '7' } });
    fireEvent.change(screen.getByLabelText(/denominator/i), { target: { value: '12' } });
    fireEvent.click(screen.getByRole('button', { name: /check it/i }));

    expect(await screen.findByText(/correct/i)).toBeInTheDocument();
    const next = screen.getByRole('button', { name: /next problem/i });
    fireEvent.click(next);
    // Advancing mounts the next problem statement returned by the loop.
    expect(screen.getByRole('heading', { name: /1\/2 \+ 1\/5/i })).toBeInTheDocument();
  });

  it('requesting a hint surfaces the nudge without advancing', async () => {
    mockFetch();
    render(<Tutor session={SESSION} />);

    fireEvent.click(screen.getByRole('button', { name: /i'd like a hint/i }));

    expect(await screen.findByRole('note')).toHaveTextContent(/are the pieces the same size/i);
    // Still on the same problem — a hint does not advance.
    expect(screen.getByRole('heading', { name: /1\/3 \+ 1\/4/i })).toBeInTheDocument();
  });
});
