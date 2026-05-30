import { describe, expect, it } from 'vitest';

import {
  TEACHER_API_READY,
  assignUnit,
  demoLogin,
  fetchRoster,
  fetchTeacherStudent,
  type StudentCategory,
} from './teacher';

import { ApiError } from './index';

// The student bots that seed a real class are deferred (saved to test the lesson plans), so the
// client runs in DEMO mode (TEACHER_API_READY=false): it serves the seeded demo class so the
// dashboard renders a populated roster instead of the empty live one. These tests pin the demo
// path the dashboard relies on + the offline sign-in. (The live /teacher/* path is intact and was
// verified end-to-end manually; it re-activates when the flag flips back to true.)

describe('teacher demo client (bots deferred)', () => {
  it('serves the demo class while the bots are deferred', () => {
    expect(TEACHER_API_READY).toBe(false);
  });

  it('demo-login signs in offline (no backend needed)', async () => {
    const handle = await demoLogin();
    expect(handle.role).toBe('teacher');
    expect(handle.token).not.toBe('');
  });

  it('roster spans every ranked category so the dashboard shows all three sections', async () => {
    const roster = await fetchRoster();
    const present = new Set<StudentCategory>((roster.students ?? []).map((s) => s.category));
    expect(present.has('struggling')).toBe(true);
    expect(present.has('needs_attention')).toBe(true);
    expect(present.has('on_track')).toBe(true);
    expect(roster.teacher_name).not.toBe('');
    expect(roster.class_name).not.toBe('');
  });

  it('every struggling student carries at least one urgent alert (the ranking invariant)', async () => {
    const roster = await fetchRoster();
    const struggling = (roster.students ?? []).filter((s) => s.category === 'struggling');
    expect(struggling.length).toBeGreaterThan(0);
    for (const s of struggling) {
      expect((s.alerts ?? []).some((a) => a.severity === 'urgent')).toBe(true);
    }
  });

  it('drills into a student with the named misconception teachers asked for', async () => {
    const maya = await fetchTeacherStudent('stu-maya');
    expect(maya.name).toBe('Maya R.');
    expect(maya.struggle.matched_misconception).toBe('Natural-number bias');
    expect((maya.strengths ?? []).length + (maya.weaknesses ?? []).length).toBeGreaterThan(0);
  });

  it('404s on a student not in the class (the authorization contract)', async () => {
    await expect(fetchTeacherStudent('stu-nobody')).rejects.toBeInstanceOf(ApiError);
    await expect(fetchTeacherStudent('stu-nobody')).rejects.toMatchObject({ status: 404 });
  });

  it('assign-next-unit is idempotent and reflected on the next read', async () => {
    const updated = await assignUnit('stu-emma', 'u1-ratios-rates');
    expect(updated.assigned_unit_id).toBe('u1-ratios-rates');
    const again = await assignUnit('stu-emma', 'u1-ratios-rates');
    expect(again.assigned_unit_id).toBe('u1-ratios-rates');
    const reread = await fetchTeacherStudent('stu-emma');
    expect(reread.assigned_unit_id).toBe('u1-ratios-rates');
  });

  it('rejects assigning to a student not in the class', async () => {
    await expect(assignUnit('stu-nobody', 'u1-ratios-rates')).rejects.toMatchObject({
      status: 404,
    });
  });
});
