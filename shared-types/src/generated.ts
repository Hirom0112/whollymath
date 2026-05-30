/* tslint:disable */
/* eslint-disable */
/**
/* This file was automatically generated from pydantic models by running pydantic2ts.
/* Do not modify it by hand - just update the pydantic models and then re-run the script
*/

/**
 * Ranking bucket for a student (TCH.B6). Any urgent alert forces ``struggling``.
 */
export type StudentCategory = "struggling" | "needs_attention" | "on_track";
/**
 * The named, tunable alert rules (TCH.B5).
 */
export type AlertKind =
  | "STUCK"
  | "REPEATED_MISCONCEPTION"
  | "LOW_ENGAGEMENT"
  | "FAILING_TREND"
  | "IDLE"
  | "REMEDIATION_STUCK";
/**
 * Alert severity (TCH.B5). Color is never the sole cue — paired with an icon + word.
 */
export type AlertSeverity = "info" | "warn" | "urgent";
/**
 * Behavioral HelpNeed direction over the recent window (TCH.B4).
 */
export type HelpNeedTrend = "rising" | "steady" | "falling";
/**
 * Mastery status for a KC — mirrors the learner course-map vocabulary (CP.A.1).
 */
export type KcStatus = "locked" | "available" | "in_progress" | "mastered" | "due_review";
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
 * The node's status on the learning path.
 */
export type CourseNodeStatus = "locked" | "available" | "in_progress" | "mastered" | "due_review";
/**
 * Which intervention form was offered (§3.7).
 */
export type InterventionKind = "inline_assertion" | "conceptual_prompt";
/**
 * Stable KC identifiers, matching `diagnostic_gems.json` `_meta.kc_catalog`.
 *
 * ``StrEnum`` makes a member compare equal to and serialize as its catalog
 * string, so the diagnostic-gem bank, the DB, and the API all speak the same
 * id, while still giving us guaranteed-unique members and a typed handle for
 * code that should not pass raw strings around. The string VALUES are the
 * contract with the catalog and must not change without updating the catalog.
 */
export type KnowledgeComponentId1 =
  | "KC_equivalence"
  | "KC_common_denominator"
  | "KC_addition_unlike"
  | "KC_subtraction_unlike"
  | "KC_number_line_placement";
/**
 * The learner's status on this lesson's KC (the course-map node's status).
 */
export type CourseNodeStatus1 = "locked" | "available" | "in_progress" | "mastered" | "due_review";
/**
 * Representation to render (§3.5).
 */
export type Representation = "symbolic" | "area_model" | "number_line" | "word_problem";
/**
 * How to answer: a numeric fraction (default) or yes/no buttons.
 */
export type AnswerKind = "numeric" | "yes_no";
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
 * The learner's aggregated status on this unit.
 */
export type UnitStatus = "locked" | "available" | "in_progress" | "mastered";
/**
 * The learner's aggregated status on this unit.
 */
export type UnitStatus1 = "locked" | "available" | "in_progress" | "mastered";

/**
 * One entry in the recent-activity timeline (TCH.F3 §5).
 */
export interface ActivityEventView {
  /**
   * Human-readable relative time, e.g. '2h ago' (server-rendered).
   */
  at: string;
  /**
   * Plain text, e.g. 'Answered 3/4 + 1/4 on the number line'.
   */
  label: string;
  outcome: "correct" | "incorrect" | "neutral";
}
/**
 * A live, in-session adaptation the hyperreactive loop proposed (Slice HR.B4).
 *
 * Present only when the live state classifier (HR.B2) fired a SUSTAINED state and the policy
 * (HR.B3) routed it to a move; ``null`` in the observe-only default (and whenever the live
 * adaptation flag is off). ``state`` is the LearnerState that triggered it (for surface styling),
 * ``reason`` is the one-line on-screen label, and ``is_morph`` distinguishes a surface change
 * (the new surface is on ``next_surface_state``) from a nudge-only (no state change — refuse-rule
 * 3). Deterministic; the LLM only voices an already-decided adaptation (§2.3).
 */
export interface AdaptationView {
  /**
   * The triggering LearnerState, e.g. 'confused' (HR.B2).
   */
  state: string;
  /**
   * The one-line on-screen reason for the change.
   */
  reason: string;
  /**
   * True if it proposes a surface change; False for a nudge-only (refuse-rule 3).
   */
  is_morph: boolean;
  /**
   * The surface state the morph proposes (e.g. 'S2_number_line_primary'), or null for a nudge-only. Advisory: the surface applies it; the per-answer routing on next_surface_state is unchanged by the observe-then-act adaptation.
   */
  to_surface?: string | null;
}
/**
 * One adaptive-arm turn, display-ready (Slice 5.3 theater). The verified path: the
 * persona's answer, the SymPy verdict, the labelled error class, the one-line feedback, the
 * resulting surface state, and the §3.4 effort/scaffold flags (hinted, below engagement floor).
 */
export interface AdaptiveTurnView {
  problem_statement: string;
  /**
   * The representation shown, e.g. 'Number line'.
   */
  format_label: string;
  /**
   * The persona's submitted answer, or '—' for none.
   */
  student_answer: string;
  /**
   * The SymPy verdict for this turn (domain decides).
   */
  correct: boolean;
  /**
   * 'Correct' or the labelled error, e.g. 'Magnitude'.
   */
  result_label: string;
  /**
   * The tutor's one-line labelled feedback for the turn.
   */
  feedback: string;
  /**
   * Surface state after the turn, e.g. 'S1 · symbolic'.
   */
  state_label: string;
  /**
   * Whether the attempt was scaffolded (down-weighted).
   */
  hint_used: boolean;
  /**
   * Whether the answer landed under the 2s engagement floor (non-evidence).
   */
  below_engagement_floor: boolean;
  /**
   * How long the persona 'thought', e.g. '12.0s'.
   */
  latency_label: string;
}
/**
 * One arm's mastery verdict for one persona, pre-formatted for display.
 *
 * The view layer (``api/eval_view``) maps the raw eval outcome to a label + a tone the
 * surface can render directly — the frontend stays presentation-only (CLAUDE.md §7).
 */
export interface ArmVerdictView {
  /**
   * Adaptive | Chat | Static
   */
  arm: string;
  /**
   * Short display label, e.g. 'Denied ✓' or 'N/A'.
   */
  verdict: string;
  /**
   * good | bad | neutral | pending — drives the surface styling.
   */
  tone: string;
  /**
   * One-line explanation (e.g. 'blocked at: transfer_probe').
   */
  detail: string;
}
/**
 * ``POST /teacher/student/{id}/assign-unit`` body (TCH.B8).
 */
export interface AssignUnitRequest {
  /**
   * The unit slug to assign next.
   */
  unit_id: string;
}
/**
 * ``POST /teacher/student/{id}/assign-unit`` response (TCH.B7/B8).
 */
export interface AssignUnitResult {
  student: TeacherStudentView;
}
/**
 * ``GET /teacher/student/{id}`` response — the full drill-in (TCH.B8, aggregating B3–B6).
 */
export interface TeacherStudentView {
  /**
   * The student's external key (Learner.session_id).
   */
  student_id: string;
  name: string;
  category: StudentCategory;
  category_reason: string;
  alerts?: TeacherAlertView[];
  struggle: StruggleSummaryView;
  current_unit_title?: string | null;
  current_lesson_title?: string | null;
  percent_complete: number;
  strengths?: KcMasteryView[];
  weaknesses?: KcMasteryView[];
  activity?: ActivityEventView[];
  assignable_units?: AssignableUnitView[];
  assigned_unit_id?: string | null;
}
/**
 * One alert on a student (TCH.B5). ``message`` is plain-language, templated, NO LLM.
 */
export interface TeacherAlertView {
  kind: AlertKind;
  severity: AlertSeverity;
  /**
   * Plain-language, templated alert text (no LLM).
   */
  message: string;
}
/**
 * The "what + WHY struggling" diagnostic (TCH.B4). Templated, NO LLM.
 */
export interface StruggleSummaryView {
  /**
   * One-line plain-language summary.
   */
  headline: string;
  /**
   * Longer templated explanation a teacher can read aloud.
   */
  detail: string;
  /**
   * Human label, e.g. 'Natural-number bias', or null if none.
   */
  matched_misconception?: string | null;
  helpneed_trend?: HelpNeedTrend | null;
  /**
   * 0..1 over the recent window, or null with no recent answers.
   */
  recent_error_rate?: number | null;
}
/**
 * A KC mastery row for the strengths/weaknesses lists (TCH.B3).
 */
export interface KcMasteryView {
  /**
   * KnowledgeComponentId catalog string, e.g. 'KC_equivalence'.
   */
  kc_id: string;
  /**
   * Display name from the KC registry (get_kc.skill_name).
   */
  skill_name: string;
  /**
   * BKT p(known), 0..1.
   */
  probability: number;
  status: KcStatus;
}
/**
 * A unit the teacher can assign next (TCH.F3 §6).
 */
export interface AssignableUnitView {
  /**
   * The unit slug.
   */
  unit_id: string;
  title: string;
  /**
   * false = prereqs not met. Advisory only: a teacher may assign either (TCH.Q5).
   */
  available: boolean;
}
/**
 * One entry in the benchmark-theater persona switcher: who, and the mastery dimension
 * they attack (PROJECT.md §4.2). Display-ready; the surface renders these verbatim.
 */
export interface BenchmarkPersonaSummaryView {
  /**
   * Opaque persona id; sent back to load that transcript.
   */
  persona_id: string;
  /**
   * Display name, e.g. 'Procedure Priya'.
   */
  persona_name: string;
  /**
   * The one mastery rule/dimension this learner attacks.
   */
  attacks: string;
  /**
   * The knowledge component the run targets.
   */
  kc: string;
}
/**
 * One persona run through all three arms, turn by turn, with each arm's verdict — the
 * on-screen "benchmark theater" (a teaching view of Slice 5.3 / PROJECT.md §3.11).
 *
 * The adaptive verdict is the real two-stage gate (provisional ``declare_mastery`` then the
 * S5 transfer probe); the chat verdict is the recorded LIVE self-certification (or the §9
 * prediction when no live run is committed); static has no mastery construct by design.
 */
export interface BenchmarkTranscriptView {
  persona_id: string;
  persona_name: string;
  attacks: string;
  kc: string;
  /**
   * The problem statements, the same set fed every arm.
   */
  problems: string[];
  adaptive_turns: AdaptiveTurnView[];
  /**
   * Display label, e.g. 'Denied ✓ — refused mastery'.
   */
  adaptive_verdict: string;
  /**
   * good | bad — drives the surface styling.
   */
  adaptive_tone: string;
  /**
   * Plain-language, demo-ready explanation of the verdict.
   */
  adaptive_why: string;
  /**
   * Stage that caught the learner (provisional | transfer_probe | NOT BLOCKED).
   */
  adaptive_blocked_at: string;
  /**
   * The exact rule(s) that denied mastery.
   */
  adaptive_reasons?: string[];
  /**
   * True when the learner reached provisional and the transfer probe ran.
   */
  adaptive_probe_ran: boolean;
  /**
   * The transfer-probe items, shown when the probe ran.
   */
  adaptive_probe_steps?: TransferProbeStepView[];
  chat_turns: ChatTurnView[];
  /**
   * Display label, e.g. 'Mastered ✗ (false positive)'.
   */
  chat_verdict: string;
  /**
   * good | bad | pending — drives the surface styling.
   */
  chat_tone: string;
  /**
   * Plain-language, demo-ready explanation of the chat verdict.
   */
  chat_why: string;
  /**
   * The chat tutor's own MASTERED/NOT_YET word (or a prediction note).
   */
  chat_self_assessment: string;
  /**
   * True when the verdict reflects a real recorded LLM run.
   */
  chat_live: boolean;
  /**
   * The standing caveat that the chat replies above are offline placeholders.
   */
  chat_illustrative_note: string;
  static_turns: StaticTurnView[];
  /**
   * Always 'N/A — certifies nothing' (no mastery model).
   */
  static_verdict: string;
  /**
   * neutral — the static arm has no verdict to style.
   */
  static_tone: string;
  /**
   * One-line note that the arm never checks or tracks.
   */
  static_note: string;
}
/**
 * One item of the S5 transfer probe, made visible (PROJECT.md §3.9): the step that tests
 * understanding rather than computation — a same-skill-new-format item, or an error-finding
 * 'Tim says ¼+¼=2/8, why is he wrong?' item — with its pass/fail and a plain-language line.
 */
export interface TransferProbeStepView {
  /**
   * 'representation' (new format) or 'error_finding'.
   */
  item_type: string;
  /**
   * What the learner was shown for this probe item.
   */
  prompt: string;
  /**
   * The representation of the item, e.g. 'number_line'.
   */
  surface_format: string;
  /**
   * Whether the learner passed this transfer item.
   */
  passed: boolean;
  /**
   * Plain-language line on what the persona did here.
   */
  detail: string;
}
/**
 * One chat-arm exchange, display-ready. ``tutor_reply`` is an ILLUSTRATIVE placeholder in
 * the offline theater (no live model is called) — the arm's real signal is its self-
 * certification verdict on the transcript, not this wording (CLAUDE.md §5, §8.2).
 */
export interface ChatTurnView {
  problem_statement: string;
  /**
   * The persona's typed answer (same as every arm).
   */
  student_answer: string;
  /**
   * Illustrative chat reply (offline placeholder, labelled).
   */
  tutor_reply: string;
}
/**
 * One static-arm screen, display-ready: the fixed worked-example walkthrough shown, and the
 * answer the learner submitted — recorded UNVERIFIED (the arm has no verifier, by design).
 */
export interface StaticTurnView {
  problem_statement: string;
  /**
   * The pre-rendered linear walkthrough shown for the item.
   */
  walkthrough: string;
  /**
   * The submitted answer, recorded but never checked.
   */
  student_answer: string;
}
/**
 * One KC's place on the course map (Slice CP.A.1 — the course-product home screen).
 *
 * Each node carries enough to render a learning-path stop: its KC id + human-readable
 * ``skill_name``/``description`` (from the KC registry), its ``status`` (the engine-derived
 * ``CourseNodeStatus`` — locked/available/in_progress/mastered/due_review), the ``prerequisites``
 * to draw as incoming edges, and the stored mastery ``probability`` for a progress indicator
 * (``null`` if the learner hasn't started this skill). Derived from existing engine state only
 * (PROJECT.md §3.13: reuse, never rebuild); off the turn loop, advisory.
 */
export interface CourseNodeView {
  kc_id: KnowledgeComponentId;
  /**
   * Human-readable skill name (KC registry).
   */
  skill_name: string;
  /**
   * One-sentence description of the skill (KC registry).
   */
  description: string;
  status: CourseNodeStatus;
  /**
   * KCs that must be confirmed before this one is suggested (the incoming edges).
   */
  prerequisites?: KnowledgeComponentId[];
  /**
   * Stored BKT mastery level for a touched skill; null if not yet started.
   */
  probability?: number | null;
}
/**
 * The whole learning path for one learner (Slice CP.A.1).
 *
 * ``nodes`` is the full catalog of KCs in teaching (algebra-spine) order, each with its status
 * — so the frontend can render the course map as nodes + prerequisite edges and use it as the
 * post-sign-in home. Always contains every KC (a path needs all its stops), even for a brand-new
 * learner (root available, rest locked).
 */
export interface CourseView {
  /**
   * Every KC as a path node, in teaching order, with its status.
   */
  nodes?: CourseNodeView[];
}
/**
 * The one-click demo-teacher handle returned by ``POST /teacher/demo-login`` (Slice TCH.B2).
 *
 * Extends ``TeacherHandle`` with the NON-secret ``token`` the frontend echoes back as
 * ``Authorization: Bearer <token>`` on subsequent teacher requests. The token is public by
 * design — the "Teacher demo" tab is a free, password-free demo, not an account (owner
 * decision). There is no second credential scheme: real teachers use their Google ID token.
 */
export interface DemoLoginResponse {
  /**
   * Stable persistence handle for the teacher (TCH.B2).
   */
  learner_id: number;
  /**
   * The teacher's email, if known — a display label only.
   */
  email?: string | null;
  /**
   * Identity role tag; always 'teacher' on this surface.
   */
  role: string;
  /**
   * Non-secret Bearer credential to echo back (form: 'demo:<id>'); free demo.
   */
  token: string;
}
/**
 * A buffered batch of interaction events for one session (Slice PL.2).
 *
 * The surface accumulates events client-side and flushes them in one POST to ``/events``.
 * ``session_id`` is the opaque session id the client already holds (the same value it threads
 * onto every ``TurnRequest``); telemetry is lenient, so an unknown ``session_id`` is NOT an
 * error — the server persists what it can and still accepts the batch (the endpoint never 404s).
 * The list is capped (``max_length``) so a giant batch can't be abused.
 */
export interface EventBatchRequest {
  /**
   * Opaque session id (TECH_STACK §9).
   */
  session_id: string;
  /**
   * The buffered events to record (≤200 per batch).
   *
   * @maxItems 200
   */
  events: InteractionEventIn[];
}
/**
 * One raw behavioral event the surface emits, on the wire (Slice PL.2).
 *
 * The fine-grained telemetry beyond the coarse ``TurnRequest``: a number-line drag, an
 * answer edit, focus/blur, idle, problem-presented, submit, hint-request, first-interaction.
 * Persisted OFF the turn loop (ARCHITECTURE.md §14 invariant 7) — this schema is captured and
 * stored, never fed into verify/mastery/policy.
 *
 *   - ``event_type`` is the open tag (a string, not an enum) so the surface can add a kind
 *     without a backend change; required and non-empty.
 *   - ``payload`` is the free-form detail for the event. It is intentionally an open object —
 *     the whole point of the capture table is to record arbitrary per-event detail PL.4 can
 *     mine later, so a fixed schema here would defeat it. This is the one justified ``Any`` in
 *     the contract (CLAUDE.md §6): it generates a permissive TS object, which is correct for an
 *     open telemetry payload. Defaults to ``{}`` so a bare event (e.g. ``focus``) needs no body.
 *   - ``client_ts`` is when the client recorded the event, if it sends one; the server stamps
 *     its own authoritative ``server_ts`` on receipt regardless.
 */
export interface InteractionEventIn {
  /**
   * Open event tag, e.g. 'numberline_drag'.
   */
  event_type: string;
  /**
   * Free-form per-event detail (open object — see class doc, §8.6).
   */
  payload?: {
    [k: string]: unknown;
  };
  /**
   * When the client recorded the event; server stamps its own too.
   */
  client_ts?: string | null;
}
/**
 * The ``/events`` reply: how many events were attempted-persisted (Slice PL.2).
 *
 * Returned with HTTP 202 ACCEPTED — the server has accepted the batch for best-effort
 * persistence off the turn loop, not confirmed durable storage (invariant 7). ``accepted`` is
 * the count the server tried to write; it is 0 when no DB is wired (the in-memory demo) or for
 * an empty batch. A persistence failure is swallowed, so a non-zero ``accepted`` is "attempted",
 * not a durability guarantee — which is exactly the contract telemetry needs.
 */
export interface EventIngestResponse {
  /**
   * Number of events accepted for best-effort persist.
   */
  accepted: number;
  /**
   * A proactive, additive help nudge offered MID-PROBLEM (live loop Beat 1) when the behavioral stream shows sustained struggle on the in-progress problem — rendered inline, never reorganizing the workspace (refuse-rule 1). null in the default / observe-only arm. The mascot may voice it; it never decides correctness (§8.1).
   */
  nudge?: InterventionView | null;
}
/**
 * A proactively-offered help nudge (Slice 4.5), or absent when none is offered.
 *
 * Distinct from the reactive ``hint`` (which answers an explicit REQUEST_HINT): this is
 * help the system offers *unasked* after the §3.7 sustained-signal gate fires on the
 * HelpNeed stream. Present only when the session's proactive arm is enabled AND the gate
 * fired; ``null`` otherwise (the observe-only default). The surface renders ``text``
 * inline in the workspace, never as a modal (§3.8 refuse-rule 6).
 */
export interface InterventionView {
  kind: InterventionKind;
  /**
   * The pre-written nudge text (no LLM, §8.1).
   */
  text: string;
}
/**
 * Start a homework run for a skill (the desktop, at lesson end). Returns a token for the QR.
 */
export interface HwAssignRequest {
  kc: KnowledgeComponentId1;
  /**
   * Optional session this homework belongs to (carried for context).
   */
  session_id?: string | null;
}
/**
 * The freshly-created homework run: the upload token (QR payload) + the question list.
 */
export interface HwAssignResponse {
  /**
   * One-time upload token; the QR encodes it.
   */
  token: string;
  /**
   * The anchored target skill.
   */
  target_kc: string;
  /**
   * The set, in order (target first).
   */
  questions: HwQuestionView[];
}
/**
 * One homework question, for the desktop checklist + the mobile capture screen.
 */
export interface HwQuestionView {
  /**
   * 0-based position in the set (the grading/scan index).
   */
  index: number;
  /**
   * The kid-facing problem text.
   */
  statement: string;
  /**
   * True for the anchored target skill; False for spaced review.
   */
  is_target: boolean;
}
/**
 * One learner-confirmed answer from the read-back (may differ from the draft if corrected).
 */
export interface HwConfirmAnswer {
  index: number;
  /**
   * The confirmed answer text, or null if left blank.
   */
  answer?: string | null;
}
/**
 * The confirmed answers to grade (after the desktop read-back).
 */
export interface HwConfirmRequest {
  token: string;
  /**
   * Confirmed answer per question index.
   */
  answers: HwConfirmAnswer[];
}
/**
 * One question's DRAFT transcription, shown for the read-back ('I read this as 1/4 — yes?').
 */
export interface HwDraftItemView {
  index: number;
  statement: string;
  is_target: boolean;
  /**
   * What the scanner read for this question; null if unreadable.
   */
  read_as?: string | null;
}
/**
 * The graded set + the ★★ verdict (target-skill score ≥ 0.8 = passed).
 */
export interface HwGradeResultView {
  results: HwQuestionResultView[];
  target_correct: number;
  target_total: number;
  target_score: number;
  /**
   * True = ★★ earned; False = redo the lesson + a fresh set.
   */
  passed: boolean;
}
/**
 * One graded question — for the 1-on-1 walk-through (right or wrong).
 */
export interface HwQuestionResultView {
  index: number;
  statement: string;
  is_target: boolean;
  submitted: string | null;
  correct: boolean;
  unreadable: boolean;
}
/**
 * What the desktop polls: the run state, the draft (for the read-back), and the verdict.
 */
export interface HwStatusResponse {
  /**
   * waiting | ready_for_review | graded.
   */
  state: string;
  /**
   * The transcribed draft (present once photos are in).
   */
  draft?: HwDraftItemView[];
  /**
   * The graded verdict (present once confirmed).
   */
  result?: HwGradeResultView | null;
}
/**
 * The phone's page photos for a run — base64-encoded images (no multipart dependency).
 */
export interface HwSubmitRequest {
  /**
   * The run's upload token (from the QR).
   */
  token: string;
  /**
   * One or more page images, base64-encoded (data may be raw or data-URL).
   *
   * @minItems 1
   */
  pages: [string, ...string[]];
}
/**
 * Acknowledges the upload and reports the new run state (``ready_for_review``).
 */
export interface HwSubmitResponse {
  /**
   * Run state after the upload (waiting | ready_for_review | graded).
   */
  state: string;
  /**
   * How many questions the draft now covers.
   */
  question_count: number;
}
/**
 * One lesson within a unit, with the learner's status on its KC (Slice DAT.9).
 *
 * The renderable subset of a catalog ``CatalogLesson`` joined to its rolled-up
 * ``LessonProgress`` (``mastery/unit_progress``): the catalog ``title`` + dual-coverage
 * standard codes for display, plus the learner's per-lesson ``status``/``probability`` derived
 * from the lesson's KC course-map node. ``kc_id`` is the raw catalog string (a real KC id, a
 * forward-declared Wave-3 string, or ``null`` for an interleave-gate lesson); ``ccss_code`` /
 * ``teks_code`` are ``null`` where a lesson is single-framework (the honest exceptions in the
 * catalog). ``probability`` is ``null`` until the KC is touched (or for an unmapped lesson).
 * Derived from existing engine state only (PROJECT.md §3.13); off the turn loop, advisory.
 */
export interface LessonView {
  /**
   * Stable lesson slug (unique within the unit).
   */
  lesson_slug: string;
  /**
   * Human-readable lesson title (catalog).
   */
  title: string;
  /**
   * The lesson's catalog KC string, or null if it maps to no KC yet.
   */
  kc_id?: string | null;
  /**
   * Common Core (CCSS) standard code, or null if single-framework.
   */
  ccss_code?: string | null;
  /**
   * Texas (TEKS) standard code, or null if single-framework.
   */
  teks_code?: string | null;
  status: CourseNodeStatus1;
  /**
   * Stored BKT mastery level for the lesson's KC; null if not yet started.
   */
  probability?: number | null;
}
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
 * The authenticated learner's persistent identity handle + carried-forward mastery (PL.3).
 *
 * Returned by ``GET /me`` for a request bearing a valid Google ID token. This is the
 * "same login anywhere → same state" proof: the ``learner_id`` is the stable persistence
 * handle the Google ``sub`` maps to (idempotently — the same login always resolves to the
 * same row), and ``mastery`` is that learner's persisted per-KC state (reusing the PL.1
 * ``MasteryState`` rows), so a learner signing in on a new device sees their prior progress.
 *
 * What is deliberately NOT here: the Google ``sub`` itself. The ``sub`` is an auth-layer
 * secret-ish identifier we key on but never re-expose; the wire handle is the internal
 * ``learner_id``. ``email`` is included only as the convenience label the surface greets the
 * learner with. Neither field is consumed by any turn-loop decision — identity never reaches
 * the mastery model, policy, or LLM (ARCHITECTURE.md §14 invariant 8); this payload exists
 * purely for persistence/continuity on the auth path.
 */
export interface MeResponse {
  /**
   * Stable persistence handle the Google sub maps to (PL.3).
   */
  learner_id: number;
  /**
   * The learner's Google email, if the token carried one — a display label only.
   */
  email?: string | null;
  /**
   * The learner's carried-forward per-KC mastery (PL.1 rows; mastered=confirmed).
   */
  mastery?: MasterySnapshot[];
  study_plan?: StudyPlanView;
}
/**
 * What to do next: due reviews (spaced repetition) + the next unlocked skill.
 */
export interface StudyPlanView {
  /**
   * Confirmed KCs due for review, most-decayed first (spaced repetition).
   */
  due_reviews?: string[];
  /**
   * New KCs whose prerequisites are confirmed, in algebra-spine order.
   */
  unlocked_next?: string[];
  /**
   * The single best next KC (due review > new skill > null if all done/fresh).
   */
  recommended?: string | null;
}
/**
 * One arm's verdict on one pre-registered metric, pre-formatted for display.
 *
 * Like ``ArmVerdictView`` but for the per-metric table (Slice 5.3.3): a short status label
 * plus a tone that drives styling (``good`` enforced / ``bad`` missed / ``neutral`` no
 * mechanism / ``pending`` predicted).
 */
export interface MetricArmVerdictView {
  /**
   * Adaptive | Chat | Static
   */
  arm: string;
  /**
   * Short label, e.g. 'Enforced', 'Missed ✗', 'Max ✗', 'N/A'.
   */
  status: string;
  /**
   * good | bad | neutral | pending — drives the surface styling.
   */
  tone: string;
  /**
   * One-line explanation of the verdict.
   */
  detail: string;
}
/**
 * One of the five remaining pre-registered metrics across the three arms (RESEARCH.md §9).
 *
 * The adaptive verdict is derived from the actual deterministic run (the rule that blocked the
 * adversary); the chat verdict from the recorded live run (or the §9 prediction); the static
 * verdict from the arm's architecture. The headline (false-positive mastery) is the per-persona
 * table above.
 */
export interface MetricComparisonView {
  /**
   * Stable metric id, e.g. 'hint_dependence'.
   */
  key: string;
  /**
   * Display name, e.g. 'Hint dependence at mastery'.
   */
  name: string;
  /**
   * The persona that attacks this metric.
   */
  adversary: string;
  adaptive: MetricArmVerdictView;
  chat: MetricArmVerdictView;
  static: MetricArmVerdictView;
}
/**
 * One persona's row in the three-arm comparison: who, what it attacks, the problems it
 * saw, and each arm's verdict.
 */
export interface PersonaComparisonView {
  persona_name: string;
  attacks: string;
  /**
   * The problem statements this persona was given.
   */
  problems: string[];
  adaptive: ArmVerdictView;
  chat: ArmVerdictView;
  static: ArmVerdictView;
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
  answer_kind?: AnswerKind;
  /**
   * For a yes/no item, what it asks: 'equal' (same amount?) or 'greater' (a > b?). Lets the surface label the question accurately. 'equal' for non-yes/no items.
   */
  yes_no_relation?: string;
  /**
   * Number-line only: equal intervals PER UNIT to snap a drag to (the target's denominator); null otherwise. The total ticks shown is ``(axis_max - axis_min) * tick_segments``.
   */
  tick_segments?: number | null;
  /**
   * Number-line only: the left end of the axis. 0 for a proper-fraction or improper placement; negative for a negative target (e.g. −2 to place −5/4) — CCSS 6.NS.6. Ignored by non-number-line surfaces.
   */
  axis_min?: number;
  /**
   * Number-line only: the right end of the axis. 1 for a proper fraction, 2 for an improper target (e.g. 5/4), so the marker can sit PAST the '1' whole. Ignored by non-number-line surfaces.
   */
  axis_max?: number;
  /**
   * Equivalence fill-the-top only: the denominator named in the question ('?/8'), pre-filled and locked so the learner enters only the numerator. Null otherwise.
   */
  given_denominator?: number | null;
}
/**
 * The read-back of a snapped handwritten answer, for the learner to confirm (Slice HR.C2).
 *
 * The multimodal beat: instead of typing, a child photographs their work; the camera→OCR path
 * transcribes it and this is what the surface shows back — "I read this as 3/4 — right?" — BEFORE
 * grading. On confirm, ``transcribed_answer`` is submitted through the normal turn (the SAME SymPy
 * verifier as a typed answer). ``readable`` is false when no answer could be read, so the surface
 * asks the learner to rewrite it rather than grade a misread. No LLM, no second grader (§8.2).
 */
export interface ReadBackView {
  /**
   * The answer read from the image (e.g. '3/4'), or null if unreadable.
   */
  transcribed_answer?: string | null;
  /**
   * Whether an answer was extracted; false → ask the learner to rewrite it.
   */
  readable: boolean;
}
/**
 * A roster row — one student summarized for the ranked list (TCH.B3 + B6).
 */
export interface RosterStudentView {
  /**
   * The student's external key (Learner.session_id).
   */
  student_id: string;
  name: string;
  category: StudentCategory;
  /**
   * One-line reason for the bucket (TCH.B6).
   */
  category_reason: string;
  current_unit_title?: string | null;
  current_lesson_title?: string | null;
  /**
   * 0..1 across the assigned course.
   */
  percent_complete: number;
  alerts?: TeacherAlertView[];
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
 * Begin a session — EITHER from a Turn-0 routing choice (0.D.2) OR a course-map skill.
 *
 * Two mutually-exclusive entry points (exactly one of ``route_key`` / ``kc``):
 *
 *   - ``route_key`` — the chosen Turn-0 option key (the cold-start path). The KC, calibration
 *     item, and BKT prior are all derived server-side from the locked routing table (tutor
 *     ``from_route``), so the prior-not-commitment seeding stays authoritative (0.D.2).
 *   - ``kc`` — start a lesson DIRECTLY for this knowledge component (the course-map node
 *     launch, §3.13). The server presents a generated first problem for the KC in its first
 *     live representation; no skill claim is seeded (studying a skill is not a claim to know
 *     it).
 */
export interface StartSessionRequest {
  /**
   * The chosen Turn-0 option key (0.D.2). Provide this OR kc, not both.
   */
  route_key?: string | null;
  /**
   * Start a lesson directly for this KC (course map). Provide this OR route_key.
   */
  kc?: KnowledgeComponentId | null;
  /**
   * Opt into the proactive HelpNeed arm for this session (Slice 4.5). Default OFF = observe-only (RESEARCH.md §7.5); set by the Slice 5.4 A/B harness or a demo. When OFF the session never sees a proactive intervention.
   */
  proactive_enabled?: boolean;
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
  answer_kind?: AnswerKind;
  /**
   * For a yes/no item, what it asks: 'equal' (same amount?) or 'greater' (a > b?). Lets the surface label the question accurately. 'equal' for non-yes/no items.
   */
  yes_no_relation?: string;
  /**
   * Number-line only: equal intervals PER UNIT to snap a drag to (the target's denominator); null otherwise. The total ticks shown is ``(axis_max - axis_min) * tick_segments``.
   */
  tick_segments?: number | null;
  /**
   * Number-line only: the left end of the axis. 0 for a proper-fraction or improper placement; negative for a negative target (e.g. −2 to place −5/4) — CCSS 6.NS.6. Ignored by non-number-line surfaces.
   */
  axis_min?: number;
  /**
   * Number-line only: the right end of the axis. 1 for a proper fraction, 2 for an improper target (e.g. 5/4), so the marker can sit PAST the '1' whole. Ignored by non-number-line surfaces.
   */
  axis_max?: number;
  /**
   * Equivalence fill-the-top only: the denominator named in the question ('?/8'), pre-filled and locked so the learner enters only the numerator. Null otherwise.
   */
  given_denominator?: number | null;
}
/**
 * What a returning learner should do next (Slice 6.x — spaced repetition).
 *
 * Derived from the persisted mastery (PL.1 rows): ``due_reviews`` are confirmed skills whose
 * retention has decayed since last practice (most-decayed first — the "space" in spaced
 * repetition); ``unlocked_next`` are new skills whose prerequisites are confirmed, in
 * algebra-spine order; ``recommended`` is the single best next action (a due review if any,
 * else the earliest unlocked new skill, else null when everything is confirmed and fresh).
 * KC ids are the catalog strings. Off the turn loop; advisory only.
 */
export interface StudyPlanView1 {
  /**
   * Confirmed KCs due for review, most-decayed first (spaced repetition).
   */
  due_reviews?: string[];
  /**
   * New KCs whose prerequisites are confirmed, in algebra-spine order.
   */
  unlocked_next?: string[];
  /**
   * The single best next KC (due review > new skill > null if all done/fresh).
   */
  recommended?: string | null;
}
/**
 * The authenticated teacher's identity handle (Slice TCH.B2).
 *
 * Returned by ``GET /teacher/me`` once ``current_teacher`` has authorized the request (a Google
 * learner with ``role="teacher"`` or the demo teacher). Carries only the stable ``learner_id``,
 * the email display label, and the ``role`` tag — never the Google ``sub`` and never anything
 * the turn loop reads (ARCHITECTURE.md §14 invariant 8).
 */
export interface TeacherHandle {
  /**
   * Stable persistence handle for the teacher (TCH.B2).
   */
  learner_id: number;
  /**
   * The teacher's email, if known — a display label only.
   */
  email?: string | null;
  /**
   * Identity role tag; always 'teacher' on this surface.
   */
  role: string;
}
/**
 * ``GET /teacher/roster`` response (TCH.B8).
 */
export interface TeacherRosterView {
  teacher_name: string;
  class_name: string;
  students?: RosterStudentView[];
}
/**
 * The full three-arm comparison for display (Slice 5.3, PROJECT.md §3.11).
 *
 * The adaptive and static columns are computed live and deterministically; the chat
 * column is the pre-registered prediction until the cost-gated live LLM run
 * (``chat_live`` says which).
 */
export interface ThreeArmComparisonView {
  rows: PersonaComparisonView[];
  /**
   * Number of personas (arms are scored over these).
   */
  total: number;
  adaptive_false_positives: number;
  /**
   * Chat false positives from the live run, or null when still the prediction.
   */
  chat_false_positives?: number | null;
  /**
   * True once the chat column reflects a real LLM run.
   */
  chat_live: boolean;
  /**
   * The §3.11 pitch summary for the header.
   */
  headline: string;
  /**
   * The five remaining pre-registered metrics, each across the three arms.
   */
  metrics?: MetricComparisonView[];
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
   * Observe-only P(unproductive) from the HelpNeed predictor for the NEXT problem, given this session's history (Slice 4.4.1). It is reported, not acted on by the surface. null on a hint turn (no answer was submitted, so the history is unchanged).
   */
  help_need?: number | null;
  /**
   * A proactively-offered help nudge (Slice 4.5), present only when the session's proactive arm is enabled AND the §3.7 sustained-signal gate fired on the HelpNeed stream. null in the observe-only default. Rendered inline in the workspace (§3.8 refuse-rule 6).
   */
  intervention?: InterventionView | null;
  /**
   * A live, in-session adaptation the hyperreactive loop proposed (Slice HR.B4), present only when the live state classifier fired a SUSTAINED state and the adaptation flag is on. null in the observe-only default. The morph target (if any) is on next_surface_state; the on-screen reason is on adaptation.reason.
   */
  adaptation?: AdaptationView | null;
  /**
   * The next problem to present after this turn, or null when the loop has nothing further to serve (e.g. an unrecognized session). The surface renders it directly; the deterministic loop chose it (§10 step 12).
   */
  next_problem?: ProblemView | null;
  /**
   * The ordered worked steps to reveal when ``next_surface_state`` is S4_worked_example; empty otherwise. This is the worked solution of the problem the learner JUST got stuck on — NOT ``next_problem`` (which is the fresh practice item and whose answer must not be revealed). The surface reveals these one step at a time, each with its 'why?' prompt (§3.5 S4). May be empty even on an S4 turn when the stuck problem's KC procedure has no buildable worked example (e.g. a yes/no item with no operand pair) — the surface then shows S4 without a walkthrough rather than the loop failing.
   */
  worked_example?: WorkedStepView[];
  /**
   * The worked steps of the problem the learner JUST SOLVED, present only after a CORRECT answer so the surface can affirm WHY it works ('Nice — here's why 1/2 + 1/4 = 3/4') before the next problem (live loop Beat 2). Distinct from ``worked_example`` (the stuck-path S4 walkthrough): this is a celebrate-and-consolidate beat, not a rescue. Empty on a wrong answer, a hint turn, or when the solved problem has no buildable walkthrough. The mascot may voice it; no LLM decides correctness (§8.1).
   */
  explanation?: WorkedStepView[];
  /**
   * True on the turn that FINISHES the lesson — i.e. the goal KC just became CONFIRMED (the S5 transfer probe passed). The bounded-lesson terminal signal (CP.B; PROJECT.md §3.13): the surface shows the 'you finished it' screen and routes the learner home instead of presenting yet another practice problem. ``next_problem`` may still be populated as an optional 'keep practicing' item, but a complete lesson must not silently loop on. False on every other turn.
   */
  lesson_complete?: boolean;
}
/**
 * One revealed step of an S4 worked example, on the wire (Slice 3.6 → API).
 *
 * The renderable subset of a domain ``WorkedStep`` (``tutor/worked_example.py``): the
 * kid-facing ``shown`` step content and the one-line conceptual ``why_prompt`` that
 * accompanies it. The §3.5 S4 requirement is that EVERY revealed step carries a "why did
 * this work?" prompt, so both fields are required. The domain ``WorkedStep`` also carries
 * a SymPy ``revealed_value`` for self-consistency; that is internal and never crosses the
 * wire (it would leak intermediate magnitudes — the surface reveals steps one at a time,
 * §3.5 S4).
 */
export interface WorkedStepView {
  /**
   * The kid-facing step content (§3.5 S4).
   */
  shown: string;
  /**
   * The one-line 'why did this work?' prompt for this step (§3.5 S4).
   */
  why_prompt: string;
}
/**
 * A single unit with its lessons and the learner's per-lesson progress (Slice DAT.9).
 *
 * The ``UnitView`` fields (so a detail page needs no second card lookup) plus ``lessons`` — the
 * unit's lessons in catalog order, each a ``LessonView`` carrying the learner's per-lesson
 * status. The frontend renders this as a unit's lesson list / learning-path rail.
 */
export interface UnitDetailView {
  /**
   * Stable unit slug (unique across the catalog).
   */
  unit_slug: string;
  /**
   * Human-readable unit title (catalog).
   */
  title: string;
  /**
   * Short description of the unit (catalog).
   */
  description: string;
  /**
   * Display/teaching order within the catalog (1-based).
   */
  order: number;
  /**
   * Common Core (CCSS) cluster code, or null if single-framework.
   */
  ccss_cluster?: string | null;
  /**
   * Texas (TEKS) cluster code, or null if single-framework.
   */
  teks_cluster?: string | null;
  status: UnitStatus;
  /**
   * Percent of the unit's lessons completed, in [0, 100].
   */
  percent_complete: number;
  /**
   * Number of lessons in the unit.
   */
  lesson_count: number;
  /**
   * True only for the signed-in learner's teacher-assigned unit (DAT.10).
   */
  assigned: boolean;
  /**
   * The unit's lessons, in catalog order, each with per-lesson progress.
   */
  lessons?: LessonView[];
}
/**
 * The full unit catalog for one learner, with progress + assignment (Slice DAT.8).
 *
 * ``units`` is every catalog unit in teaching order, each a ``UnitView`` with the learner's
 * rolled-up progress — so the frontend can render the unit map and use it as a learning home.
 * Always contains every unit (a path needs all its stops), even for a brand-new learner.
 * ``assigned_unit_slug`` is the teacher-assigned unit for a signed-in learner (Slice DAT.10),
 * or ``null`` when none is assigned OR the caller is anonymous (anonymous demo learners have no
 * teacher assignment).
 */
export interface UnitListView {
  /**
   * Every unit as a card, in teaching order, with the learner's progress.
   */
  units?: UnitView[];
  /**
   * Slug of the teacher-assigned unit for a signed-in learner (DAT.10), or null when none is assigned or the caller is anonymous.
   */
  assigned_unit_slug?: string | null;
}
/**
 * One unit with the learner's rolled-up progress, no lessons (Slice DAT.8).
 *
 * The unit-card view for the unit list: the catalog ``title``/``description``/``order`` +
 * dual-coverage cluster codes, plus the learner's aggregated ``status``/``percent_complete``
 * (from ``mastery/unit_progress``) and ``lesson_count``. ``assigned`` is ``true`` only for the
 * signed-in learner's teacher-assigned unit (Slice DAT.10), ``false`` for every other unit and
 * for an anonymous caller. ``ccss_cluster``/``teks_cluster`` are ``null`` for a single-framework
 * unit (e.g. TEKS-only integer arithmetic). Derived from the catalog + course map only
 * (PROJECT.md §3.13: reuse, never rebuild); off the turn loop, advisory.
 */
export interface UnitView {
  /**
   * Stable unit slug (unique across the catalog).
   */
  unit_slug: string;
  /**
   * Human-readable unit title (catalog).
   */
  title: string;
  /**
   * Short description of the unit (catalog).
   */
  description: string;
  /**
   * Display/teaching order within the catalog (1-based).
   */
  order: number;
  /**
   * Common Core (CCSS) cluster code, or null if single-framework.
   */
  ccss_cluster?: string | null;
  /**
   * Texas (TEKS) cluster code, or null if single-framework.
   */
  teks_cluster?: string | null;
  status: UnitStatus1;
  /**
   * Percent of the unit's lessons completed, in [0, 100].
   */
  percent_complete: number;
  /**
   * Number of lessons in the unit.
   */
  lesson_count: number;
  /**
   * True only for the signed-in learner's teacher-assigned unit (DAT.10).
   */
  assigned: boolean;
}
