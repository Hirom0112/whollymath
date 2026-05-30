// Typed client for the WhollyMath TEACHER surface (TODO TCH.F1; teacher dashboard +
// visibility, the #1 priority lane). The teacher views read one teacher's roster and drill
// into one student's mastery evidence + the named misconception we already compute and were
// throwing away (TEACHER_NEEDS.md headline finding).
//
// The wire types are the GENERATED shared types (single source of truth, regenerated from the
// backend Pydantic schemas — TCH.B8), re-exported here so `teacherDemo.ts` and the teacher pages
// keep importing them from `../api/teacher`. The client hits the real `/teacher/*` endpoints; the
// seeded demo class (teacherDemo.ts) is retained as the offline fallback the routes are seeded
// from (TCH.B9), selectable via `TEACHER_API_READY`.

import type {
  ActivityEventView,
  AlertKind,
  AlertSeverity,
  AssignableUnitView,
  AssignUnitResult,
  DemoLoginResponse,
  HelpNeedTrend,
  KcMasteryView,
  KcStatus,
  RosterStudentView,
  StruggleSummaryView,
  StudentCategory,
  TeacherAlertView,
  TeacherRosterView,
  TeacherStudentView,
} from '@whollymath/shared-types';

import { DEMO_ROSTER, demoStudent, assignUnitInDemo } from './teacherDemo';

import { ApiError } from './index';

// Re-export the generated teacher types so the demo data + pages have a stable import surface.
export type {
  ActivityEventView,
  AlertKind,
  AlertSeverity,
  AssignableUnitView,
  AssignUnitResult,
  DemoLoginResponse,
  HelpNeedTrend,
  KcMasteryView,
  KcStatus,
  RosterStudentView,
  StruggleSummaryView,
  StudentCategory,
  TeacherAlertView,
  TeacherRosterView,
  TeacherStudentView,
};

// The /teacher endpoints + regenerated types have landed (TCH.B8), so the client hits the real
// API. Flip to false to fall back to the seeded demo class (teacherDemo.ts) for offline/storybook.
export const TEACHER_API_READY = true;

/* ──────────────────────────────────────────────────────────────────────────
   Client. Both paths exist; `TEACHER_API_READY` selects which is live.
   ────────────────────────────────────────────────────────────────────────── */

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: teacherAuthHeaders() });
  if (!response.ok) {
    throw new ApiError(response.status, `GET ${path} failed (${String(response.status)})`);
  }
  return (await response.json()) as T;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'content-type': 'application/json', ...teacherAuthHeaders() },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new ApiError(response.status, `POST ${path} failed (${String(response.status)})`);
  }
  return (await response.json()) as T;
}

// The demo-teacher bearer token (TODO TCH.B2 seeds a demo teacher login). Set on teacher
// sign-in. Module-level so the routes authenticate without prop-threading, mirroring the
// learner `setAuthToken` (api/index.ts).
let teacherToken: string | null = null;

/** Set (or clear) the demo-teacher bearer token used for /teacher/* calls (TODO TCH.B2). */
export function setTeacherToken(token: string | null): void {
  teacherToken = token;
}

function teacherAuthHeaders(): Record<string, string> {
  return teacherToken === null ? {} : { authorization: `Bearer ${teacherToken}` };
}

/**
 * One-click demo-teacher login (TCH.B2). POSTs `/teacher/demo-login`, which seeds-or-returns the
 * durable demo teacher + its seeded class and mints the NON-secret bearer token ('demo:<id>').
 * The caller sets the returned token via `setTeacherToken` so subsequent /teacher/* calls
 * authenticate. No auth on this call itself; throws ApiError(503) if the server has no
 * persistence channel (the demo teacher must be a real row to authenticate later).
 */
export async function demoLogin(): Promise<DemoLoginResponse> {
  return postJson<DemoLoginResponse>('/teacher/demo-login', {});
}

/** Fetch the signed-in teacher's roster, students grouped-ready for the ranked list (TCH.B8). */
export async function fetchRoster(): Promise<TeacherRosterView> {
  if (!TEACHER_API_READY) return Promise.resolve(DEMO_ROSTER);
  return getJson<TeacherRosterView>('/teacher/roster');
}

/** Fetch one student's full drill-in. 404 if the student is not on this teacher's roster. */
export async function fetchTeacherStudent(studentId: string): Promise<TeacherStudentView> {
  if (!TEACHER_API_READY) {
    const student = demoStudent(studentId);
    if (student === null) throw new ApiError(404, `student ${studentId} not on roster`);
    return Promise.resolve(student);
  }
  return getJson<TeacherStudentView>(`/teacher/student/${encodeURIComponent(studentId)}`);
}

/** Assign the next unit to a student (TODO TCH.B7). Idempotent; owns-student guarded server-side. */
export async function assignUnit(studentId: string, unitId: string): Promise<TeacherStudentView> {
  if (!TEACHER_API_READY) {
    const student = assignUnitInDemo(studentId, unitId);
    if (student === null) throw new ApiError(404, `student ${studentId} not on roster`);
    return Promise.resolve(student);
  }
  const result = await postJson<AssignUnitResult>(
    `/teacher/student/${encodeURIComponent(studentId)}/assign-unit`,
    { unit_id: unitId },
  );
  return result.student;
}
