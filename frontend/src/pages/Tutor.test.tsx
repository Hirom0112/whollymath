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

// A submitted answer whose turn carries a proactive offer for the NEXT problem (the
// §3.7 sustained gate fired). The mascot should voice it unasked on the next problem.
const PROACTIVE_TURN: TurnResponse = {
  ...CORRECT_TURN,
  intervention: {
    kind: 'inline_assertion',
    text: 'Remember to give both fractions the same size pieces first.',
  },
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

  it('requesting a hint surfaces the nudge (mascot speech) without advancing', async () => {
    mockFetch();
    render(<Tutor session={SESSION} />);

    fireEvent.click(screen.getByRole('button', { name: /i'd like a hint/i }));

    expect(await screen.findByRole('note')).toHaveTextContent(/are the pieces the same size/i);
    // Still on the same problem — a hint does not advance.
    expect(screen.getByRole('heading', { name: /1\/3 \+ 1\/4/i })).toBeInTheDocument();
  });

  it('shows no mascot speech on a plain problem with no help', () => {
    mockFetch();
    render(<Tutor session={SESSION} />);
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
  });

  it('voices a proactive offer (unasked) on the next problem', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse(PROACTIVE_TURN))),
    );
    render(<Tutor session={SESSION} />);

    fireEvent.change(screen.getByLabelText(/numerator/i), { target: { value: '7' } });
    fireEvent.change(screen.getByLabelText(/denominator/i), { target: { value: '12' } });
    fireEvent.click(screen.getByRole('button', { name: /check it/i }));

    // No offer while still on the answered problem (it pertains to the next one).
    fireEvent.click(await screen.findByRole('button', { name: /next problem/i }));
    expect(await screen.findByRole('note')).toHaveTextContent(/same size pieces first/i);
  });
});
