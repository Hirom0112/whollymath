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
  EventBatchRequest,
  InteractionEventIn,
  MeResponse,
  StartSessionResponse,
  ThreeArmComparisonView,
  TurnRequest,
  TurnResponse,
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
  ArmVerdictView,
  ErrorCategory,
  EventBatchRequest,
  InteractionEventIn,
  InterventionKind,
  InterventionView,
  KnowledgeComponentId,
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
  SurfaceState,
  ThreeArmComparisonView,
  TurnRequest,
  TurnResponse,
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
 * The Slice 5.3 three-arm comparison for the on-screen eval dashboard (PROJECT.md §3.11).
 * Free/deterministic on the server: adaptive + static are computed live, the chat column is
 * the pre-registered prediction until the cost-gated live LLM run.
 */
export async function fetchThreeArmComparison(): Promise<ThreeArmComparisonView> {
  return getJson<ThreeArmComparisonView>('/eval/three-arm-comparison');
}
