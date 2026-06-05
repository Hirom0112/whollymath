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

// LIVE (2026-06-05): the teacher surface now reads REAL data. The two prerequisites that kept this
// on fixtures are met: (1) the TCH.B9 seeder exists and runs idempotently on demo-login
// (`SessionStore.provision_demo_teacher` → `seed_demo_class`), driving six persona bots through the
// real turn loop; (2) those bots ARE the synthetic learners — their sessions/mastery are genuine, so
// the roster/triage/insights reflect real persisted progress. Every /teacher/* endpoint returns the
// UI-complete shape (verified: roster carries as_of/bucket_trends/per-student trend, drill-in carries
// remediation_estimate_minutes/accuracy_history/notes, aggregate-trends carries skill_gap_series).
// DEMO_ROSTER (teacherDemo.ts) is retained only as the offline fallback below.
// (The parent surface still mirrors the old pattern via PARENT_API_READY — see api/parent.ts.)
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
 * One-click demo-teacher login (TCH.B2). In live mode, POSTs `/teacher/demo-login`, which
 * seeds-or-returns the durable demo teacher + its class and mints the NON-secret bearer token
 * ('demo:<id>') the caller sets via `setTeacherToken` so subsequent /teacher/* calls authenticate.
 *
 * In demo mode (`!TEACHER_API_READY`, the bots-deferred state) it short-circuits to a synthetic
 * handle and makes NO network call, so the teacher demo signs in and renders the seeded class with
 * or without a backend.
 */
export async function demoLogin(): Promise<DemoLoginResponse> {
  if (!TEACHER_API_READY) {
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

/** Fetch the class-level aggregate trends for the "Student Insights" card (dashboard upgrade). */
export async function fetchAggregateTrends(): Promise<TeacherAggregateTrends> {
  if (!TEACHER_API_READY) return Promise.resolve(DEMO_AGGREGATE_TRENDS);
  return getJson<TeacherAggregateTrends>('/teacher/aggregate-trends');
}

/** Fetch the signed-in teacher's reminders / to-dos (dashboard upgrade). */
export async function fetchReminders(): Promise<TeacherReminder[]> {
  if (!TEACHER_API_READY) return Promise.resolve(DEMO_REMINDERS);
  return getJson<TeacherReminder[]>('/teacher/reminders');
}
