import { afterEach, describe, expect, it, vi } from 'vitest';

import { startLesson, startSession, submitTurn, type TurnRequest } from './index';

// The Slice 3.6 help-locale threading: start + turn requests carry `locale`, defaulting to 'en'
// so every existing caller (and the English path) is byte-for-byte unchanged. fetch is mocked — we
// assert the BODY we send, not any real server (CLAUDE.md §9).

function mockFetch(): ReturnType<typeof vi.fn> {
  const fn = vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) } as Response),
  );
  vi.stubGlobal('fetch', fn);
  return fn;
}

const TURN: TurnRequest = {
  session_id: 's1',
  problem_id: 'p1',
  action: 'submit_answer',
  submitted_answer: '1/2',
  surface_state: 'S1_symbolic_focus',
  latency_ms: 1000,
  hint_used: false,
};

function bodyOf(fn: ReturnType<typeof vi.fn>): Record<string, unknown> {
  const init = fn.mock.calls[0][1] as RequestInit;
  return JSON.parse(init.body as string) as Record<string, unknown>;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('help-locale threading (Slice 3.6)', () => {
  it('submitTurn defaults to locale "en" when none is passed', async () => {
    const fn = mockFetch();
    await submitTurn(TURN);
    expect(bodyOf(fn).locale).toBe('en');
  });

  it('submitTurn sends "es-MX" when the toggle has picked Spanish', async () => {
    const fn = mockFetch();
    await submitTurn(TURN, 'es-MX');
    expect(bodyOf(fn).locale).toBe('es-MX');
  });

  it('startSession defaults to locale "en"', async () => {
    const fn = mockFetch();
    await startSession('route-key');
    expect(bodyOf(fn).locale).toBe('en');
  });

  it('startSession sends the chosen locale', async () => {
    const fn = mockFetch();
    await startSession('route-key', false, 'es-MX');
    expect(bodyOf(fn).locale).toBe('es-MX');
  });

  it('startLesson defaults to locale "en"', async () => {
    const fn = mockFetch();
    await startLesson('KC_equivalence');
    expect(bodyOf(fn).locale).toBe('en');
  });

  it('startLesson sends the chosen locale', async () => {
    const fn = mockFetch();
    await startLesson('KC_equivalence', false, 'es-MX');
    expect(bodyOf(fn).locale).toBe('es-MX');
  });
});
