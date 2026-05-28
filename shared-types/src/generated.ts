/* tslint:disable */
/* eslint-disable */
/**
/* This file was automatically generated from pydantic models by running pydantic2ts.
/* Do not modify it by hand - just update the pydantic models and then re-run the script
*/

/**
 * Stable KC identifiers, matching `diagnostic_gems.json` `_meta.kc_catalog`.
 *
 * ``StrEnum`` makes a member compare equal to and serialize as its catalog
 * string, so the diagnostic-gem bank, the DB, and the API all speak the same
 * id, while still giving us guaranteed-unique members and a typed handle for
 * code that should not pass raw strings around. The string VALUES are the
 * contract with the catalog and must not change without updating the catalog.
 */
export type KnowledgeComponentId =
  | "KC_equivalence"
  | "KC_common_denominator"
  | "KC_addition_unlike"
  | "KC_subtraction_unlike"
  | "KC_number_line_placement";
/**
 * Representation to render (§3.5).
 */
export type Representation = "symbolic" | "area_model" | "number_line" | "word_problem";
/**
 * The starting surface state (S1, §7).
 */
export type SurfaceState =
  | "S1_symbolic_focus"
  | "S2_number_line_primary"
  | "S3_fraction_bars_primary"
  | "S4_worked_example"
  | "S5_transfer_probe";
/**
 * What kind of learner action this turn carries (ARCHITECTURE.md §10 step 1).
 *
 * The learner either submits an answer to the current problem, or asks for a
 * hint. Splitting the two is what lets the mastery model later down-weight
 * hinted attempts and enforce the ">=1 unassisted correct" rule (ARCHITECTURE.md
 * §6 rule 3) — the route does not implement that here, but the contract must be
 * able to express the distinction.
 */
export type ActionType = "submit_answer" | "request_hint";
/**
 * The surface the learner is currently in (§7).
 */
export type SurfaceState1 =
  | "S1_symbolic_focus"
  | "S2_number_line_primary"
  | "S3_fraction_bars_primary"
  | "S4_worked_example"
  | "S5_transfer_probe";
/**
 * Labeled error class when incorrect; NONE when correct (§10).
 */
export type ErrorCategory = "none" | "magnitude" | "operation" | "format" | "other";
/**
 * The surface state to show next (policy, §7).
 */
export type SurfaceState2 =
  | "S1_symbolic_focus"
  | "S2_number_line_primary"
  | "S3_fraction_bars_primary"
  | "S4_worked_example"
  | "S5_transfer_probe";

/**
 * A per-KC mastery readout returned to the surface (ARCHITECTURE.md §6).
 *
 * The response carries a snapshot so the UI can show mastery progress without a
 * second round-trip. ``probability`` is the BKT probability for the KC and
 * ``mastered`` is the model's *declared* mastery (which requires more than the
 * probability threshold — §6 rules 1-4). This slice only fixes the shape; the
 * real values come from the mastery model (a later slice).
 */
export interface MasterySnapshot {
  kc_id: KnowledgeComponentId;
  /**
   * BKT mastery probability for this KC.
   */
  probability: number;
  /**
   * Whether the mastery model has *declared* mastery (§6).
   */
  mastered: boolean;
}
/**
 * The learner-facing view of one presented problem (ARCHITECTURE.md §10 step 12).
 *
 * This is what the surface needs to RENDER a problem — the readable subset of the
 * domain ``Problem`` (problem_generators.py). It deliberately carries no answer,
 * operands, or SymPy values: correctness is the domain verifier's job (CLAUDE.md
 * §8.2), so the wire never ships the answer to the client where it could leak.
 *
 *   - ``problem_id`` echoes back on the next ``TurnRequest`` so the loop knows
 *     which problem an answer is for.
 *   - ``kc`` / ``surface_format`` let the surface pick the right workspace
 *     (symbolic editor / number line / fraction bars — §3.5).
 *   - ``statement`` is the kid-friendly text shown to the learner.
 *   - ``tick_segments`` is a NUMBER-LINE rendering hint: how many equal intervals
 *     to divide the 0–1 line into. ``None`` for non-number-line problems.
 */
export interface ProblemView {
  /**
   * Stable id; echoed on the next turn.
   */
  problem_id: string;
  kc: KnowledgeComponentId;
  surface_format: Representation;
  /**
   * Kid-friendly problem text.
   */
  statement: string;
  /**
   * Number-line only: equal intervals on the 0–1 line to snap to; null otherwise.
   */
  tick_segments?: number | null;
}
/**
 * One Turn-0 routing option for the cold-start menu (decision 0.D.2).
 *
 * The kid-friendly view of a tutor ``RouteOption``: the surface renders ``prompt``
 * and visually de-emphasizes the single ``is_unsure_default`` option (0.D.2: no
 * quiz/diagnostic framing — that is a presentation choice the surface makes). The
 * client sends ``key`` back on ``POST /session`` to start in that route; it never
 * sends the KC directly, so the routing menu stays the single source of truth.
 */
export interface RouteOptionView {
  /**
   * Opaque option id; sent back to start a session.
   */
  key: string;
  /**
   * Kid-friendly option text (no curriculum terms).
   */
  prompt: string;
  /**
   * The single de-emphasized 'I'm not sure' default (0.D.2).
   */
  is_unsure_default: boolean;
}
/**
 * Begin a session from a Turn-0 routing choice (decision 0.D.2).
 *
 * Carries only the chosen ``route_key`` (a ``RouteOptionView.key``). The KC,
 * calibration item, and BKT prior are all derived server-side from the locked
 * routing table (tutor ``from_route``) — the client cannot set them, so the
 * prior-not-commitment seeding stays authoritative on the backend (0.D.2).
 */
export interface StartSessionRequest {
  /**
   * The chosen Turn-0 option key (0.D.2).
   */
  route_key: string;
}
/**
 * The freshly-started session and its Turn-1 calibration problem (0.D.2).
 *
 * Returns the opaque ``session_id`` the surface threads onto every subsequent
 * ``TurnRequest``, the starting ``surface_state`` (S1 — the default fluent state,
 * ARCHITECTURE.md §7), and the locked Turn-1 calibration ``problem`` for the route
 * (0.D.2). One round-trip puts the learner in front of their first problem.
 */
export interface StartSessionResponse {
  /**
   * Opaque session id (TECH_STACK §9).
   */
  session_id: string;
  surface_state: SurfaceState;
  problem: ProblemView1;
}
/**
 * The Turn-1 calibration problem for the route (0.D.2).
 */
export interface ProblemView1 {
  /**
   * Stable id; echoed on the next turn.
   */
  problem_id: string;
  kc: KnowledgeComponentId;
  surface_format: Representation;
  /**
   * Kid-friendly problem text.
   */
  statement: string;
  /**
   * Number-line only: equal intervals on the 0–1 line to snap to; null otherwise.
   */
  tick_segments?: number | null;
}
/**
 * One learner action entering the turn loop (ARCHITECTURE.md §10 steps 1-2).
 *
 * This is the ``submit`` payload the surface sends. Fields mirror exactly what
 * the deterministic path needs downstream:
 *
 *   - ``session_id`` / ``problem_id`` identify *who* and *which problem*
 *     (TECH_STACK §9: v1 uses session-id-based identification, no auth).
 *   - ``action`` is submit-vs-hint (drives the unassisted-attempt rule, §6).
 *   - ``submitted_answer`` is the raw answer string the verifier checks with
 *     SymPy (domain layer; never validated here — that is §9's job).
 *   - ``surface_state`` is the state the learner is *currently* in, so the
 *     policy can compute the transition relative to it (§7).
 *   - ``latency_ms`` feeds both the engagement floor (§6) and the HelpNeed
 *     feature vector (§8) — it is evidence, so it is required.
 *   - ``hint_used`` records whether the learner had a hint on this problem, so
 *     the attempt can be down-weighted (§6 rule 3).
 */
export interface TurnRequest {
  /**
   * Opaque learner-session id (TECH_STACK §9).
   */
  session_id: string;
  /**
   * Id of the problem this action answers.
   */
  problem_id: string;
  action: ActionType;
  /**
   * Raw learner answer; SymPy (domain) decides correctness, not the API.
   */
  submitted_answer?: string | null;
  surface_state: SurfaceState1;
  /**
   * Time the learner took; feeds engagement floor (§6) + HelpNeed (§8).
   */
  latency_ms: number;
  /**
   * Whether a hint was shown for this problem (down-weights the attempt, §6).
   */
  hint_used?: boolean;
}
/**
 * The turn loop's reply to the surface (ARCHITECTURE.md §10 steps 11-12).
 *
 * This is the "next state + labeled feedback" the API returns. Fields mirror
 * the deterministic outputs of the loop:
 *
 *   - ``correct`` / ``error_type`` are the verifier's verdict (§10 step 4).
 *   - ``next_surface_state`` is the policy's chosen transition (§10 step 9).
 *   - ``feedback`` is the *labeled* feedback string — refuse-rule 4 requires a
 *     one-line label explaining any transition (§7). It is plain text here; the
 *     LLM surface layer may later replace/augment it, but only *after* the
 *     deterministic path (§10 ``opt`` block, ARCHITECTURE.md §14 invariant 1).
 *   - ``hint`` is optional natural-language help, present only when help is
 *     shown (§10 ``opt`` block).
 *   - ``mastery`` is the per-KC snapshot (§6).
 */
export interface TurnResponse {
  /**
   * Whether the submitted answer was correct (SymPy verdict, §9).
   */
  correct: boolean;
  error_type?: ErrorCategory;
  next_surface_state: SurfaceState2;
  /**
   * One-line labeled feedback explaining the transition (refuse-rule 4, §7).
   */
  feedback: string;
  /**
   * Optional natural-language hint, shown only when help is offered (§10).
   */
  hint?: string | null;
  /**
   * Per-KC mastery snapshot for the affected KC(s) (§6).
   */
  mastery?: MasterySnapshot[];
  /**
   * The next problem to present after this turn, or null when the loop has nothing further to serve (e.g. an unrecognized session). The surface renders it directly; the deterministic loop chose it (§10 step 12).
   */
  next_problem?: ProblemView | null;
}
