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

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

# We reuse the Layer-1 typed handles as the field types so the API speaks the
# same KC ids and representation names as the domain model — the registry is the
# single source of truth (ARCHITECTURE.md §4). Importing the enums (not raw
# strings) keeps the contract aligned with the domain and the generated TS types.
from app.domain.knowledge_components import KnowledgeComponentId, Representation

# ErrorType IS the domain verifier's ErrorCategory (Slice 1.4). The verifier owns
# the §3.6 routing alphabet; the API speaks the very same enum so the wire contract
# and the policy that routes on it cannot drift. (Reconciles the Slice 1.9 flag —
# the local placeholder enum is gone; this is now the single source of truth.)
from app.domain.verifier import ErrorCategory as ErrorType

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
    # The number-line surface needs a candidate set to snap a drag onto BEFORE the
    # answer reaches the domain (the verifier does exact Rational equality, no
    # tolerance — verifier.py docstring). The candidate set is k/tick_segments for
    # k=0..tick_segments; the displayed fraction p/q is exactly one of them because
    # the generator displays the reduced target and tick_segments == its denominator.
    # None when the problem is not a number-line placement (no snap grid needed).
    tick_segments: int | None = Field(
        default=None,
        ge=1,
        description="Number-line only: equal intervals on the 0–1 line to snap to; null otherwise.",
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
    """Begin a session from a Turn-0 routing choice (decision 0.D.2).

    Carries only the chosen ``route_key`` (a ``RouteOptionView.key``). The KC,
    calibration item, and BKT prior are all derived server-side from the locked
    routing table (tutor ``from_route``) — the client cannot set them, so the
    prior-not-commitment seeding stays authoritative on the backend (0.D.2).
    """

    model_config = ConfigDict(extra="forbid")

    route_key: str = Field(min_length=1, description="The chosen Turn-0 option key (0.D.2).")
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


class ThreeArmComparisonView(BaseModel):
    """The full three-arm comparison for display (Slice 5.3, PROJECT.md §3.11).

    The adaptive and static columns are computed live and deterministically; the chat
    column is the pre-registered prediction until the cost-gated live LLM run
    (``chat_live`` says which)."""

    model_config = ConfigDict(extra="forbid")

    rows: list[PersonaComparisonView]
    total: int = Field(description="Number of personas (arms are scored over these).")
    adaptive_false_positives: int
    chat_live: bool = Field(description="True once the chat column reflects a real LLM run.")
    headline: str = Field(description="The §3.11 pitch summary for the header.")


__all__ = [
    "ActionType",
    "ArmVerdictView",
    "ErrorType",
    "InterventionKind",
    "InterventionView",
    "MasterySnapshot",
    "PersonaComparisonView",
    "ProblemView",
    "RouteOptionView",
    "StartSessionRequest",
    "StartSessionResponse",
    "SurfaceState",
    "ThreeArmComparisonView",
    "TurnRequest",
    "TurnResponse",
]
