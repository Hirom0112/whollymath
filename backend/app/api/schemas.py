"""Pydantic v2 request/response models for the turn loop (Slice 1.9).

These models are the *contract* for the core turn endpoint — the shapes a single
learner action and its response take as they flow through the loop described in
ARCHITECTURE.md §10 (Learner -> Surface -> Turn Loop -> Verifier -> Mastery ->
HelpNeed -> Policy -> back to Surface). This slice defines the shapes only; the
deterministic verify/mastery/policy logic that fills them in does not exist yet
(later slices), so the route returns a clearly-marked stub (see ``service.py``).

Why Pydantic v2 specifically: TECH_STACK §3 makes Pydantic the typed boundary of
the API, and TECH_STACK §2 generates the frontend TypeScript types from these
same schemas — one source of truth for what a ``TurnRequest``/``TurnResponse``
looks like on both sides. That is also why every field is explicitly typed (no
loose ``dict``/``Any``): a loose field would generate a useless ``any`` in TS and
defeat the contract (CLAUDE.md §6 "no any without justification").

No SymPy, no LLM, no DB here — those are other layers (CLAUDE.md §7,
ARCHITECTURE.md §14). This module is pure data shape.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# We reuse the Layer-1 typed handles as the field types so the API speaks the
# same KC ids and representation names as the domain model — the registry is the
# single source of truth (ARCHITECTURE.md §4). Importing the enums (not raw
# strings) keeps the contract aligned with the domain and the generated TS types.
from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.domain.problem_generators import AnswerKind

# ErrorType IS the domain verifier's ErrorCategory (Slice 1.4). The verifier owns
# the §3.6 routing alphabet; the API speaks the very same enum so the wire contract
# and the policy that routes on it cannot drift. (Reconciles the Slice 1.9 flag —
# the local placeholder enum is gone; this is now the single source of truth.)
from app.domain.verifier import ErrorCategory as ErrorType

# CourseNodeStatus is the mastery layer's course-map status enum (Slice CP.A.1). The wire
# reuses it as the field type — same single-source-of-truth principle as the KC/AnswerKind
# handles above — so the API and the generated TS types speak the exact statuses the engine
# derives, and the two can't drift.
from app.mastery.course_map import CourseNodeStatus

# UnitStatus is owned by mastery/ (the unit-progress overlay's status vocabulary — see
# ``unit_progress.build_unit_progress``). The unit-product wire reuses it as the field type,
# the same single-source-of-truth principle as ``CourseNodeStatus`` above, so the API and the
# generated TS types speak the exact unit statuses the overlay derives and the two can't drift.
from app.mastery.unit_progress import UnitStatus

# SurfaceState is owned by policy/ (the adaptation policy's vocabulary — it routes
# between the five states, ARCHITECTURE.md §7); the API imports it forward so the
# wire speaks the same enum the policy and tutor do (single source of truth, §4).
from app.policy.surface_states import SurfaceState


class ActionType(StrEnum):
    """What kind of learner action this turn carries (ARCHITECTURE.md §10 step 1).

    The learner either submits an answer to the current problem, or asks for a
    hint. Splitting the two is what lets the mastery model later down-weight
    hinted attempts and enforce the ">=1 unassisted correct" rule (ARCHITECTURE.md
    §6 rule 3) — the route does not implement that here, but the contract must be
    able to express the distinction.
    """

    SUBMIT_ANSWER = "submit_answer"
    REQUEST_HINT = "request_hint"


# ErrorType is imported above from the domain verifier (Slice 1.4's ErrorCategory):
# its values are none/magnitude/operation/format/other, the closed §3.6 routing set,
# and the verifier decides which applies. The API does not redefine it.


class InterventionKind(StrEnum):
    """Which proactive-intervention form was offered (PROJECT.md §3.7).

    ``INLINE_ASSERTION`` is the first fire — a partial scaffold shown *within* the
    workspace (Maniktala et al. 2020; §3.8 refuse-rule 6). v1 fills it with the
    pre-written conceptual nudge (Slice 3.8); the LLM-mediated partial worked step lands
    at Slice 5.6 (no LLM in the turn loop, §8.1). ``CONCEPTUAL_PROMPT`` is the ~30s-no-
    response escalation (§3.7 step 2), reserved here and surfaced when the UI timer lands.
    """

    INLINE_ASSERTION = "inline_assertion"
    CONCEPTUAL_PROMPT = "conceptual_prompt"


class InterventionView(BaseModel):
    """A proactively-offered help nudge (Slice 4.5), or absent when none is offered.

    Distinct from the reactive ``hint`` (which answers an explicit REQUEST_HINT): this is
    help the system offers *unasked* after the §3.7 sustained-signal gate fires on the
    HelpNeed stream. Present only when the session's proactive arm is enabled AND the gate
    fired; ``null`` otherwise (the observe-only default). The surface renders ``text``
    inline in the workspace, never as a modal (§3.8 refuse-rule 6).
    """

    model_config = ConfigDict(extra="forbid")

    kind: InterventionKind = Field(description="Which intervention form was offered (§3.7).")
    text: str = Field(min_length=1, description="The pre-written nudge text (no LLM, §8.1).")


class ProblemView(BaseModel):
    """The learner-facing view of one presented problem (ARCHITECTURE.md §10 step 12).

    This is what the surface needs to RENDER a problem — the readable subset of the
    domain ``Problem`` (problem_generators.py). It deliberately carries no answer,
    operands, or SymPy values: correctness is the domain verifier's job (CLAUDE.md
    §8.2), so the wire never ships the answer to the client where it could leak.

      - ``problem_id`` echoes back on the next ``TurnRequest`` so the loop knows
        which problem an answer is for.
      - ``kc`` / ``surface_format`` let the surface pick the right workspace
        (symbolic editor / number line / fraction bars — §3.5).
      - ``statement`` is the kid-friendly text shown to the learner.
      - ``tick_segments`` is a NUMBER-LINE rendering hint: how many equal intervals
        to divide the 0–1 line into. ``None`` for non-number-line problems.
    """

    model_config = ConfigDict(extra="forbid")

    problem_id: str = Field(min_length=1, description="Stable id; echoed on the next turn.")
    kc: KnowledgeComponentId
    surface_format: Representation = Field(description="Representation to render (§3.5).")
    statement: str = Field(min_length=1, description="Kid-friendly problem text.")
    answer_kind: AnswerKind = Field(
        default=AnswerKind.NUMERIC,
        description="How to answer: a numeric fraction (default) or yes/no buttons.",
    )
    yes_no_relation: str = Field(
        default="equal",
        description=(
            "For a yes/no item, what it asks: 'equal' (same amount?) or 'greater' (a > b?). "
            "Lets the surface label the question accurately. 'equal' for non-yes/no items."
        ),
    )
    # The number-line surface needs a candidate set to snap a drag onto BEFORE the
    # answer reaches the domain (the verifier does exact Rational equality, no
    # tolerance — verifier.py docstring). The candidate set is k/tick_segments for
    # k=0..tick_segments; the displayed fraction p/q is exactly one of them because
    # the generator displays the reduced target and tick_segments == its denominator.
    # None when the problem is not a number-line placement (no snap grid needed).
    tick_segments: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Number-line only: equal intervals PER UNIT to snap a drag to (the target's "
            "denominator); null otherwise. The total ticks shown is "
            "``(axis_max - axis_min) * tick_segments``."
        ),
    )
    axis_min: int = Field(
        default=0,
        description=(
            "Number-line only: the left end of the axis. 0 for a proper-fraction or improper "
            "placement; negative for a negative target (e.g. −2 to place −5/4) — CCSS 6.NS.6. "
            "Ignored by non-number-line surfaces."
        ),
    )
    axis_max: int = Field(
        default=1,
        description=(
            "Number-line only: the right end of the axis. 1 for a proper fraction, 2 for an "
            "improper target (e.g. 5/4), so the marker can sit PAST the '1' whole. Ignored by "
            "non-number-line surfaces."
        ),
    )
    given_denominator: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Equivalence fill-the-top only: the denominator named in the question "
            "('?/8'), pre-filled and locked so the learner enters only the numerator. "
            "Null otherwise."
        ),
    )


class WorkedStepView(BaseModel):
    """One revealed step of an S4 worked example, on the wire (Slice 3.6 → API).

    The renderable subset of a domain ``WorkedStep`` (``tutor/worked_example.py``): the
    kid-facing ``shown`` step content and the one-line conceptual ``why_prompt`` that
    accompanies it. The §3.5 S4 requirement is that EVERY revealed step carries a "why did
    this work?" prompt, so both fields are required. The domain ``WorkedStep`` also carries
    a SymPy ``revealed_value`` for self-consistency; that is internal and never crosses the
    wire (it would leak intermediate magnitudes — the surface reveals steps one at a time,
    §3.5 S4).
    """

    model_config = ConfigDict(extra="forbid")

    shown: str = Field(min_length=1, description="The kid-facing step content (§3.5 S4).")
    why_prompt: str = Field(
        min_length=1,
        description="The one-line 'why did this work?' prompt for this step (§3.5 S4).",
    )


class RouteOptionView(BaseModel):
    """One Turn-0 routing option for the cold-start menu (decision 0.D.2).

    The kid-friendly view of a tutor ``RouteOption``: the surface renders ``prompt``
    and visually de-emphasizes the single ``is_unsure_default`` option (0.D.2: no
    quiz/diagnostic framing — that is a presentation choice the surface makes). The
    client sends ``key`` back on ``POST /session`` to start in that route; it never
    sends the KC directly, so the routing menu stays the single source of truth.
    """

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, description="Opaque option id; sent back to start a session.")
    prompt: str = Field(min_length=1, description="Kid-friendly option text (no curriculum terms).")
    is_unsure_default: bool = Field(
        description="The single de-emphasized 'I'm not sure' default (0.D.2).",
    )


class StartSessionRequest(BaseModel):
    """Begin a session — EITHER from a Turn-0 routing choice (0.D.2) OR a course-map skill.

    Two mutually-exclusive entry points (exactly one of ``route_key`` / ``kc``):

      - ``route_key`` — the chosen Turn-0 option key (the cold-start path). The KC, calibration
        item, and BKT prior are all derived server-side from the locked routing table (tutor
        ``from_route``), so the prior-not-commitment seeding stays authoritative (0.D.2).
      - ``kc`` — start a lesson DIRECTLY for this knowledge component (the course-map node
        launch, §3.13). The server presents a generated first problem for the KC in its first
        live representation; no skill claim is seeded (studying a skill is not a claim to know
        it).
    """

    model_config = ConfigDict(extra="forbid")

    route_key: str | None = Field(
        default=None,
        min_length=1,
        description="The chosen Turn-0 option key (0.D.2). Provide this OR kc, not both.",
    )
    kc: KnowledgeComponentId | None = Field(
        default=None,
        description="Start a lesson directly for this KC (course map). Provide this OR route_key.",
    )
    proactive_enabled: bool = Field(
        default=False,
        description=(
            "Opt into the proactive HelpNeed arm for this session (Slice 4.5). Default "
            "OFF = observe-only (RESEARCH.md §7.5); set by the Slice 5.4 A/B harness or a "
            "demo. When OFF the session never sees a proactive intervention."
        ),
    )


class StartSessionResponse(BaseModel):
    """The freshly-started session and its Turn-1 calibration problem (0.D.2).

    Returns the opaque ``session_id`` the surface threads onto every subsequent
    ``TurnRequest``, the starting ``surface_state`` (S1 — the default fluent state,
    ARCHITECTURE.md §7), and the locked Turn-1 calibration ``problem`` for the route
    (0.D.2). One round-trip puts the learner in front of their first problem.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, description="Opaque session id (TECH_STACK §9).")
    surface_state: SurfaceState = Field(description="The starting surface state (S1, §7).")
    problem: ProblemView = Field(
        description="The Turn-1 calibration problem for the route (0.D.2)."
    )


class MasterySnapshot(BaseModel):
    """A per-KC mastery readout returned to the surface (ARCHITECTURE.md §6).

    The response carries a snapshot so the UI can show mastery progress without a
    second round-trip. ``probability`` is the BKT probability for the KC and
    ``mastered`` is the model's *declared* mastery (which requires more than the
    probability threshold — §6 rules 1-4). This slice only fixes the shape; the
    real values come from the mastery model (a later slice).
    """

    # Reject unknown keys: a strict, generatable contract.
    model_config = ConfigDict(extra="forbid")

    kc_id: KnowledgeComponentId
    probability: float = Field(ge=0.0, le=1.0, description="BKT mastery probability for this KC.")
    mastered: bool = Field(description="Whether the mastery model has *declared* mastery (§6).")


class TurnRequest(BaseModel):
    """One learner action entering the turn loop (ARCHITECTURE.md §10 steps 1-2).

    This is the ``submit`` payload the surface sends. Fields mirror exactly what
    the deterministic path needs downstream:

      - ``session_id`` / ``problem_id`` identify *who* and *which problem*
        (TECH_STACK §9: v1 uses session-id-based identification, no auth).
      - ``action`` is submit-vs-hint (drives the unassisted-attempt rule, §6).
      - ``submitted_answer`` is the raw answer string the verifier checks with
        SymPy (domain layer; never validated here — that is §9's job).
      - ``surface_state`` is the state the learner is *currently* in, so the
        policy can compute the transition relative to it (§7).
      - ``latency_ms`` feeds both the engagement floor (§6) and the HelpNeed
        feature vector (§8) — it is evidence, so it is required.
      - ``hint_used`` records whether the learner had a hint on this problem, so
        the attempt can be down-weighted (§6 rule 3).
    """

    # Unknown keys are a contract violation, not silently dropped.
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, description="Opaque learner-session id (TECH_STACK §9).")
    problem_id: str = Field(min_length=1, description="Id of the problem this action answers.")
    action: ActionType
    # Optional because a REQUEST_HINT action carries no answer. The route does not
    # enforce the cross-field rule (answer required iff submit) at this slice — that
    # is business logic for the verify/policy services; the contract just allows both.
    submitted_answer: str | None = Field(
        default=None,
        description="Raw learner answer; SymPy (domain) decides correctness, not the API.",
    )
    surface_state: SurfaceState = Field(
        description="The surface the learner is currently in (§7).",
    )
    latency_ms: int = Field(
        ge=0,
        description="Time the learner took; feeds engagement floor (§6) + HelpNeed (§8).",
    )
    hint_used: bool = Field(
        default=False,
        description="Whether a hint was shown for this problem (down-weights the attempt, §6).",
    )


class TurnResponse(BaseModel):
    """The turn loop's reply to the surface (ARCHITECTURE.md §10 steps 11-12).

    This is the "next state + labeled feedback" the API returns. Fields mirror
    the deterministic outputs of the loop:

      - ``correct`` / ``error_type`` are the verifier's verdict (§10 step 4).
      - ``next_surface_state`` is the policy's chosen transition (§10 step 9).
      - ``feedback`` is the *labeled* feedback string — refuse-rule 4 requires a
        one-line label explaining any transition (§7). It is plain text here; the
        LLM surface layer may later replace/augment it, but only *after* the
        deterministic path (§10 ``opt`` block, ARCHITECTURE.md §14 invariant 1).
      - ``hint`` is optional natural-language help, present only when help is
        shown (§10 ``opt`` block).
      - ``mastery`` is the per-KC snapshot (§6).
    """

    # Strict, fully-enumerated response shape.
    model_config = ConfigDict(extra="forbid")

    correct: bool = Field(
        description="Whether the submitted answer was correct (SymPy verdict, §9).",
    )
    error_type: ErrorType = Field(
        default=ErrorType.NONE,
        description="Labeled error class when incorrect; NONE when correct (§10).",
    )
    next_surface_state: SurfaceState = Field(
        description="The surface state to show next (policy, §7).",
    )
    feedback: str = Field(
        description="One-line labeled feedback explaining the transition (refuse-rule 4, §7).",
    )
    hint: str | None = Field(
        default=None,
        description="Optional natural-language hint, shown only when help is offered (§10).",
    )
    mastery: list[MasterySnapshot] = Field(
        default_factory=list,
        description="Per-KC mastery snapshot for the affected KC(s) (§6).",
    )
    help_need: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Observe-only P(unproductive) from the HelpNeed predictor for the NEXT "
            "problem, given this session's history (Slice 4.4.1). It is reported, not "
            "acted on by the surface. null on a hint turn (no answer was submitted, so "
            "the history is unchanged)."
        ),
    )
    intervention: InterventionView | None = Field(
        default=None,
        description=(
            "A proactively-offered help nudge (Slice 4.5), present only when the "
            "session's proactive arm is enabled AND the §3.7 sustained-signal gate fired "
            "on the HelpNeed stream. null in the observe-only default. Rendered inline "
            "in the workspace (§3.8 refuse-rule 6)."
        ),
    )
    next_problem: ProblemView | None = Field(
        default=None,
        description=(
            "The next problem to present after this turn, or null when the loop has "
            "nothing further to serve (e.g. an unrecognized session). The surface "
            "renders it directly; the deterministic loop chose it (§10 step 12)."
        ),
    )
    worked_example: list[WorkedStepView] = Field(
        default_factory=list,
        description=(
            "The ordered worked steps to reveal when ``next_surface_state`` is "
            "S4_worked_example; empty otherwise. This is the worked solution of the "
            "problem the learner JUST got stuck on — NOT ``next_problem`` (which is the "
            "fresh practice item and whose answer must not be revealed). The surface "
            "reveals these one step at a time, each with its 'why?' prompt (§3.5 S4). "
            "May be empty even on an S4 turn when the stuck problem's KC procedure has no "
            "buildable worked example (e.g. a yes/no item with no operand pair) — the "
            "surface then shows S4 without a walkthrough rather than the loop failing."
        ),
    )
    lesson_complete: bool = Field(
        default=False,
        description=(
            "True on the turn that FINISHES the lesson — i.e. the goal KC just became "
            "CONFIRMED (the S5 transfer probe passed). The bounded-lesson terminal signal "
            "(CP.B; PROJECT.md §3.13): the surface shows the 'you finished it' screen and "
            "routes the learner home instead of presenting yet another practice problem. "
            "``next_problem`` may still be populated as an optional 'keep practicing' item, "
            "but a complete lesson must not silently loop on. False on every other turn."
        ),
    )


class ArmVerdictView(BaseModel):
    """One arm's mastery verdict for one persona, pre-formatted for display.

    The view layer (``api/eval_view``) maps the raw eval outcome to a label + a tone the
    surface can render directly — the frontend stays presentation-only (CLAUDE.md §7)."""

    model_config = ConfigDict(extra="forbid")

    arm: str = Field(description="Adaptive | Chat | Static")
    verdict: str = Field(description="Short display label, e.g. 'Denied ✓' or 'N/A'.")
    tone: str = Field(description="good | bad | neutral | pending — drives the surface styling.")
    detail: str = Field(description="One-line explanation (e.g. 'blocked at: transfer_probe').")


class PersonaComparisonView(BaseModel):
    """One persona's row in the three-arm comparison: who, what it attacks, the problems it
    saw, and each arm's verdict."""

    model_config = ConfigDict(extra="forbid")

    persona_name: str
    attacks: str
    problems: list[str] = Field(description="The problem statements this persona was given.")
    adaptive: ArmVerdictView
    chat: ArmVerdictView
    static: ArmVerdictView


class MetricArmVerdictView(BaseModel):
    """One arm's verdict on one pre-registered metric, pre-formatted for display.

    Like ``ArmVerdictView`` but for the per-metric table (Slice 5.3.3): a short status label
    plus a tone that drives styling (``good`` enforced / ``bad`` missed / ``neutral`` no
    mechanism / ``pending`` predicted)."""

    model_config = ConfigDict(extra="forbid")

    arm: str = Field(description="Adaptive | Chat | Static")
    status: str = Field(description="Short label, e.g. 'Enforced', 'Missed ✗', 'Max ✗', 'N/A'.")
    tone: str = Field(description="good | bad | neutral | pending — drives the surface styling.")
    detail: str = Field(description="One-line explanation of the verdict.")


class MetricComparisonView(BaseModel):
    """One of the five remaining pre-registered metrics across the three arms (RESEARCH.md §9).

    The adaptive verdict is derived from the actual deterministic run (the rule that blocked the
    adversary); the chat verdict from the recorded live run (or the §9 prediction); the static
    verdict from the arm's architecture. The headline (false-positive mastery) is the per-persona
    table above."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(description="Stable metric id, e.g. 'hint_dependence'.")
    name: str = Field(description="Display name, e.g. 'Hint dependence at mastery'.")
    adversary: str = Field(description="The persona that attacks this metric.")
    adaptive: MetricArmVerdictView
    chat: MetricArmVerdictView
    static: MetricArmVerdictView


class ThreeArmComparisonView(BaseModel):
    """The full three-arm comparison for display (Slice 5.3, PROJECT.md §3.11).

    The adaptive and static columns are computed live and deterministically; the chat
    column is the pre-registered prediction until the cost-gated live LLM run
    (``chat_live`` says which)."""

    model_config = ConfigDict(extra="forbid")

    rows: list[PersonaComparisonView]
    total: int = Field(description="Number of personas (arms are scored over these).")
    adaptive_false_positives: int
    chat_false_positives: int | None = Field(
        default=None,
        description="Chat false positives from the live run, or null when still the prediction.",
    )
    chat_live: bool = Field(description="True once the chat column reflects a real LLM run.")
    headline: str = Field(description="The §3.11 pitch summary for the header.")
    metrics: list[MetricComparisonView] = Field(
        default_factory=list,
        description="The five remaining pre-registered metrics, each across the three arms.",
    )


class BenchmarkPersonaSummaryView(BaseModel):
    """One entry in the benchmark-theater persona switcher: who, and the mastery dimension
    they attack (PROJECT.md §4.2). Display-ready; the surface renders these verbatim."""

    model_config = ConfigDict(extra="forbid")

    persona_id: str = Field(description="Opaque persona id; sent back to load that transcript.")
    persona_name: str = Field(description="Display name, e.g. 'Procedure Priya'.")
    attacks: str = Field(description="The one mastery rule/dimension this learner attacks.")
    kc: str = Field(description="The knowledge component the run targets.")


class AdaptiveTurnView(BaseModel):
    """One adaptive-arm turn, display-ready (Slice 5.3 theater). The verified path: the
    persona's answer, the SymPy verdict, the labelled error class, the one-line feedback, the
    resulting surface state, and the §3.4 effort/scaffold flags (hinted, below engagement floor)."""

    model_config = ConfigDict(extra="forbid")

    problem_statement: str
    format_label: str = Field(description="The representation shown, e.g. 'Number line'.")
    student_answer: str = Field(description="The persona's submitted answer, or '—' for none.")
    correct: bool = Field(description="The SymPy verdict for this turn (domain decides).")
    result_label: str = Field(description="'Correct' or the labelled error, e.g. 'Magnitude'.")
    feedback: str = Field(description="The tutor's one-line labelled feedback for the turn.")
    state_label: str = Field(description="Surface state after the turn, e.g. 'S1 · symbolic'.")
    hint_used: bool = Field(description="Whether the attempt was scaffolded (down-weighted).")
    below_engagement_floor: bool = Field(
        description="Whether the answer landed under the 2s engagement floor (non-evidence)."
    )
    latency_label: str = Field(description="How long the persona 'thought', e.g. '12.0s'.")


class ChatTurnView(BaseModel):
    """One chat-arm exchange, display-ready. ``tutor_reply`` is an ILLUSTRATIVE placeholder in
    the offline theater (no live model is called) — the arm's real signal is its self-
    certification verdict on the transcript, not this wording (CLAUDE.md §5, §8.2)."""

    model_config = ConfigDict(extra="forbid")

    problem_statement: str
    student_answer: str = Field(description="The persona's typed answer (same as every arm).")
    tutor_reply: str = Field(description="Illustrative chat reply (offline placeholder, labelled).")


class StaticTurnView(BaseModel):
    """One static-arm screen, display-ready: the fixed worked-example walkthrough shown, and the
    answer the learner submitted — recorded UNVERIFIED (the arm has no verifier, by design)."""

    model_config = ConfigDict(extra="forbid")

    problem_statement: str
    walkthrough: str = Field(description="The pre-rendered linear walkthrough shown for the item.")
    student_answer: str = Field(description="The submitted answer, recorded but never checked.")


class TransferProbeStepView(BaseModel):
    """One item of the S5 transfer probe, made visible (PROJECT.md §3.9): the step that tests
    understanding rather than computation — a same-skill-new-format item, or an error-finding
    'Tim says ¼+¼=2/8, why is he wrong?' item — with its pass/fail and a plain-language line."""

    model_config = ConfigDict(extra="forbid")

    item_type: str = Field(description="'representation' (new format) or 'error_finding'.")
    prompt: str = Field(description="What the learner was shown for this probe item.")
    surface_format: str = Field(description="The representation of the item, e.g. 'number_line'.")
    passed: bool = Field(description="Whether the learner passed this transfer item.")
    detail: str = Field(description="Plain-language line on what the persona did here.")


class BenchmarkTranscriptView(BaseModel):
    """One persona run through all three arms, turn by turn, with each arm's verdict — the
    on-screen "benchmark theater" (a teaching view of Slice 5.3 / PROJECT.md §3.11).

    The adaptive verdict is the real two-stage gate (provisional ``declare_mastery`` then the
    S5 transfer probe); the chat verdict is the recorded LIVE self-certification (or the §9
    prediction when no live run is committed); static has no mastery construct by design."""

    model_config = ConfigDict(extra="forbid")

    persona_id: str
    persona_name: str
    attacks: str
    kc: str
    problems: list[str] = Field(description="The problem statements, the same set fed every arm.")

    adaptive_turns: list[AdaptiveTurnView]
    adaptive_verdict: str = Field(description="Display label, e.g. 'Denied ✓ — refused mastery'.")
    adaptive_tone: str = Field(description="good | bad — drives the surface styling.")
    adaptive_why: str = Field(description="Plain-language, demo-ready explanation of the verdict.")
    adaptive_blocked_at: str = Field(
        description="Stage that caught the learner (provisional | transfer_probe | NOT BLOCKED)."
    )
    adaptive_reasons: list[str] = Field(
        default_factory=list, description="The exact rule(s) that denied mastery."
    )
    adaptive_probe_ran: bool = Field(
        description="True when the learner reached provisional and the transfer probe ran."
    )
    adaptive_probe_steps: list[TransferProbeStepView] = Field(
        default_factory=list, description="The transfer-probe items, shown when the probe ran."
    )

    chat_turns: list[ChatTurnView]
    chat_verdict: str = Field(description="Display label, e.g. 'Mastered ✗ (false positive)'.")
    chat_tone: str = Field(description="good | bad | pending — drives the surface styling.")
    chat_why: str = Field(description="Plain-language, demo-ready explanation of the chat verdict.")
    chat_self_assessment: str = Field(
        description="The chat tutor's own MASTERED/NOT_YET word (or a prediction note)."
    )
    chat_live: bool = Field(description="True when the verdict reflects a real recorded LLM run.")
    chat_illustrative_note: str = Field(
        description="The standing caveat that the chat replies above are offline placeholders."
    )

    static_turns: list[StaticTurnView]
    static_verdict: str = Field(description="Always 'N/A — certifies nothing' (no mastery model).")
    static_tone: str = Field(description="neutral — the static arm has no verdict to style.")
    static_note: str = Field(description="One-line note that the arm never checks or tracks.")


class HwQuestionView(BaseModel):
    """One homework question, for the desktop checklist + the mobile capture screen."""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0, description="0-based position in the set (the grading/scan index).")
    statement: str = Field(description="The kid-facing problem text.")
    is_target: bool = Field(
        description="True for the anchored target skill; False for spaced review."
    )


class HwAssignRequest(BaseModel):
    """Start a homework run for a skill (the desktop, at lesson end). Returns a token for the QR."""

    model_config = ConfigDict(extra="forbid")

    kc: KnowledgeComponentId = Field(description="The just-learned skill the set is anchored to.")
    session_id: str | None = Field(
        default=None, description="Optional session this homework belongs to (carried for context)."
    )


class HwAssignResponse(BaseModel):
    """The freshly-created homework run: the upload token (QR payload) + the question list."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, description="One-time upload token; the QR encodes it.")
    target_kc: str = Field(description="The anchored target skill.")
    questions: list[HwQuestionView] = Field(description="The set, in order (target first).")


class HwSubmitRequest(BaseModel):
    """The phone's page photos for a run — base64-encoded images (no multipart dependency)."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, description="The run's upload token (from the QR).")
    pages: list[str] = Field(
        min_length=1,
        description="One or more page images, base64-encoded (data may be raw or data-URL).",
    )


class HwSubmitResponse(BaseModel):
    """Acknowledges the upload and reports the new run state (``ready_for_review``)."""

    model_config = ConfigDict(extra="forbid")

    state: str = Field(
        description="Run state after the upload (waiting | ready_for_review | graded)."
    )
    question_count: int = Field(ge=0, description="How many questions the draft now covers.")


class HwDraftItemView(BaseModel):
    """One question's DRAFT transcription, shown for the read-back ('I read this as 1/4 — yes?')."""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    statement: str
    is_target: bool
    read_as: str | None = Field(
        default=None, description="What the scanner read for this question; null if unreadable."
    )


class HwConfirmAnswer(BaseModel):
    """One learner-confirmed answer from the read-back (may differ from the draft if corrected)."""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    answer: str | None = Field(
        default=None, description="The confirmed answer text, or null if left blank."
    )


class HwConfirmRequest(BaseModel):
    """The confirmed answers to grade (after the desktop read-back)."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1)
    answers: list[HwConfirmAnswer] = Field(description="Confirmed answer per question index.")


class HwQuestionResultView(BaseModel):
    """One graded question — for the 1-on-1 walk-through (right or wrong)."""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    statement: str
    is_target: bool
    submitted: str | None
    correct: bool
    unreadable: bool


class HwGradeResultView(BaseModel):
    """The graded set + the ★★ verdict (target-skill score ≥ 0.8 = passed)."""

    model_config = ConfigDict(extra="forbid")

    results: list[HwQuestionResultView]
    target_correct: int = Field(ge=0)
    target_total: int = Field(ge=0)
    target_score: float = Field(ge=0.0, le=1.0)
    passed: bool = Field(description="True = ★★ earned; False = redo the lesson + a fresh set.")


class HwStatusResponse(BaseModel):
    """What the desktop polls: the run state, the draft (for the read-back), and the verdict."""

    model_config = ConfigDict(extra="forbid")

    state: str = Field(description="waiting | ready_for_review | graded.")
    draft: list[HwDraftItemView] = Field(
        default_factory=list, description="The transcribed draft (present once photos are in)."
    )
    result: HwGradeResultView | None = Field(
        default=None, description="The graded verdict (present once confirmed)."
    )


class InteractionEventIn(BaseModel):
    """One raw behavioral event the surface emits, on the wire (Slice PL.2).

    The fine-grained telemetry beyond the coarse ``TurnRequest``: a number-line drag, an
    answer edit, focus/blur, idle, problem-presented, submit, hint-request, first-interaction.
    Persisted OFF the turn loop (ARCHITECTURE.md §14 invariant 7) — this schema is captured and
    stored, never fed into verify/mastery/policy.

      - ``event_type`` is the open tag (a string, not an enum) so the surface can add a kind
        without a backend change; required and non-empty.
      - ``payload`` is the free-form detail for the event. It is intentionally an open object —
        the whole point of the capture table is to record arbitrary per-event detail PL.4 can
        mine later, so a fixed schema here would defeat it. This is the one justified ``Any`` in
        the contract (CLAUDE.md §6): it generates a permissive TS object, which is correct for an
        open telemetry payload. Defaults to ``{}`` so a bare event (e.g. ``focus``) needs no body.
      - ``client_ts`` is when the client recorded the event, if it sends one; the server stamps
        its own authoritative ``server_ts`` on receipt regardless.
    """

    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(min_length=1, description="Open event tag, e.g. 'numberline_drag'.")
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form per-event detail (open object — see class doc, §8.6).",
    )
    client_ts: datetime | None = Field(
        default=None, description="When the client recorded the event; server stamps its own too."
    )


# Cap a single batch so one POST cannot persist an unbounded number of rows (a cheap abuse
# guard for an unauthenticated endpoint — CLAUDE.md §8.6 keeps it a simple constant, not a
# rate-limiter). The surface flushes small buffers frequently; 200 is comfortably above a
# normal flush and well below an abusive payload.
_MAX_EVENTS_PER_BATCH = 200


class EventBatchRequest(BaseModel):
    """A buffered batch of interaction events for one session (Slice PL.2).

    The surface accumulates events client-side and flushes them in one POST to ``/events``.
    ``session_id`` is the opaque session id the client already holds (the same value it threads
    onto every ``TurnRequest``); telemetry is lenient, so an unknown ``session_id`` is NOT an
    error — the server persists what it can and still accepts the batch (the endpoint never 404s).
    The list is capped (``max_length``) so a giant batch can't be abused.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, description="Opaque session id (TECH_STACK §9).")
    events: list[InteractionEventIn] = Field(
        max_length=_MAX_EVENTS_PER_BATCH,
        description=f"The buffered events to record (≤{_MAX_EVENTS_PER_BATCH} per batch).",
    )


class EventIngestResponse(BaseModel):
    """The ``/events`` reply: how many events were attempted-persisted (Slice PL.2).

    Returned with HTTP 202 ACCEPTED — the server has accepted the batch for best-effort
    persistence off the turn loop, not confirmed durable storage (invariant 7). ``accepted`` is
    the count the server tried to write; it is 0 when no DB is wired (the in-memory demo) or for
    an empty batch. A persistence failure is swallowed, so a non-zero ``accepted`` is "attempted",
    not a durability guarantee — which is exactly the contract telemetry needs.
    """

    model_config = ConfigDict(extra="forbid")

    accepted: int = Field(ge=0, description="Number of events accepted for best-effort persist.")


class StudyPlanView(BaseModel):
    """What a returning learner should do next (Slice 6.x — spaced repetition).

    Derived from the persisted mastery (PL.1 rows): ``due_reviews`` are confirmed skills whose
    retention has decayed since last practice (most-decayed first — the "space" in spaced
    repetition); ``unlocked_next`` are new skills whose prerequisites are confirmed, in
    algebra-spine order; ``recommended`` is the single best next action (a due review if any,
    else the earliest unlocked new skill, else null when everything is confirmed and fresh).
    KC ids are the catalog strings. Off the turn loop; advisory only.
    """

    model_config = ConfigDict(extra="forbid")

    due_reviews: list[str] = Field(
        default_factory=list,
        description="Confirmed KCs due for review, most-decayed first (spaced repetition).",
    )
    unlocked_next: list[str] = Field(
        default_factory=list,
        description="New KCs whose prerequisites are confirmed, in algebra-spine order.",
    )
    recommended: str | None = Field(
        default=None,
        description="The single best next KC (due review > new skill > null if all done/fresh).",
    )


class CourseNodeView(BaseModel):
    """One KC's place on the course map (Slice CP.A.1 — the course-product home screen).

    Each node carries enough to render a learning-path stop: its KC id + human-readable
    ``skill_name``/``description`` (from the KC registry), its ``status`` (the engine-derived
    ``CourseNodeStatus`` — locked/available/in_progress/mastered/due_review), the ``prerequisites``
    to draw as incoming edges, and the stored mastery ``probability`` for a progress indicator
    (``null`` if the learner hasn't started this skill). Derived from existing engine state only
    (PROJECT.md §3.13: reuse, never rebuild); off the turn loop, advisory.
    """

    model_config = ConfigDict(extra="forbid")

    kc_id: KnowledgeComponentId
    skill_name: str = Field(description="Human-readable skill name (KC registry).")
    description: str = Field(description="One-sentence description of the skill (KC registry).")
    status: CourseNodeStatus = Field(description="The node's status on the learning path.")
    prerequisites: list[KnowledgeComponentId] = Field(
        default_factory=list,
        description="KCs that must be confirmed before this one is suggested (the incoming edges).",
    )
    probability: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Stored BKT mastery level for a touched skill; null if not yet started.",
    )


class CourseView(BaseModel):
    """The whole learning path for one learner (Slice CP.A.1).

    ``nodes`` is the full catalog of KCs in teaching (algebra-spine) order, each with its status
    — so the frontend can render the course map as nodes + prerequisite edges and use it as the
    post-sign-in home. Always contains every KC (a path needs all its stops), even for a brand-new
    learner (root available, rest locked).
    """

    model_config = ConfigDict(extra="forbid")

    nodes: list[CourseNodeView] = Field(
        default_factory=list,
        description="Every KC as a path node, in teaching order, with its status.",
    )


class LessonView(BaseModel):
    """One lesson within a unit, with the learner's status on its KC (Slice DAT.9).

    The renderable subset of a catalog ``CatalogLesson`` joined to its rolled-up
    ``LessonProgress`` (``mastery/unit_progress``): the catalog ``title`` + dual-coverage
    standard codes for display, plus the learner's per-lesson ``status``/``probability`` derived
    from the lesson's KC course-map node. ``kc_id`` is the raw catalog string (a real KC id, a
    forward-declared Wave-3 string, or ``null`` for an interleave-gate lesson); ``ccss_code`` /
    ``teks_code`` are ``null`` where a lesson is single-framework (the honest exceptions in the
    catalog). ``probability`` is ``null`` until the KC is touched (or for an unmapped lesson).
    Derived from existing engine state only (PROJECT.md §3.13); off the turn loop, advisory.
    """

    model_config = ConfigDict(extra="forbid")

    lesson_slug: str = Field(description="Stable lesson slug (unique within the unit).")
    title: str = Field(description="Human-readable lesson title (catalog).")
    kc_id: str | None = Field(
        default=None,
        description="The lesson's catalog KC string, or null if it maps to no KC yet.",
    )
    ccss_code: str | None = Field(
        default=None,
        description="Common Core (CCSS) standard code, or null if single-framework.",
    )
    teks_code: str | None = Field(
        default=None,
        description="Texas (TEKS) standard code, or null if single-framework.",
    )
    status: CourseNodeStatus = Field(
        description="The learner's status on this lesson's KC (the course-map node's status).",
    )
    probability: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Stored BKT mastery level for the lesson's KC; null if not yet started.",
    )


class UnitView(BaseModel):
    """One unit with the learner's rolled-up progress, no lessons (Slice DAT.8).

    The unit-card view for the unit list: the catalog ``title``/``description``/``order`` +
    dual-coverage cluster codes, plus the learner's aggregated ``status``/``percent_complete``
    (from ``mastery/unit_progress``) and ``lesson_count``. ``assigned`` is ``true`` only for the
    signed-in learner's teacher-assigned unit (Slice DAT.10), ``false`` for every other unit and
    for an anonymous caller. ``ccss_cluster``/``teks_cluster`` are ``null`` for a single-framework
    unit (e.g. TEKS-only integer arithmetic). Derived from the catalog + course map only
    (PROJECT.md §3.13: reuse, never rebuild); off the turn loop, advisory.
    """

    model_config = ConfigDict(extra="forbid")

    unit_slug: str = Field(description="Stable unit slug (unique across the catalog).")
    title: str = Field(description="Human-readable unit title (catalog).")
    description: str = Field(description="Short description of the unit (catalog).")
    order: int = Field(description="Display/teaching order within the catalog (1-based).")
    ccss_cluster: str | None = Field(
        default=None,
        description="Common Core (CCSS) cluster code, or null if single-framework.",
    )
    teks_cluster: str | None = Field(
        default=None,
        description="Texas (TEKS) cluster code, or null if single-framework.",
    )
    status: UnitStatus = Field(description="The learner's aggregated status on this unit.")
    percent_complete: float = Field(
        ge=0.0,
        le=100.0,
        description="Percent of the unit's lessons completed, in [0, 100].",
    )
    lesson_count: int = Field(ge=0, description="Number of lessons in the unit.")
    assigned: bool = Field(
        description="True only for the signed-in learner's teacher-assigned unit (DAT.10).",
    )


class UnitListView(BaseModel):
    """The full unit catalog for one learner, with progress + assignment (Slice DAT.8).

    ``units`` is every catalog unit in teaching order, each a ``UnitView`` with the learner's
    rolled-up progress — so the frontend can render the unit map and use it as a learning home.
    Always contains every unit (a path needs all its stops), even for a brand-new learner.
    ``assigned_unit_slug`` is the teacher-assigned unit for a signed-in learner (Slice DAT.10),
    or ``null`` when none is assigned OR the caller is anonymous (anonymous demo learners have no
    teacher assignment).
    """

    model_config = ConfigDict(extra="forbid")

    units: list[UnitView] = Field(
        default_factory=list,
        description="Every unit as a card, in teaching order, with the learner's progress.",
    )
    assigned_unit_slug: str | None = Field(
        default=None,
        description=(
            "Slug of the teacher-assigned unit for a signed-in learner (DAT.10), or null when "
            "none is assigned or the caller is anonymous."
        ),
    )


class UnitDetailView(BaseModel):
    """A single unit with its lessons and the learner's per-lesson progress (Slice DAT.9).

    The ``UnitView`` fields (so a detail page needs no second card lookup) plus ``lessons`` — the
    unit's lessons in catalog order, each a ``LessonView`` carrying the learner's per-lesson
    status. The frontend renders this as a unit's lesson list / learning-path rail.
    """

    model_config = ConfigDict(extra="forbid")

    unit_slug: str = Field(description="Stable unit slug (unique across the catalog).")
    title: str = Field(description="Human-readable unit title (catalog).")
    description: str = Field(description="Short description of the unit (catalog).")
    order: int = Field(description="Display/teaching order within the catalog (1-based).")
    ccss_cluster: str | None = Field(
        default=None,
        description="Common Core (CCSS) cluster code, or null if single-framework.",
    )
    teks_cluster: str | None = Field(
        default=None,
        description="Texas (TEKS) cluster code, or null if single-framework.",
    )
    status: UnitStatus = Field(description="The learner's aggregated status on this unit.")
    percent_complete: float = Field(
        ge=0.0,
        le=100.0,
        description="Percent of the unit's lessons completed, in [0, 100].",
    )
    lesson_count: int = Field(ge=0, description="Number of lessons in the unit.")
    assigned: bool = Field(
        description="True only for the signed-in learner's teacher-assigned unit (DAT.10).",
    )
    lessons: list[LessonView] = Field(
        default_factory=list,
        description="The unit's lessons, in catalog order, each with per-lesson progress.",
    )


class MeResponse(BaseModel):
    """The authenticated learner's persistent identity handle + carried-forward mastery (PL.3).

    Returned by ``GET /me`` for a request bearing a valid Google ID token. This is the
    "same login anywhere → same state" proof: the ``learner_id`` is the stable persistence
    handle the Google ``sub`` maps to (idempotently — the same login always resolves to the
    same row), and ``mastery`` is that learner's persisted per-KC state (reusing the PL.1
    ``MasteryState`` rows), so a learner signing in on a new device sees their prior progress.

    What is deliberately NOT here: the Google ``sub`` itself. The ``sub`` is an auth-layer
    secret-ish identifier we key on but never re-expose; the wire handle is the internal
    ``learner_id``. ``email`` is included only as the convenience label the surface greets the
    learner with. Neither field is consumed by any turn-loop decision — identity never reaches
    the mastery model, policy, or LLM (ARCHITECTURE.md §14 invariant 8); this payload exists
    purely for persistence/continuity on the auth path.
    """

    model_config = ConfigDict(extra="forbid")

    learner_id: int = Field(description="Stable persistence handle the Google sub maps to (PL.3).")
    email: str | None = Field(
        default=None,
        description="The learner's Google email, if the token carried one — a display label only.",
    )
    mastery: list[MasterySnapshot] = Field(
        default_factory=list,
        description="The learner's carried-forward per-KC mastery (PL.1 rows; mastered=confirmed).",
    )
    study_plan: StudyPlanView = Field(
        default_factory=StudyPlanView,
        description="What to do next: due reviews (spaced repetition) + the next unlocked skill.",
    )


__all__ = [
    "ActionType",
    "AdaptiveTurnView",
    "AnswerKind",
    "ArmVerdictView",
    "BenchmarkPersonaSummaryView",
    "BenchmarkTranscriptView",
    "ChatTurnView",
    "CourseNodeView",
    "CourseView",
    "CourseNodeStatus",
    "ErrorType",
    "EventBatchRequest",
    "EventIngestResponse",
    "HwAssignRequest",
    "HwAssignResponse",
    "HwConfirmAnswer",
    "HwConfirmRequest",
    "HwDraftItemView",
    "HwGradeResultView",
    "HwQuestionResultView",
    "HwQuestionView",
    "HwStatusResponse",
    "HwSubmitRequest",
    "HwSubmitResponse",
    "InteractionEventIn",
    "InterventionKind",
    "InterventionView",
    "LessonView",
    "MasterySnapshot",
    "MeResponse",
    "StudyPlanView",
    "MetricArmVerdictView",
    "MetricComparisonView",
    "PersonaComparisonView",
    "ProblemView",
    "RouteOptionView",
    "StartSessionRequest",
    "StartSessionResponse",
    "StaticTurnView",
    "SurfaceState",
    "ThreeArmComparisonView",
    "TransferProbeStepView",
    "TurnRequest",
    "TurnResponse",
    "UnitDetailView",
    "UnitListView",
    "UnitStatus",
    "UnitView",
    "WorkedStepView",
]
