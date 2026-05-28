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
  StartSessionResponse,
  ThreeArmComparisonView,
  TurnRequest,
  TurnResponse,
} from '@whollymath/shared-types';

export type {
  ActionType,
  ArmVerdictView,
  ErrorCategory,
  InterventionKind,
  InterventionView,
  KnowledgeComponentId,
  MasterySnapshot,
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
    headers: { 'content-type': 'application/json' },
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

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new ApiError(response.status, `GET ${path} failed (${String(response.status)})`);
  }
  return (await response.json()) as T;
}

/**
 * The Slice 5.3 three-arm comparison for the on-screen eval dashboard (PROJECT.md §3.11).
 * Free/deterministic on the server: adaptive + static are computed live, the chat column is
 * the pre-registered prediction until the cost-gated live LLM run.
 */
export async function fetchThreeArmComparison(): Promise<ThreeArmComparisonView> {
  return getJson<ThreeArmComparisonView>('/eval/three-arm-comparison');
}
