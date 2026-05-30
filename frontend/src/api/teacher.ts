// Typed client for the WhollyMath TEACHER surface (TODO TCH.F1; teacher dashboard +
// visibility, the #1 priority lane). The teacher views read one teacher's roster and drill
// into one student's mastery evidence + the named misconception we already compute and were
// throwing away (TEACHER_NEEDS.md headline finding).
//
// GATE NOTE (read before editing): the real teacher endpoints + generated TS types are owned by
// lane T1 (TODO DAT.9 regen + TCH.B8 `GET /teacher/roster`, `GET /teacher/student/{id}`,
// `POST /teacher/student/{id}/assign-unit`). Until those land in `@whollymath/shared-types`,
// this module defines the wire shapes LOCALLY and serves the demo class from `teacherDemo.ts`.
// The swap is deliberately one-line: flip `TEACHER_API_READY` to true and replace these local
// interfaces with the generated imports. Both code paths (real fetch + demo) are written now so
// the handoff is a boolean, not a rewrite.

import { DEMO_ROSTER, demoStudent, assignUnitInDemo } from './teacherDemo';

import { ApiError } from './index';

// Flip to true once lane T1 has pushed the regenerated shared types + the /teacher routes
// (TODO DAT.9 + TCH.B8 marked [x]). While false, the client serves the seeded demo class so the
// pages are fully buildable/screenshot-verifiable on mocked data (TODO: build F2/F3 on mocks first).
export const TEACHER_API_READY = false;

/* ──────────────────────────────────────────────────────────────────────────
   Wire shapes (LOCAL until T1's generated types land; see GATE NOTE above).
   ────────────────────────────────────────────────────────────────────────── */

/** Ranking bucket for a student (TODO TCH.B6). Any urgent alert forces `struggling`. */
export type StudentCategory = 'struggling' | 'needs_attention' | 'on_track';

/** Alert severity (TODO TCH.B5). Color is never the sole cue — paired with an icon + word. */
export type AlertSeverity = 'info' | 'warn' | 'urgent';

/** The named, tunable alert rules (TODO TCH.B5). */
export type AlertKind =
  | 'STUCK'
  | 'REPEATED_MISCONCEPTION'
  | 'LOW_ENGAGEMENT'
  | 'FAILING_TREND'
  | 'IDLE'
  | 'REMEDIATION_STUCK';

/** Behavioral HelpNeed direction over the recent window (TODO TCH.B4). */
export type HelpNeedTrend = 'rising' | 'steady' | 'falling';

/** Mastery status for a KC — mirrors the learner course-map vocabulary (CP.A.1). */
export type KcStatus = 'locked' | 'available' | 'in_progress' | 'mastered' | 'due_review';

/** One alert on a student (TODO TCH.B5). `message` is plain-language, templated, NO LLM. */
export interface TeacherAlertView {
  kind: AlertKind;
  severity: AlertSeverity;
  message: string;
}

/** A KC mastery row for the strengths/weaknesses lists (TODO TCH.B3). */
export interface KcMasteryView {
  kc_id: string;
  skill_name: string;
  probability: number; // BKT p(known), 0..1
  status: KcStatus;
}

/** The "what + WHY struggling" summary (TODO TCH.B4) — the diagnostic teachers asked for. */
export interface StruggleSummaryView {
  headline: string; // one-line plain-language summary
  detail: string; // a longer templated explanation a teacher can read aloud
  matched_misconception: string | null; // human label, e.g. "Natural-number bias"
  helpneed_trend: HelpNeedTrend | null;
  recent_error_rate: number | null; // 0..1 over the recent window
}

/** One entry in the recent-activity timeline (TODO TCH.F3 §5). */
export interface ActivityEventView {
  at: string; // human-readable relative time, e.g. "2h ago" (server-rendered)
  label: string; // plain text, e.g. "Answered 3/4 + 1/4 on the number line"
  outcome: 'correct' | 'incorrect' | 'neutral';
}

/** A unit the teacher can assign next (TODO TCH.F3 §6). */
export interface AssignableUnitView {
  unit_id: string;
  title: string;
  available: boolean; // false = prereqs not met (see TCH.Q5 for override policy)
}

/** A roster row — one student summarized for the ranked list (TODO TCH.B3 + B6). */
export interface RosterStudentView {
  student_id: string;
  name: string;
  category: StudentCategory;
  category_reason: string; // one-line reason for the bucket (TODO TCH.B6)
  current_unit_title: string | null;
  current_lesson_title: string | null;
  percent_complete: number; // 0..1 across the assigned course
  alerts: TeacherAlertView[];
}

/** `GET /teacher/roster` response (TODO TCH.B8). */
export interface TeacherRosterView {
  teacher_name: string;
  class_name: string;
  students: RosterStudentView[];
}

/** `GET /teacher/student/{id}` response — the full drill-in (TODO TCH.B8, aggregating B3–B6). */
export interface TeacherStudentView {
  student_id: string;
  name: string;
  category: StudentCategory;
  category_reason: string;
  alerts: TeacherAlertView[];
  struggle: StruggleSummaryView;
  current_unit_title: string | null;
  current_lesson_title: string | null;
  percent_complete: number;
  strengths: KcMasteryView[];
  weaknesses: KcMasteryView[];
  activity: ActivityEventView[];
  assignable_units: AssignableUnitView[];
  assigned_unit_id: string | null;
}

/** `POST /teacher/student/{id}/assign-unit` response (TODO TCH.B7/B8). */
export interface AssignUnitResult {
  student: TeacherStudentView;
}

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
// sign-in; until T1's auth lands it is unused by the demo path. Module-level so the routes
// authenticate without prop-threading, mirroring the learner `setAuthToken` (api/index.ts).
let teacherToken: string | null = null;

/** Set (or clear) the demo-teacher bearer token used for /teacher/* calls (TODO TCH.B2). */
export function setTeacherToken(token: string | null): void {
  teacherToken = token;
}

function teacherAuthHeaders(): Record<string, string> {
  return teacherToken === null ? {} : { authorization: `Bearer ${teacherToken}` };
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
