import { render, screen } from '@testing-library/react';
import { StrictMode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { StartSessionResponse } from './api';
import { AppRoutes } from './App';
import { SessionProvider } from './state/SessionContext';

// Regression test for the /lesson/:kc start under React StrictMode.
//
// StrictMode mounts → unmounts → remounts every component in dev/build, double-invoking
// effects. The LessonRoute starts the session in an effect guarded by a per-kc ref. An earlier
// implementation also cancelled the in-flight request on cleanup, which — combined with the ref
// guard — left the lesson hung on the loading screen forever (the first request was cancelled and
// the remount was guarded out, so the session was never set). This test renders the lesson route
// inside <StrictMode> and asserts the problem actually appears, locking in the fix.

// vi.hoisted: the mock + fixture must exist before the hoisted vi.mock factory runs.
const { startLessonMock } = vi.hoisted(() => {
  const session: StartSessionResponse = {
    session_id: 'sess-strict-1',
    surface_state: 'S1_symbolic_focus',
    problem: {
      problem_id: 'CALIB-ADD-1_3+1_4',
      kc: 'KC_addition_unlike',
      surface_format: 'symbolic',
      statement: '1/3 + 1/4 = ?',
      widget_id: 'fraction_editor',
    },
  };
  return { startLessonMock: vi.fn(() => Promise.resolve(session)) };
});

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>();
  return { ...actual, startLesson: startLessonMock };
});

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe('LessonRoute under StrictMode', () => {
  it('renders the problem (does not hang on loading) and starts the session once', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })),
    );

    render(
      <StrictMode>
        <SessionProvider proactive={false}>
          <MemoryRouter initialEntries={['/lesson/KC_addition_unlike']}>
            <AppRoutes />
          </MemoryRouter>
        </SessionProvider>
      </StrictMode>,
    );

    // If the StrictMode interaction regressed, this never resolves (stuck on the loading screen).
    expect(await screen.findByRole('heading', { name: /1\/3 \+ 1\/4/i })).toBeInTheDocument();

    // The ref guard means exactly one start despite StrictMode's double mount.
    expect(startLessonMock).toHaveBeenCalledTimes(1);
  });
});
