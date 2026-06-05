// Typed client for the WhollyMath PARENT surface. The parent views read one parent's household
// (several children) and drill into one child's progress — the SAME mastery evidence + named-
// misconception the teacher surface surfaces, reframed in plain-parent language. A child's detail
// reuses the teacher's `TeacherStudentView` shape (a child IS one learner's drill-in), so we import
// those types from `./teacher` rather than redefining them.
//
// This mirrors `teacher.ts` exactly: a `PARENT_API_READY` flag selects between the live `/api/parent/*`
// fetch path (stubbed for later) and the seeded demo household (parentDemo.ts). Both paths exist so
// flipping to real data is a one-line change once a backend + real child logins land.

import { createChild, getJson, listChildren, parentMe, type ChildAccount } from './parentAuth';
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

// Parent auth + child accounts are now LIVE (see api/parentAuth.ts): signup/login set a cookie
// session, and a child is a real account (display_name + grade + locale + username + PIN). So the
// HOUSEHOLD ROSTER (`fetchHousehold`) and ADD-A-CHILD (`addChild`) now read/write the real
// `/parent/*` backend.
//
// What the auth backend does NOT yet serve is per-child PROGRESS (mastery category, accuracy trend,
// current lesson, percent-complete) — that's a separate data model. So a real child maps into the
// dashboard's richer `ChildSummary` as an honest "just getting started" card (no fabricated
// progress), and per-child DRILL-IN (`fetchChild`) + the parent NOTES card still come from the
// authored demo fixtures, which is where the polished progress story lives for the pitch.
//
// `PARENT_API_READY` keeps the seeded-demo escape hatch: set true (default) for the real roster +
// real add-child; set false to fall back to the fully-seeded demo household offline.
export const PARENT_API_READY = true;

/* ──────────────────────────────────────────────────────────────────────────
   Client. The household ROSTER + ADD-A-CHILD go through the real cookie-session
   `/parent/*` backend (api/parentAuth.ts); per-child DRILL-IN + NOTES stay on the
   authored demo fixtures (no backend progress yet). `PARENT_API_READY` (default
   true) toggles the roster between real and the fully-seeded demo household.
   ────────────────────────────────────────────────────────────────────────── */

// Derive a friendly household label + parent first-name from the parent's email local-part, since
// the auth backend keys the account by email and carries no separate display name yet.
function nameFromEmail(email: string): string {
  const local = email.split('@')[0] ?? email;
  const word = local.split(/[._-]+/)[0] || local;
  return word.charAt(0).toUpperCase() + word.slice(1);
}

// Map a real child ACCOUNT (api/parentAuth.ChildAccount) into the dashboard's richer ChildSummary.
// The auth backend serves identity (name/grade/locale) but NOT progress, so this is an honest
// "just added — no practice yet" card: needs_attention category, a flat trend, 0% complete. This
// keeps the dashboard's shape intact (per CLAUDE.md §7: adapt in the API layer, don't rewrite the
// page) while never fabricating progress the backend hasn't measured.
function summaryFromAccount(account: ChildAccount): ChildSummary {
  return {
    child_id: account.public_id,
    name: account.display_name,
    grade: account.grade_level,
    category: 'needs_attention',
    status_line: 'Just added — ask them to sign in and start their first lesson.',
    current_unit_title: null,
    current_lesson_title: null,
    percent_complete: 0,
    practiced_today: false,
    trend: [],
  };
}

// Build a roster card from a child's REAL progress drill-in, so the household roster reflects the
// same live data as the per-child view (no "just added" placeholder for a child who has practiced).
// Falls back to the identity-only card if the progress read fails for one child, so a single bad
// read never breaks the whole roster. Scales line up: percent_complete is 0..1 and accuracy_history
// is the 0..100 sparkline series on both the drill-in and the ChildSummary card.
async function childSummaryFromProgress(account: ChildAccount): Promise<ChildSummary> {
  try {
    const d = await fetchChild(account.public_id);
    return {
      child_id: account.public_id,
      name: account.display_name,
      grade: account.grade_level,
      category: d.category,
      status_line: d.category_reason,
      current_unit_title: d.current_unit_title ?? null,
      current_lesson_title: d.current_lesson_title ?? null,
      percent_complete: d.percent_complete,
      practiced_today: (d.accuracy_history?.length ?? 0) > 0,
      trend: d.accuracy_history ?? [],
    };
  } catch {
    return summaryFromAccount(account);
  }
}

/** Fetch the signed-in parent's household: their name, the household label, and the child cards. */
export async function fetchHousehold(): Promise<Household> {
  if (!PARENT_API_READY) return demoHousehold();
  const [me, accounts] = await Promise.all([parentMe(), listChildren()]);
  const first = nameFromEmail(me.email);
  // Each card is built from the child's live progress drill-in (one read per child), so the roster
  // and the per-child view never disagree. A child with no practice yet returns an honest
  // just-getting-started view from the same code path.
  const children = await Promise.all(accounts.map(childSummaryFromProgress));
  return {
    parent_name: first,
    household_label: `The ${first} Family`,
    children,
  };
}

/** Fetch one child's full progress drill-in from the live, parent-owned endpoint (BOLA-scoped
 *  server-side). 404 if the child is not this parent's. In offline demo mode (`!PARENT_API_READY`)
 *  it serves the authored fixtures instead. */
export async function fetchChild(childId: string): Promise<ChildDetail> {
  if (!PARENT_API_READY) {
    const child = demoChild(childId);
    if (child === null) throw new ApiError(404, `child ${childId} has no progress detail yet`);
    return child;
  }
  return getJson<ChildDetail>(`/parent/children/${encodeURIComponent(childId)}/progress`);
}

/** Fetch the parent's seeded notes / "things to ask about" (authored fixtures; local-toggle). */
export async function fetchParentNotes(): Promise<ParentNote[]> {
  return Promise.resolve(DEMO_PARENT_NOTES);
}

/**
 * Add a child to the household. In real mode (`PARENT_API_READY`) this POSTs the live
 * `/parent/children` endpoint (cookie session + CSRF, via parentAuth.createChild), creating a real
 * child account with a username + PIN the child uses to sign in, and returns the login to share. In
 * demo mode it appends to the in-memory household instead (no network, no real account).
 *
 * The live path needs the child's locale + 4-digit PIN, which the legacy `AddChildInput` doesn't
 * carry, so callers pass the richer `AddChildLive` shape; demo mode reads the overlapping fields.
 */
export interface AddChildLive {
  name: string;
  grade: number;
  locale: 'en' | 'es-MX';
  username: string;
  pin: string;
}

export async function addChild(
  input: AddChildLive,
): Promise<{ childId: string; username: string }> {
  if (!PARENT_API_READY) {
    const demoInput: AddChildInput = {
      name: input.name,
      grade: input.grade,
      username: input.username,
    };
    return Promise.resolve(addChildInDemo(demoInput));
  }
  const created = await createChild({
    display_name: input.name,
    grade_level: input.grade,
    locale: input.locale,
    username: input.username,
    pin: input.pin,
  });
  return { childId: created.public_id, username: created.username };
}
