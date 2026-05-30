// Typed client for the WhollyMath turn-loop API (ARCHITECTURE.md §10).
//
// The request/response TYPES come from `@whollymath/shared-types`, which is
// generated from the backend Pydantic schemas (TECH_STACK §2) — one source of
// truth, so the front end cannot drift from the wire contract. This module owns
// only the RUNTIME: the fetch wrappers and the two endpoint calls. Re-export the
// types we use so existing `from '../api'` imports keep a stable surface.
//
// Requests use RELATIVE paths; in dev, Vite proxies them to the FastAPI server
// (vite.config.ts), so the browser sees one origin and there is no CORS to manage.

import type {
  BenchmarkPersonaSummaryView,
  BenchmarkTranscriptView,
  CourseView,
  EventBatchRequest,
  HwAssignResponse,
  HwConfirmAnswer,
  HwStatusResponse,
  HwSubmitResponse,
  InteractionEventIn,
  KnowledgeComponentId,
  MeResponse,
  StartSessionResponse,
  ThreeArmComparisonView,
  TurnRequest,
  TurnResponse,
  UnitDetailView,
  UnitListView,
} from '@whollymath/shared-types';

// The Google ID token for the signed-in learner (Slice PL.3), attached as a Bearer header
// on every request once set. Module-level (not React state) so any caller — the turn loop,
// telemetry, /me — authenticates without threading it through props. null = anonymous, which
// is the default and leaves the v1 session-id flow untouched.
let authToken: string | null = null;

/** Set (or clear, with null) the bearer token used for all subsequent API calls (Slice PL.3). */
export function setAuthToken(token: string | null): void {
  authToken = token;
}

function authHeaders(): Record<string, string> {
  return authToken === null ? {} : { authorization: `Bearer ${authToken}` };
}

export type {
  ActionType,
  AdaptiveTurnView,
  ArmVerdictView,
  BenchmarkPersonaSummaryView,
  BenchmarkTranscriptView,
  ChatTurnView,
  CourseNodeStatus,
  CourseNodeView,
  CourseView,
  ErrorCategory,
  HwAssignResponse,
  HwConfirmAnswer,
  HwDraftItemView,
  HwGradeResultView,
  HwQuestionResultView,
  HwQuestionView,
  HwStatusResponse,
  HwSubmitResponse,
  EventBatchRequest,
  InteractionEventIn,
  InterventionKind,
  InterventionView,
  KnowledgeComponentId,
  LessonView,
  MasterySnapshot,
  MeResponse,
  MetricArmVerdictView,
  MetricComparisonView,
  PersonaComparisonView,
  ProblemView,
  Representation,
  RouteOptionView,
  StartSessionRequest,
  StartSessionResponse,
  StaticTurnView,
  SurfaceState,
  ThreeArmComparisonView,
  TransferProbeStepView,
  TurnRequest,
  TurnResponse,
  UnitDetailView,
  UnitListView,
  UnitStatus,
  UnitView,
} from '@whollymath/shared-types';

/** A non-2xx response from the API, carrying the status for the caller to surface. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'content-type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new ApiError(response.status, `POST ${path} failed (${String(response.status)})`);
  }
  return (await response.json()) as T;
}

/**
 * Start a session from a Turn-0 route choice (decision 0.D.2).
 *
 * `proactiveEnabled` opts the session into the proactive HelpNeed arm (Slice 4.5);
 * default OFF = observe-only (RESEARCH.md §7.5). It is a demo / A/B switch, not a
 * learner-facing control.
 */
export async function startSession(
  routeKey: string,
  proactiveEnabled = false,
): Promise<StartSessionResponse> {
  return postJson<StartSessionResponse>('/session', {
    route_key: routeKey,
    proactive_enabled: proactiveEnabled,
  });
}

/**
 * Start a lesson DIRECTLY for a knowledge component — the course-map node launch (CP.A.2).
 *
 * Unlike `startSession` (a Turn-0 menu route), this begins the lesson for `kc` itself; the
 * server presents a generated first problem in the KC's first live representation. Used so
 * every course-map node can launch its own lesson, including KCs that are not Turn-0 routes.
 */
export async function startLesson(
  kc: KnowledgeComponentId,
  proactiveEnabled = false,
): Promise<StartSessionResponse> {
  return postJson<StartSessionResponse>('/session', { kc, proactive_enabled: proactiveEnabled });
}

/** Submit one learner action (answer or hint request) and get the turn result. */
export async function submitTurn(request: TurnRequest): Promise<TurnResponse> {
  return postJson<TurnResponse>('/turn', request);
}

/**
 * Send a batch of raw behavioral events (Slice PL.2). Fire-and-forget: telemetry must
 * never break the learner's experience, so this NEVER throws — a failed/blocked flush is
 * swallowed (the server endpoint is itself lenient and off the turn loop). Returns true if
 * the batch was accepted, false on any failure, so a caller can decide whether to re-buffer.
 */
export async function postEvents(
  sessionId: string,
  events: InteractionEventIn[],
): Promise<boolean> {
  if (events.length === 0) return true;
  const body: EventBatchRequest = { session_id: sessionId, events };
  try {
    const response = await fetch('/events', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
      keepalive: true, // let an in-flight flush survive a page unload
    });
    return response.ok;
  } catch {
    return false;
  }
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: authHeaders() });
  if (!response.ok) {
    throw new ApiError(response.status, `GET ${path} failed (${String(response.status)})`);
  }
  return (await response.json()) as T;
}

/**
 * Fetch the signed-in learner's persistent identity + carried-forward mastery (Slice PL.3).
 * Requires an auth token (setAuthToken) — the server keys the learner to the Google `sub`,
 * so the same login on any device returns the same state. Throws ApiError(401) if the token
 * is absent/invalid (callers treat that as "stay anonymous").
 */
export async function fetchMe(): Promise<MeResponse> {
  return getJson<MeResponse>('/me');
}

/**
 * Fetch the learner's course map — every KC as a path node with a status (CP.A.1/CP.A.2).
 * A signed-in learner (auth token set) gets it from their persisted mastery; an anonymous demo
 * learner passes their `sessionId` to get it from their in-session progress; a brand-new visitor
 * (neither) gets the fresh default path. The server always returns the full set of nodes.
 */
export async function fetchCourse(sessionId?: string | null): Promise<CourseView> {
  const query =
    sessionId != null && sessionId !== '' ? `?session_id=${encodeURIComponent(sessionId)}` : '';
  return getJson<CourseView>(`/course${query}`);
}

// Shared between /units and /unit/{slug}: an anonymous demo learner passes their session id so
// the list/detail reflects their in-session progress; a signed-in learner (auth token) gets it
// from persisted mastery and the server ignores the session id (units_routes.py).
function sessionQuery(sessionId?: string | null): string {
  return sessionId != null && sessionId !== '' ? `?session_id=${encodeURIComponent(sessionId)}` : '';
}

/**
 * Fetch the learner's units — every catalog unit as a card with status + percent-complete, plus
 * the teacher-assigned unit slug if any (DAT.8/DAT.10). Resolves progress like {@link fetchCourse}:
 * persisted mastery when signed in, the passed `sessionId` for an anonymous demo learner, else the
 * fresh default. The student unit-overview page (STU.3).
 */
export async function fetchUnits(sessionId?: string | null): Promise<UnitListView> {
  return getJson<UnitListView>(`/units${sessionQuery(sessionId)}`);
}

/**
 * Fetch one unit's detail — its lessons in catalog order, each with per-lesson progress (DAT.9).
 * Resolves progress like {@link fetchUnits}. Throws ApiError(404) for a slug not in the catalog,
 * which the unit page surfaces as a gentle "unit not found". The student unit-detail page (STU.4).
 */
export async function fetchUnit(
  slug: string,
  sessionId?: string | null,
): Promise<UnitDetailView> {
  return getJson<UnitDetailView>(`/unit/${encodeURIComponent(slug)}${sessionQuery(sessionId)}`);
}

/**
 * The Slice 5.3 three-arm comparison for the on-screen eval dashboard (PROJECT.md §3.11).
 * Free/deterministic on the server: adaptive + static are computed live, the chat column is
 * the pre-registered prediction until the cost-gated live LLM run.
 */
export async function fetchThreeArmComparison(): Promise<ThreeArmComparisonView> {
  return getJson<ThreeArmComparisonView>('/eval/three-arm-comparison');
}

/**
 * The five adversarial personas for the benchmark-theater switcher (PROJECT.md §4.2).
 * Pure data on the server — who each learner is and the one mastery dimension they attack.
 */
export async function fetchBenchmarkPersonas(): Promise<BenchmarkPersonaSummaryView[]> {
  return getJson<BenchmarkPersonaSummaryView[]>('/eval/benchmark-personas');
}

/**
 * One persona's run through all three arms, turn by turn (a teaching view of Slice 5.3).
 * Deterministic and free on the server — the chat arm uses an offline illustrative provider,
 * so the per-turn tutor wording is a placeholder while the verdict comes from a recorded run.
 */
export async function fetchBenchmarkTranscript(
  personaId: string,
): Promise<BenchmarkTranscriptView> {
  return getJson<BenchmarkTranscriptView>(
    `/eval/benchmark-transcript/${encodeURIComponent(personaId)}`,
  );
}

/* ── Homework scan flow (PROJECT.md §3.4 two-star model) ── */

/** Start a homework run for a skill at lesson end → the upload token (QR payload) + questions. */
export async function hwAssign(
  kc: KnowledgeComponentId,
  sessionId?: string | null,
): Promise<HwAssignResponse> {
  return postJson<HwAssignResponse>('/hw/assign', { kc, session_id: sessionId ?? null });
}

/** Upload the phone's page photos (base64) for a run → transcribe a draft (ready_for_review). */
export async function hwSubmit(token: string, pages: string[]): Promise<HwSubmitResponse> {
  return postJson<HwSubmitResponse>('/hw/submit', { token, pages });
}

/** Poll a run (the desktop, while it waits): state + the read-back draft + the graded verdict. */
export async function hwStatus(token: string): Promise<HwStatusResponse> {
  return getJson<HwStatusResponse>(`/hw/status?token=${encodeURIComponent(token)}`);
}

/** Grade the learner-confirmed answers (after the read-back) → the ★★ verdict. */
export async function hwConfirm(
  token: string,
  answers: HwConfirmAnswer[],
): Promise<HwStatusResponse> {
  return postJson<HwStatusResponse>('/hw/confirm', { token, answers });
}
