// Typed client for the WhollyMath turn-loop API (ARCHITECTURE.md §10).
//
// These types MIRROR the backend Pydantic schemas (backend/app/api/schemas.py).
// They are hand-written for now and are the single front-end source of truth until
// the Pydantic→TS generation (TODO 0.4.1 / 1.9.3) replaces this block with the
// generated file. Keep them byte-aligned with the backend enum values: a drift here
// is a silent contract break (CLAUDE.md §6 — no `any`, the contract is the point).
//
// Requests use RELATIVE paths; in dev, Vite proxies them to the FastAPI server
// (vite.config.ts), so the browser sees one origin and there is no CORS to manage.

export type SurfaceState =
  | 'S1_symbolic_focus'
  | 'S2_number_line_primary'
  | 'S3_fraction_bars_primary'
  | 'S4_worked_example'
  | 'S5_transfer_probe';

export type ErrorType = 'none' | 'magnitude' | 'operation' | 'format' | 'other';

export type ActionType = 'submit_answer' | 'request_hint';

export type KnowledgeComponentId =
  | 'KC_equivalence'
  | 'KC_common_denominator'
  | 'KC_addition_unlike'
  | 'KC_subtraction_unlike'
  | 'KC_number_line_placement';

export type Representation = 'symbolic' | 'area_model' | 'number_line' | 'word_problem';

export interface ProblemView {
  problem_id: string;
  kc: KnowledgeComponentId;
  surface_format: Representation;
  statement: string;
}

export interface RouteOptionView {
  key: string;
  prompt: string;
  is_unsure_default: boolean;
}

export interface StartSessionResponse {
  session_id: string;
  surface_state: SurfaceState;
  problem: ProblemView;
}

export interface MasterySnapshot {
  kc_id: KnowledgeComponentId;
  probability: number;
  mastered: boolean;
}

export interface TurnRequest {
  session_id: string;
  problem_id: string;
  action: ActionType;
  submitted_answer?: string | null;
  surface_state: SurfaceState;
  latency_ms: number;
  hint_used: boolean;
}

export interface TurnResponse {
  correct: boolean;
  error_type: ErrorType;
  next_surface_state: SurfaceState;
  feedback: string;
  hint: string | null;
  mastery: MasterySnapshot[];
  next_problem: ProblemView | null;
}

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

/** Start a session from a Turn-0 route choice (decision 0.D.2). */
export async function startSession(routeKey: string): Promise<StartSessionResponse> {
  return postJson<StartSessionResponse>('/session', { route_key: routeKey });
}

/** Submit one learner action (answer or hint request) and get the turn result. */
export async function submitTurn(request: TurnRequest): Promise<TurnResponse> {
  return postJson<TurnResponse>('/turn', request);
}
