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
  AssignUnitResult as GeneratedAssignUnitResult,
  DemoLoginResponse,
  HelpNeedTrend,
  KcMasteryView,
  KcStatus,
  RosterStudentView as GeneratedRosterStudentView,
  StruggleSummaryView,
  StudentCategory,
  TeacherAlertView,
  TeacherRosterView as GeneratedTeacherRosterView,
  TeacherStudentView as GeneratedTeacherStudentView,
} from '@whollymath/shared-types';

import {
  DEMO_ROSTER,
  DEMO_AGGREGATE_TRENDS,
  DEMO_REMINDERS,
  demoStudent,
  assignUnitInDemo,
} from './teacherDemo';

import { ApiError } from './index';

// Re-export the generated teacher types so the demo data + pages have a stable import surface.
export type {
  ActivityEventView,
  AlertKind,
  AlertSeverity,
  AssignableUnitView,
  DemoLoginResponse,
  HelpNeedTrend,
  KcMasteryView,
  KcStatus,
  StruggleSummaryView,
  StudentCategory,
  TeacherAlertView,
};

/* ──────────────────────────────────────────────────────────────────────────
   Trend / insight fields (dashboard-upgrade lane). These extend the generated
   wire types with the trend series + insight fields the upgraded dashboard
   renders. They MIRROR a backend contract being built in parallel — when the
   Pydantic schemas regenerate `shared-types`, these extensions become no-ops
   (the generated types will already carry the fields) and can be removed. Names
   and types here are the contract: keep them exact.
   ────────────────────────────────────────────────────────────────────────── */

/** Per-bucket 12-point trend series for the status-strip sparklines (TCH dashboard upgrade). */
export interface BucketTrends {
  struggling: number[];
  needs_attention: number[];
  on_track: number[];
}

/** Roster row + its per-student sparkline series (oldest → newest). */
export type RosterStudentView = GeneratedRosterStudentView & {
  trend: number[];
};

/** Roster view + the dashboard-upgrade trend header. `students` carries the extended row. */
export type TeacherRosterView = Omit<GeneratedTeacherRosterView, 'students'> & {
  students?: RosterStudentView[];
  /** ISO-8601 timestamp the roster + trends were computed. */
  as_of: string;
  bucket_trends: BucketTrends;
};

/** Student drill-in + the insight fields the upgraded detail panel renders. */
export type TeacherStudentView = GeneratedTeacherStudentView & {
  /** Estimated minutes to clear the current gap, or null when not estimable. */
  remediation_estimate_minutes: number | null;
  /** Per-session accuracy history (0..1), oldest → newest, for the detail sparkline. */
  accuracy_history: number[];
  /** Free-text teacher notes, or null. */
  notes: string | null;
};

/** `assign-unit` result, carrying the extended student view. */
export type AssignUnitResult = Omit<GeneratedAssignUnitResult, 'student'> & {
  student: TeacherStudentView;
};

/** A single teacher to-do on the dashboard (TCH dashboard upgrade). */
export interface TeacherReminder {
  id: string;
  text: string;
  done: boolean;
}

/** Class-level aggregate series for the "Student Insights" card. */
export interface TeacherAggregateTrends {
  /** 14-point class skill-gap series (oldest → newest) for the AreaChart. */
  skill_gap_series: number[];
}

// The `/teacher/*` endpoints are real and UI-complete (roster carries as_of/bucket_trends/per-student
// trend, drill-in carries remediation_estimate_minutes/accuracy_history/notes, aggregate-trends
// carries skill_gap_series). BUT the demo teacher's CLASS is empty: the TCH.B9 class seeder was never
// built (backend `provision_demo_teacher` creates only the teacher row, no students), so the live
// dashboard has nothing to show. Until that seeder lands, the demo button uses the runtime bypass
// (`setTeacherDemoMode`) to serve the polished seeded class from teacherDemo.ts. `TEACHER_API_READY`
// stays true so a real signed-in teacher with a real (seeded) class would read live data.
export const TEACHER_API_READY = true;

// Runtime demo bypass for the TEACHER surface (the "Continue as a demo teacher" button). The live
// `/teacher/*` backend authenticates a demo teacher, but its class has no seeded students (the
// TCH.B9 class seeder was never built — provision_demo_teacher only creates the teacher row), so the
// real dashboard is EMPTY. For the pitch we want a populated class, so clicking the demo button
// flips this flag and the whole teacher API layer serves the polished, deterministic seeded class
// (teacherDemo.ts) — exactly the runtime-bypass pattern api/parent.ts uses. Cleared on sign-out.
let teacherDemoMode = false;

/** Turn the teacher demo bypass on/off. Set true by the sign-in gate's demo button; false on exit. */
export function setTeacherDemoMode(on: boolean): void {
  teacherDemoMode = on;
}

/** Whether the teacher surface is serving the seeded demo class (explicit bypass OR API not ready). */
export function isTeacherDemo(): boolean {
  return teacherDemoMode || !TEACHER_API_READY;
}

/* ──────────────────────────────────────────────────────────────────────────
   Client. Both paths exist; `isTeacherDemo()` selects which is live.
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
 * One-click demo-teacher login (TCH.B2). In live mode, POSTs `/teacher/demo-login`, which
 * seeds-or-returns the durable demo teacher + its class and mints the NON-secret bearer token
 * ('demo:<id>') the caller sets via `setTeacherToken` so subsequent /teacher/* calls authenticate.
 *
 * In demo mode (`!TEACHER_API_READY`, the bots-deferred state) it short-circuits to a synthetic
 * handle and makes NO network call, so the teacher demo signs in and renders the seeded class with
 * or without a backend.
 */
export async function demoLogin(): Promise<DemoLoginResponse> {
  if (isTeacherDemo()) {
    return Promise.resolve({
      learner_id: 0,
      email: 'demo.teacher@whollymath.dev',
      role: 'teacher',
      token: 'demo:offline',
    });
  }
  return postJson<DemoLoginResponse>('/teacher/demo-login', {});
}

/** Fetch the signed-in teacher's roster, students grouped-ready for the ranked list (TCH.B8). */
export async function fetchRoster(): Promise<TeacherRosterView> {
  if (isTeacherDemo()) return Promise.resolve(DEMO_ROSTER);
  return getJson<TeacherRosterView>('/teacher/roster');
}

/** Fetch one student's full drill-in. 404 if the student is not on this teacher's roster. */
export async function fetchTeacherStudent(studentId: string): Promise<TeacherStudentView> {
  if (isTeacherDemo()) {
    const student = demoStudent(studentId);
    if (student === null) throw new ApiError(404, `student ${studentId} not on roster`);
    return Promise.resolve(student);
  }
  return getJson<TeacherStudentView>(`/teacher/student/${encodeURIComponent(studentId)}`);
}

/** Assign the next unit to a student (TODO TCH.B7). Idempotent; owns-student guarded server-side. */
export async function assignUnit(studentId: string, unitId: string): Promise<TeacherStudentView> {
  if (isTeacherDemo()) {
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

/** Fetch the class-level aggregate trends for the "Student Insights" card (dashboard upgrade). */
export async function fetchAggregateTrends(): Promise<TeacherAggregateTrends> {
  if (isTeacherDemo()) return Promise.resolve(DEMO_AGGREGATE_TRENDS);
  return getJson<TeacherAggregateTrends>('/teacher/aggregate-trends');
}

/** Fetch the signed-in teacher's reminders / to-dos (dashboard upgrade). */
export async function fetchReminders(): Promise<TeacherReminder[]> {
  if (isTeacherDemo()) return Promise.resolve(DEMO_REMINDERS);
  return getJson<TeacherReminder[]>('/teacher/reminders');
}
