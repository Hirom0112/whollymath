import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  TEACHER_API_READY,
  fetchRoster,
  fetchTeacherStudent,
  setTeacherToken,
  type StudentCategory,
} from './teacher';
import { DEMO_ROSTER, assignUnitInDemo, demoStudent } from './teacherDemo';

import { ApiError } from './index';

// Two concerns, post-swap (TCH.B8 landed): (1) the seeded demo fixtures keep the invariants the
// dashboard relies on — they're the offline fallback the real routes are also seeded from (TCH.B9);
// (2) the live client hits the real /teacher/* endpoints with the bearer token and surfaces errors.
// fetch is mocked — we assert the request we send, not a real server (CLAUDE.md §9).

describe('teacher demo fixtures', () => {
  it('the client is wired to the real API (gate landed)', () => {
    expect(TEACHER_API_READY).toBe(true);
  });

  it('roster spans every ranked category so the dashboard can show all three sections', () => {
    const present = new Set<StudentCategory>((DEMO_ROSTER.students ?? []).map((s) => s.category));
    expect(present.has('struggling')).toBe(true);
    expect(present.has('needs_attention')).toBe(true);
    expect(present.has('on_track')).toBe(true);
    expect(DEMO_ROSTER.teacher_name).not.toBe('');
    expect(DEMO_ROSTER.class_name).not.toBe('');
  });

  it('every struggling student carries at least one urgent alert (the ranking invariant)', () => {
    const struggling = (DEMO_ROSTER.students ?? []).filter((s) => s.category === 'struggling');
    expect(struggling.length).toBeGreaterThan(0);
    for (const s of struggling) {
      expect((s.alerts ?? []).some((a) => a.severity === 'urgent')).toBe(true);
    }
  });

  it('drills into a student with the named misconception teachers asked for', () => {
    const maya = demoStudent('stu-maya');
    expect(maya).not.toBeNull();
    expect(maya?.name).toBe('Maya R.');
    expect(maya?.struggle.matched_misconception).toBe('Natural-number bias');
    expect((maya?.strengths ?? []).length + (maya?.weaknesses ?? []).length).toBeGreaterThan(0);
  });

  it('returns null for a student not in the demo class, and assign is idempotent', () => {
    expect(demoStudent('stu-nobody')).toBeNull();
    expect(assignUnitInDemo('stu-nobody', 'u1-ratios-rates')).toBeNull();
    const once = assignUnitInDemo('stu-emma', 'u1-ratios-rates');
    expect(once?.assigned_unit_id).toBe('u1-ratios-rates');
    const twice = assignUnitInDemo('stu-emma', 'u1-ratios-rates');
    expect(twice?.assigned_unit_id).toBe('u1-ratios-rates');
  });
});

describe('teacher live client', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    setTeacherToken(null);
  });

  function mockFetch(payload: unknown, ok = true, status = 200): ReturnType<typeof vi.fn> {
    const fn = vi.fn(() =>
      Promise.resolve({ ok, status, json: () => Promise.resolve(payload) } as Response),
    );
    vi.stubGlobal('fetch', fn);
    return fn;
  }

  it('fetchRoster hits /teacher/roster with the bearer token', async () => {
    const fetchSpy = mockFetch(DEMO_ROSTER);
    setTeacherToken('demo-teacher');
    await fetchRoster();
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/teacher/roster');
    expect((init.headers as Record<string, string>).authorization).toBe('Bearer demo-teacher');
  });

  it('fetchTeacherStudent surfaces a non-2xx as ApiError with the status', async () => {
    mockFetch({}, false, 404);
    await expect(fetchTeacherStudent('stu-nobody')).rejects.toBeInstanceOf(ApiError);
    await expect(fetchTeacherStudent('stu-nobody')).rejects.toMatchObject({ status: 404 });
  });
});
