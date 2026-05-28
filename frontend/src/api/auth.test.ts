import { afterEach, describe, expect, it, vi } from 'vitest';

import { fetchMe, setAuthToken, submitTurn, type TurnRequest } from './index';

// The bearer-token threading (Slice PL.3): once setAuthToken is set, every request carries
// `Authorization: Bearer <token>`; cleared, requests are anonymous (the v1 default). fetch is
// mocked — we assert the header we send, not any real server (CLAUDE.md §9).

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

afterEach(() => {
  vi.unstubAllGlobals();
  setAuthToken(null); // don't leak the token across tests
});

function headersOf(fn: ReturnType<typeof vi.fn>): Record<string, string> {
  return ((fn.mock.calls[0][1] as RequestInit).headers ?? {}) as Record<string, string>;
}

describe('auth token threading', () => {
  it('omits the Authorization header when no token is set (anonymous default)', async () => {
    const fn = mockFetch();
    await submitTurn(TURN);
    expect(headersOf(fn).authorization).toBeUndefined();
  });

  it('attaches a Bearer header to a POST once a token is set', async () => {
    const fn = mockFetch();
    setAuthToken('id-token-abc');
    await submitTurn(TURN);
    expect(headersOf(fn).authorization).toBe('Bearer id-token-abc');
  });

  it('attaches a Bearer header to a GET (fetchMe)', async () => {
    const fn = mockFetch();
    setAuthToken('id-token-xyz');
    await fetchMe();
    expect(fn.mock.calls[0][0]).toBe('/me');
    expect(headersOf(fn).authorization).toBe('Bearer id-token-xyz');
  });

  it('clears the token back to anonymous', async () => {
    const fn = mockFetch();
    setAuthToken('tok');
    setAuthToken(null);
    await submitTurn(TURN);
    expect(headersOf(fn).authorization).toBeUndefined();
  });
});
