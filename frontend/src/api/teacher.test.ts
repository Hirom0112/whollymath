import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  TEACHER_API_READY,
  assignUnit,
  demoLogin,
  fetchRoster,
  fetchTeacherStudent,
  setTeacherToken,
} from './teacher';

import { ApiError } from './index';

// The teacher surface now runs LIVE (TEACHER_API_READY=true): the client hits the real /teacher/*
// endpoints, which a demo-login idempotently seeds with six persona bots. These tests pin the live
// client WIRING — correct path, method, auth header, response shaping, and 404 mapping — by mocking
// `fetch`. The roster's data quality (categories, alerts, misconceptions) is owned by the backend
// persona/teacher-service tests, not re-asserted here against fixtures.

interface MockResponse {
  status: number;
  body: unknown;
}
type Router = (url: string, method: string) => MockResponse;

function mockFetch(router: Router): ReturnType<typeof vi.fn> {
  const spy = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const method = (init?.method ?? 'GET').toUpperCase();
    const { status, body } = router(String(url), method);
    return {
      ok: status < 400,
      status,
      json: async () => body,
    } as Response;
  });
  vi.stubGlobal('fetch', spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
  setTeacherToken(null);
});

describe('teacher live client', () => {
  it('runs in live mode against the real /teacher endpoints', () => {
    expect(TEACHER_API_READY).toBe(true);
  });

  it('demo-login POSTs /teacher/demo-login and returns the minted handle', async () => {
    const spy = mockFetch((url, method) => {
      if (url.endsWith('/teacher/demo-login') && method === 'POST') {
        return {
          status: 200,
          body: {
            learner_id: 1,
            email: 'demo.teacher@whollymath.dev',
            role: 'teacher',
            token: 'demo:demo-teacher',
          },
        };
      }
      return { status: 404, body: {} };
    });
    const handle = await demoLogin();
    expect(handle.role).toBe('teacher');
    expect(handle.token).toBe('demo:demo-teacher');
    expect(spy).toHaveBeenCalledWith(
      expect.stringContaining('/teacher/demo-login'),
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('fetchRoster GETs /teacher/roster and sends the bearer token', async () => {
    setTeacherToken('demo:demo-teacher');
    const spy = mockFetch((url) => {
      if (url.endsWith('/teacher/roster')) {
        return {
          status: 200,
          body: {
            teacher_name: 'demo.teacher',
            class_name: 'Demo Class',
            as_of: '2026-06-05T00:00:00Z',
            bucket_trends: { struggling: [], needs_attention: [], on_track: [] },
            students: [{ student_id: 'bot-surface-sam', category: 'struggling', trend: [1, 2] }],
          },
        };
      }
      return { status: 404, body: {} };
    });
    const roster = await fetchRoster();
    expect(roster.teacher_name).toBe('demo.teacher');
    expect(roster.students?.[0].student_id).toBe('bot-surface-sam');
    const init = spy.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>).authorization).toBe('Bearer demo:demo-teacher');
  });

  it('fetchTeacherStudent maps a 404 to an ApiError (the authorization contract)', async () => {
    mockFetch(() => ({ status: 404, body: { detail: 'not on roster' } }));
    await expect(fetchTeacherStudent('bot-nobody')).rejects.toBeInstanceOf(ApiError);
    await expect(fetchTeacherStudent('bot-nobody')).rejects.toMatchObject({ status: 404 });
  });

  it('assignUnit POSTs the unit and returns the updated student view', async () => {
    const spy = mockFetch((url, method) => {
      if (url.includes('/assign-unit') && method === 'POST') {
        return {
          status: 200,
          body: { student: { student_id: 'bot-surface-sam', assigned_unit_id: 'u1' } },
        };
      }
      return { status: 404, body: {} };
    });
    const student = await assignUnit('bot-surface-sam', 'u1');
    expect(student.assigned_unit_id).toBe('u1');
    expect(spy).toHaveBeenCalledWith(
      expect.stringContaining('/teacher/student/bot-surface-sam/assign-unit'),
      expect.objectContaining({ method: 'POST' }),
    );
  });
});
