// Typed client for the WhollyMath PARENT surface. The parent views read one parent's household
// (several children) and drill into one child's progress — the SAME mastery evidence + named-
// misconception the teacher surface surfaces, reframed in plain-parent language. A child's detail
// reuses the teacher's `TeacherStudentView` shape (a child IS one learner's drill-in), so we import
// those types from `./teacher` rather than redefining them.
//
// This mirrors `teacher.ts` exactly: a `PARENT_API_READY` flag selects between the live `/api/parent/*`
// fetch path (stubbed for later) and the seeded demo household (parentDemo.ts). Both paths exist so
// flipping to real data is a one-line change once a backend + real child logins land.

import {
  addChildInDemo,
  demoChild,
  demoHousehold,
  DEMO_PARENT_NOTES,
  type AddChildInput,
  type ChildSummary,
  type Household,
  type ParentNote,
} from './parentDemo';
// A child's detail is the teacher drill-in shape — reuse it rather than redefine it.
import type { TeacherStudentView as ChildDetail } from './teacher';

import { ApiError } from './index';

// Re-export the parent wire types so the demo data + pages have a stable import surface.
export type { AddChildInput, ChildSummary, Household, ParentNote };
export type { ChildDetail };

// The /api/parent/* endpoints are NOT built yet — the parent surface ships demo-first, mirroring the
// teacher surface's bots-deferred state (see api/teacher.ts, TEACHER_API_READY). Until there is a
// backend that serves a real household, serve the seeded demo household (parentDemo.ts) so the parent
// dashboard renders populated and demoable. The live code paths below stay intact so the flip is a
// one-line change.
//
// TODO(owner, deferred — confirmed 2026-06-02): switch the parent surface off the hardcoded fixtures
// onto REAL data. This needs, in order:
//   1. A backend `/api/parent/*` surface (household + per-child progress), parent auth, and a
//      household → children data model linking a parent to their kids' learner accounts.
//   2. Real LOGINS for those children (the username/password the "Add a child" form collects), so a
//      child's sessions/mastery are genuine and the parent sees real progress.
// Until then we intentionally keep the polished demo fixtures for the pitch.
export const PARENT_API_READY = false;

/* ──────────────────────────────────────────────────────────────────────────
   Client. Both paths exist; `PARENT_API_READY` selects which is live. The live
   base is `/api/parent` (NOT `/parent`) — there is deliberately no `/parent`
   vite proxy, so live calls go through the API prefix and the SPA route `/parent`
   stays a clean client-side deep link.
   ────────────────────────────────────────────────────────────────────────── */

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: parentAuthHeaders() });
  if (!response.ok) {
    throw new ApiError(response.status, `GET ${path} failed (${String(response.status)})`);
  }
  return (await response.json()) as T;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'content-type': 'application/json', ...parentAuthHeaders() },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new ApiError(response.status, `POST ${path} failed (${String(response.status)})`);
  }
  return (await response.json()) as T;
}

// The demo-parent bearer token. Set on parent sign-in. Module-level so the routes authenticate
// without prop-threading, mirroring the teacher `setTeacherToken` (api/teacher.ts).
let parentToken: string | null = null;

/** Set (or clear) the demo-parent bearer token used for /api/parent/* calls. */
export function setParentToken(token: string | null): void {
  parentToken = token;
}

function parentAuthHeaders(): Record<string, string> {
  return parentToken === null ? {} : { authorization: `Bearer ${parentToken}` };
}

/** The one-click demo-parent login handle (mirrors the teacher `DemoLoginResponse` token field). */
export interface ParentLoginResponse {
  email: string;
  role: 'parent';
  token: string;
}

/**
 * One-click demo-parent login. In live mode this would POST `/api/parent/demo-login`; in demo mode
 * (`!PARENT_API_READY`) it short-circuits to a synthetic handle and makes NO network call, so the
 * parent demo signs in and renders the seeded household with or without a backend.
 */
export async function parentDemoLogin(): Promise<ParentLoginResponse> {
  if (!PARENT_API_READY) {
    return Promise.resolve({
      email: 'demo.parent@whollymath.dev',
      role: 'parent',
      token: 'demo:offline',
    });
  }
  return postJson<ParentLoginResponse>('/api/parent/demo-login', {});
}

/** Fetch the signed-in parent's household: their name, the household label, and the child cards. */
export async function fetchHousehold(): Promise<Household> {
  if (!PARENT_API_READY) return Promise.resolve(demoHousehold());
  return getJson<Household>('/api/parent/household');
}

/** Fetch one child's full progress drill-in. 404 if the child is not in this parent's household. */
export async function fetchChild(childId: string): Promise<ChildDetail> {
  if (!PARENT_API_READY) {
    const child = demoChild(childId);
    if (child === null) throw new ApiError(404, `child ${childId} not in household`);
    return Promise.resolve(child);
  }
  return getJson<ChildDetail>(`/api/parent/child/${encodeURIComponent(childId)}`);
}

/** Fetch the parent's seeded notes / "things to ask about" (local-toggle in demo mode). */
export async function fetchParentNotes(): Promise<ParentNote[]> {
  if (!PARENT_API_READY) return Promise.resolve(DEMO_PARENT_NOTES);
  return getJson<ParentNote[]>('/api/parent/notes');
}

/**
 * Add a child to the household. In demo mode this appends to the in-memory household (so the new
 * child appears on the dashboard immediately) and returns the login to share with the child — NO
 * network, NO real account. In live mode this would POST `/api/parent/child` to create a real
 * learner login (see the deferred TODO above).
 */
export async function addChild(
  input: AddChildInput,
): Promise<{ childId: string; username: string }> {
  if (!PARENT_API_READY) return Promise.resolve(addChildInDemo(input));
  return postJson<{ childId: string; username: string }>('/api/parent/child', input);
}
