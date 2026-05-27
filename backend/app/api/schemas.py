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
from app.domain.knowledge_components import KnowledgeComponentId

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


__all__ = [
    "ActionType",
    "ErrorType",
    "MasterySnapshot",
    "SurfaceState",
    "TurnRequest",
    "TurnResponse",
]
