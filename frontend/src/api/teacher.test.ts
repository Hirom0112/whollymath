import { describe, expect, it } from 'vitest';

import {
  assignUnit,
  fetchRoster,
  fetchTeacherStudent,
  TEACHER_API_READY,
  type StudentCategory,
} from './teacher';

import { ApiError } from './index';

// The teacher client serves the seeded demo class while `TEACHER_API_READY` is false (the gate
// before lane T1's /teacher endpoints land). These tests pin the demo invariants the dashboard
// relies on, and the client contract that survives the swap (404 on a foreign student, idempotent
// assign). No real server — the demo path is deterministic (CLAUDE.md §9).

describe('teacher demo client (pre-gate)', () => {
  it('serves the demo class until the real API is wired', () => {
    // A guard so the swap to T1's endpoints is a deliberate flip, not an accident.
    expect(TEACHER_API_READY).toBe(false);
  });

  it('roster spans every ranked category so the dashboard can show all three sections', async () => {
    const roster = await fetchRoster();
    const present = new Set<StudentCategory>(roster.students.map((s) => s.category));
    expect(present.has('struggling')).toBe(true);
    expect(present.has('needs_attention')).toBe(true);
    expect(present.has('on_track')).toBe(true);
    expect(roster.teacher_name).not.toBe('');
    expect(roster.class_name).not.toBe('');
  });

  it('every struggling student carries at least one urgent alert (the ranking invariant)', async () => {
    const roster = await fetchRoster();
    const struggling = roster.students.filter((s) => s.category === 'struggling');
    expect(struggling.length).toBeGreaterThan(0);
    for (const s of struggling) {
      expect(s.alerts.some((a) => a.severity === 'urgent')).toBe(true);
    }
  });

  it('drills into a student with the named misconception teachers asked for', async () => {
    const maya = await fetchTeacherStudent('stu-maya');
    expect(maya.name).toBe('Maya R.');
    expect(maya.struggle.matched_misconception).toBe('Natural-number bias');
    expect(maya.strengths.length + maya.weaknesses.length).toBeGreaterThan(0);
  });

  it('404s on a student not on the roster (the authorization contract)', async () => {
    await expect(fetchTeacherStudent('stu-nobody')).rejects.toBeInstanceOf(ApiError);
    await expect(fetchTeacherStudent('stu-nobody')).rejects.toMatchObject({ status: 404 });
  });

  it('assign-next-unit is idempotent and reflected on the next read', async () => {
    const updated = await assignUnit('stu-emma', 'u1-ratios-rates');
    expect(updated.assigned_unit_id).toBe('u1-ratios-rates');
    // Re-assigning the same unit is a no-op on the result; the read reflects it.
    const again = await assignUnit('stu-emma', 'u1-ratios-rates');
    expect(again.assigned_unit_id).toBe('u1-ratios-rates');
    const reread = await fetchTeacherStudent('stu-emma');
    expect(reread.assigned_unit_id).toBe('u1-ratios-rates');
  });

  it('rejects assigning to a foreign student', async () => {
    await expect(assignUnit('stu-nobody', 'u1-ratios-rates')).rejects.toMatchObject({
      status: 404,
    });
  });
});
