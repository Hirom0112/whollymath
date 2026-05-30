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

// A wrong answer whose transition lands in S4 and carries the worked example (the
// backend serves the solved steps of the problem just missed; §3.5).
const S4_TURN: TurnResponse = {
  correct: false,
  error_type: 'operation',
  next_surface_state: 'S4_worked_example',
  feedback: "Let's take it step by step.",
  hint: null,
  mastery: [],
  worked_example: [
    {
      shown: 'Find a common denominator for 1/3 and 1/4: the smallest is 12.',
      why_prompt: 'Why do the pieces have to be the same size before we combine them?',
    },
    {
      shown: 'Rewrite each fraction with 12 on the bottom: 1/3 = 4/12, 1/4 = 3/12.',
      why_prompt: 'Why does renaming a fraction this way not change how much it is?',
    },
  ],
  next_problem: {
    problem_id: 'gen-9',
    kc: 'KC_addition_unlike',
    surface_format: 'symbolic',
    statement: '2/5 + 1/3 = ?',
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

  it('reveals the S4 worked example one step at a time, each with its why-prompt', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse(S4_TURN))),
    );
    render(<Tutor session={SESSION} />);

    fireEvent.change(screen.getByLabelText(/numerator/i), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText(/denominator/i), { target: { value: '7' } });
    fireEvent.click(screen.getByRole('button', { name: /check it/i }));

    // First step + its why-prompt are shown; the second is hidden until asked for.
    expect(await screen.findByText(/the smallest is 12/i)).toBeInTheDocument();
    expect(screen.getByText(/have to be the same size/i)).toBeInTheDocument();
    expect(screen.queryByText(/1\/3 = 4\/12/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /show me the next step/i }));
    expect(screen.getByText(/1\/3 = 4\/12/i)).toBeInTheDocument();
  });

  it('preserves the previous problem and answer in a previous-work panel', async () => {
    mockFetch();
    render(<Tutor session={SESSION} />);

    fireEvent.change(screen.getByLabelText(/numerator/i), { target: { value: '7' } });
    fireEvent.change(screen.getByLabelText(/denominator/i), { target: { value: '12' } });
    fireEvent.click(screen.getByRole('button', { name: /check it/i }));
    fireEvent.click(await screen.findByRole('button', { name: /next problem/i }));

    // The panel echoes the problem we just left and the answer given (refuse-rule 2).
    const panel = screen.getByLabelText(/your previous answer/i);
    expect(panel).toHaveTextContent(/1\/3 \+ 1\/4/);
    expect(panel).toHaveTextContent(/7\/12/);
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

  it('shows the live-adaptation reason banner with a dismiss when the loop adapts (HR.B5)', async () => {
    const adaptTurn: TurnResponse = {
      ...CORRECT_TURN,
      adaptation: {
        state: 'confused',
        reason: 'Switching to the number line so you can see the size.',
        is_morph: true,
      },
    };
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse(adaptTurn))),
    );
    render(<Tutor session={SESSION} />);

    fireEvent.change(screen.getByLabelText(/numerator/i), { target: { value: '7' } });
    fireEvent.change(screen.getByLabelText(/denominator/i), { target: { value: '12' } });
    fireEvent.click(screen.getByRole('button', { name: /check it/i }));
    // The adaptation rides onto the NEXT problem (the morphed surface), not the answered one.
    fireEvent.click(await screen.findByRole('button', { name: /next problem/i }));

    const banner = await screen.findByRole('status');
    expect(banner).toHaveTextContent(/number line so you can see the size/i);
    // Agency: a non-fluent state offers a plain acknowledge; dismissing removes the banner.
    fireEvent.click(screen.getByRole('button', { name: /got it/i }));
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('lets a fluent-ready learner decline the implied skip ("Keep practicing")', async () => {
    const adaptTurn: TurnResponse = {
      ...CORRECT_TURN,
      adaptation: {
        state: 'fluent_ready',
        reason: "You're flying — want to keep going at this level?",
        is_morph: false,
      },
    };
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse(adaptTurn))),
    );
    render(<Tutor session={SESSION} />);

    fireEvent.change(screen.getByLabelText(/numerator/i), { target: { value: '7' } });
    fireEvent.change(screen.getByLabelText(/denominator/i), { target: { value: '12' } });
    fireEvent.click(screen.getByRole('button', { name: /check it/i }));
    fireEvent.click(await screen.findByRole('button', { name: /next problem/i }));

    expect(await screen.findByRole('status')).toHaveTextContent(/want to keep going/i);
    expect(screen.getByRole('button', { name: /keep practicing/i })).toBeInTheDocument();
  });

  it('affirms WHY a correct answer worked (explain-after-correct, Beat 2)', async () => {
    const explainTurn: TurnResponse = {
      ...CORRECT_TURN,
      explanation: [
        {
          shown: '1/3 = 4/12 and 1/4 = 3/12, so 1/3 + 1/4 = 7/12.',
          why_prompt: 'Same-size twelfths let us add the tops.',
        },
      ],
    };
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse(explainTurn))),
    );
    render(<Tutor session={SESSION} />);

    fireEvent.change(screen.getByLabelText(/numerator/i), { target: { value: '7' } });
    fireEvent.change(screen.getByLabelText(/denominator/i), { target: { value: '12' } });
    fireEvent.click(screen.getByRole('button', { name: /check it/i }));

    // On the correct verdict, the "here's why" affirmation + its step show before advancing.
    expect(await screen.findByLabelText(/why that works/i)).toBeInTheDocument();
    expect(screen.getByText(/here.s why that works/i)).toBeInTheDocument();
    expect(screen.getByText(/same-size twelfths let us add the tops/i)).toBeInTheDocument();
  });
});
