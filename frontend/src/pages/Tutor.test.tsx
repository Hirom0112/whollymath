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
    // Required on the wire type (T1, 78b4f85); frontend ignores it for now (B1 / HANDOFF_T3 §2a).
    widget_id: 'fraction_editor',
  },
};

// An expression-answer session (KC_write_expressions, 6.EE.2a): the backend derives
// widget_id "expression" from the EXPRESSION representation, so selectWidget routes it to the
// typed ExpressionInput rather than the fraction editor. Pins that the expression widget is
// wired live end-to-end (the answer string reaches /turn unchanged for SymPy grading).
const EXPR_SESSION: StartSessionResponse = {
  session_id: 'sess-expr',
  surface_state: 'S1_symbolic_focus',
  problem: {
    problem_id: 'gen-expr-1',
    kc: 'KC_write_expressions',
    surface_format: 'expression',
    statement: 'Write an expression for "7 more than p".',
    answer_kind: 'expression',
    widget_id: 'expression',
  },
};

// An inequality-answer session (KC_inequalities, 6.EE.8): the backend derives widget_id
// "inequality" from the INEQUALITY representation, so selectWidget routes it to the structured
// InequalityInput (relation buttons + a boundary field), not the fraction editor. Pins the
// inequality widget is wired live end-to-end (the composed "x>=5" string reaches /turn).
const INEQ_SESSION: StartSessionResponse = {
  session_id: 'sess-ineq',
  surface_state: 'S1_symbolic_focus',
  problem: {
    problem_id: 'gen-ineq-1',
    kc: 'KC_inequalities',
    surface_format: 'inequality',
    statement: 'Write an inequality for "x is at least 5".',
    answer_kind: 'inequality',
    widget_id: 'inequality',
  },
};

// A coordinate-answer session (KC_coordinate_plane, 6.NS.8): the backend derives widget_id
// "coordinate_plane" from the COORDINATE_PLANE representation, so selectWidget routes it to the
// CoordinatePlane plotter, not the fraction editor. Pins the coordinate widget is wired live
// end-to-end (the plotted-point string reaches /turn for point-set grading).
const COORD_SESSION: StartSessionResponse = {
  session_id: 'sess-coord',
  surface_state: 'S1_symbolic_focus',
  problem: {
    problem_id: 'gen-coord-1',
    kc: 'KC_coordinate_plane',
    surface_format: 'coordinate_plane',
    statement: 'Plot the point (0, 0).',
    answer_kind: 'coordinate',
    widget_id: 'coordinate_plane',
  },
};

// A number-set-classification session (KC_classify_number_sets, TEKS 6.2A): the backend derives
// widget_id "classify_sets" from the NUMBER_SETS representation, so selectWidget routes it to the
// ClassifySets widget, not the fraction editor. Pins the classify widget is wired live end-to-end
// (the comma-joined set-label string reaches /turn for set-membership grading).
const SETS_SESSION: StartSessionResponse = {
  session_id: 'sess-sets',
  surface_state: 'S1_symbolic_focus',
  problem: {
    problem_id: 'gen-sets-1',
    kc: 'KC_classify_number_sets',
    surface_format: 'number_sets',
    statement: 'Which sets does 5 belong to?',
    answer_kind: 'number_sets',
    widget_id: 'classify_sets',
  },
};

// A stats session (KC_summary_statistics, 6.SP.3): the problem carries a DISPLAY-ONLY dot-plot
// stimulus visualizing its data set. The answer stays numeric (number_entry); the stimulus is shown
// in the statement area, additive to the prompt text. Pins that the Tutor renders the data visual.
const STATS_SESSION: StartSessionResponse = {
  session_id: 'sess-stats',
  surface_state: 'S1_symbolic_focus',
  problem: {
    problem_id: 'gen-stats-1',
    kc: 'KC_summary_statistics',
    surface_format: 'symbolic',
    statement: 'Find the mean of 4, 4, 5, 6, 9.',
    widget_id: 'number_entry',
    stimulus: {
      kind: 'dot_plot',
      values: [4, 4, 5, 6, 9],
      axis_label: 'Value',
    },
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
    widget_id: 'fraction_editor',
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
    widget_id: 'fraction_editor',
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

  it('renders the typed expression widget and submits the string through /turn', async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse(CORRECT_TURN)));
    vi.stubGlobal('fetch', fetchMock);
    render(<Tutor session={EXPR_SESSION} />);

    // An expression problem routes to ExpressionInput (the free-text algebra field), NOT the
    // numerator/denominator fraction editor.
    expect(screen.queryByLabelText(/numerator/i)).not.toBeInTheDocument();
    const field = screen.getByLabelText(/your expression/i);
    fireEvent.change(field, { target: { value: 'p + 7' } });
    fireEvent.click(screen.getByRole('button', { name: /check it/i }));

    expect(await screen.findByText(/correct/i)).toBeInTheDocument();
    // The typed string reaches /turn unchanged — SymPy grades equivalence server-side (§8.2).
    const calls = fetchMock.mock.calls as unknown as [string, RequestInit?][];
    const turnCall = calls.find((c) => c[0] === '/turn');
    expect(turnCall).toBeDefined();
    const turnBody = JSON.parse(String(turnCall?.[1]?.body)) as Record<string, unknown>;
    expect(turnBody).toMatchObject({ submitted_answer: 'p + 7', action: 'submit_answer' });
  });

  it('renders the inequality widget and submits the composed string through /turn', async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse(CORRECT_TURN)));
    vi.stubGlobal('fetch', fetchMock);
    render(<Tutor session={INEQ_SESSION} />);

    // An inequality problem routes to InequalityInput (relation buttons + a boundary field), NOT
    // the numerator/denominator fraction editor.
    expect(screen.queryByLabelText(/numerator/i)).not.toBeInTheDocument();
    // Pick "≥" then type the boundary 5 → the widget composes "x>=5".
    fireEvent.click(screen.getByRole('radio', { name: /greater than or equal to/i }));
    fireEvent.change(screen.getByLabelText(/boundary number/i), { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: /check it/i }));

    expect(await screen.findByText(/correct/i)).toBeInTheDocument();
    // The composed string reaches /turn unchanged — SymPy grades relational equivalence (§8.2).
    const calls = fetchMock.mock.calls as unknown as [string, RequestInit?][];
    const turnCall = calls.find((c) => c[0] === '/turn');
    expect(turnCall).toBeDefined();
    const turnBody = JSON.parse(String(turnCall?.[1]?.body)) as Record<string, unknown>;
    expect(turnBody).toMatchObject({ submitted_answer: 'x>=5', action: 'submit_answer' });
  });

  it('renders the coordinate-plane widget and submits the plotted point through /turn', async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse(CORRECT_TURN)));
    vi.stubGlobal('fetch', fetchMock);
    render(<Tutor session={COORD_SESSION} />);

    // A coordinate problem routes to CoordinatePlane (the grid plotter), NOT the fraction editor.
    expect(screen.queryByLabelText(/numerator/i)).not.toBeInTheDocument();
    // Place the origin via the keyboard cursor (which starts at (0,0)): focus the grid, press Enter.
    const grid = screen.getByRole('application', { name: /coordinate plane/i });
    fireEvent.focus(grid);
    fireEvent.keyDown(grid, { key: 'Enter' });
    fireEvent.click(screen.getByRole('button', { name: /check it/i }));

    expect(await screen.findByText(/correct/i)).toBeInTheDocument();
    // The plotted-point string reaches /turn unchanged — the backend grades by point-set (§8.2).
    const calls = fetchMock.mock.calls as unknown as [string, RequestInit?][];
    const turnCall = calls.find((c) => c[0] === '/turn');
    expect(turnCall).toBeDefined();
    const turnBody = JSON.parse(String(turnCall?.[1]?.body)) as Record<string, unknown>;
    expect(turnBody).toMatchObject({ submitted_answer: '(0,0)', action: 'submit_answer' });
  });

  it('renders the classify-sets widget and submits the selected sets through /turn', async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse(CORRECT_TURN)));
    vi.stubGlobal('fetch', fetchMock);
    render(<Tutor session={SETS_SESSION} />);

    // A classification problem routes to ClassifySets (the nested set regions), NOT the fraction
    // editor.
    expect(screen.queryByLabelText(/numerator/i)).not.toBeInTheDocument();
    // 5 is a whole number → it belongs to all three nested sets. Toggle each region on.
    fireEvent.click(screen.getByRole('checkbox', { name: /^whole$/i }));
    fireEvent.click(screen.getByRole('checkbox', { name: /^integers$/i }));
    fireEvent.click(screen.getByRole('checkbox', { name: /^rational$/i }));
    fireEvent.click(screen.getByRole('button', { name: /check it/i }));

    expect(await screen.findByText(/correct/i)).toBeInTheDocument();
    // The canonical (small→large) comma-joined string reaches /turn — graded by set membership (§8.2).
    const calls = fetchMock.mock.calls as unknown as [string, RequestInit?][];
    const turnCall = calls.find((c) => c[0] === '/turn');
    expect(turnCall).toBeDefined();
    const turnBody = JSON.parse(String(turnCall?.[1]?.body)) as Record<string, unknown>;
    expect(turnBody).toMatchObject({
      submitted_answer: 'whole,integer,rational',
      action: 'submit_answer',
    });
  });

  it('renders the display-only stats stimulus in the statement area for a stats problem', () => {
    mockFetch();
    render(<Tutor session={STATS_SESSION} />);

    // The dot plot is drawn (5 data points → 5 dots), additive to the prompt text which still shows.
    expect(screen.getByText(/find the mean of 4, 4, 5, 6, 9/i)).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /dot plot/i })).toBeInTheDocument();
  });

  it('shows no stats stimulus on a non-stats problem', () => {
    mockFetch();
    render(<Tutor session={SESSION} />);
    expect(screen.queryByRole('img', { name: /dot plot|histogram/i })).not.toBeInTheDocument();
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
