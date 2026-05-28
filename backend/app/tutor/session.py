"""The tutor session loop + two-step cold start (Slices 1.7, 2.6).

This is the tutor scaffolding (PROJECT.md §6): the in-memory session orchestrator
that walks a session correctly. It is a *service* — it ORCHESTRATES the
already-built, already-tested Layer-1 domain, the mastery model, and the §3.6
adaptation policy; it never re-implements their jobs (CLAUDE.md §7 boundaries).
Concretely:

  - SymPy correctness is the verifier's job, called via ``domain.verifier.verify``
    — there is NO direct SymPy here beyond carrying the ``Rational`` values the
    domain hands back (CLAUDE.md §8.2, ARCHITECTURE.md §14 invariant 2/5);
  - the mastery probability and the §3.4 rules are the mastery model's job, called
    via ``mastery.mastery_model`` — no BKT math is re-derived here;
  - the next surface state is the policy's job, called via
    ``policy.transitions.next_transition`` and GATED by ``policy.refuse_rules`` —
    no transition table is re-derived here (ARCHITECTURE.md §7);
  - there is NO LLM anywhere on this path (CLAUDE.md §8.1, ARCHITECTURE.md §14
    invariant 1: nothing in the turn loop calls a model provider);
  - there is NO DB persistence — the session lives in memory. Repositories /
    persistence are a deliberately later slice; this orchestrator is pure-ish and
    deterministic so the persona harness can drive it reproducibly (PROJECT.md
    §4.1).

What this module implements:

  1. **The two-step cold start, locked in decision 0.D.2.** Turn 0 is a
     kid-friendly routing question (three equal-weight KC options + a
     de-emphasized "I'm not sure" default that routes to equivalence). The choice
     seeds a BKT *prior, not a commitment* (via
     ``mastery.initial_prior_from_self_report``). Turn 1 is one calibration
     problem in the chosen route, built from the LOCKED 0.D.2 items. The
     self-report is never echoed to the learner; predicted-vs-actual is logged as
     a metacognitive-calibration signal only and is NOT acted on.
  2. **The reactive session loop (Slice 2.6).** Present a problem, accept a
     submitted answer, call the domain verifier, build a mastery ``Observation``,
     update the in-session mastery view, append the turn to history, and APPLY the
     §3.6 policy BETWEEN problems. The surface may now move S1↔S2↔S3↔S4: the loop
     maintains the two counters ``next_transition`` routes on
     (``consecutive_correct_no_hint_in_state``, ``consecutive_errors``), asks the
     policy for the next transition on each answer's ``AnswerOutcome``, and applies
     the resulting ``StateChange`` to ``surface_state`` — but ONLY when the
     refuse-rules permit it (refuse-rule 1: state changes happen BETWEEN problems,
     not mid-problem; refuse-rule 3: idle never changes state, structurally
     enforced by ``next_transition``; refuse-rule 4: every applied transition
     carries a non-empty label). S5/the transfer probe is deliberately NOT wired
     here — that is Slice 3.7. An ``interleaved_set_passed`` hook is exposed so the
     later slice can feed the mastery signal in, but it does not build or run the
     probe.

Determinism: ``TutorSession`` owns all its state (history + per-KC priors +
counters + surface state); there is no module-global mutable state. Generated
problems are seeded. Same inputs ⇒ same walk (PROJECT.md §4.1, CLAUDE.md §8.1).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sympy import Rational

from app.domain.knowledge_components import KnowledgeComponentId, Representation, get_kc

# MisconceptionId is owned by misconceptions.py (the verifier re-uses but does not
# re-export it). Importing it from its home keeps the re-export explicit for
# mypy --strict and points the reader at the source of truth.
from app.domain.misconceptions import MisconceptionId
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.verifier import ErrorCategory, Submitted, verify
from app.mastery.mastery_model import (
    DEFAULT_BKT_PARAMS,
    BktParams,
    Observation,
    declare_mastery,
    initial_prior_from_self_report,
    kc_mastery_probability,
)

# A persona config is the synthetic learner the probe evaluates against in the harness
# (the production surface would supply a real learner's S5 answers; the harness drives
# the deterministic Layer-3 simulator — ARCHITECTURE.md §5, §11).
from app.personas.persona_config import PersonaConfig

# The §3.6 reactive policy (Slice 2.4) decides the next surface state from a turn's
# outcome; the refuse-rules (§3.8) gate WHEN an applied transition is allowed. The
# tutor consumes both — it never re-derives the transition table (CLAUDE.md §7;
# ARCHITECTURE.md §7). ``InterleavedSetPassed`` is imported only so the
# ``interleaved_set_passed`` hook can hand the mastery signal to the policy; the
# transfer probe itself (S5) is Slice 3.7 and is NOT built here.
from app.policy.refuse_rules import is_state_change_allowed
from app.policy.surface_states import SurfaceState
from app.policy.transitions import (
    AnswerOutcome,
    InterleavedSetPassed,
    StateChange,
    TransferProbeFailed,
    Transition,
    next_transition,
)

# Slice 3.7: the S5 transfer probe. The tutor consumes it — when the surface reaches
# S5 (the interleaved set passed, §3.6 row 6), it runs the probe and routes the
# verdict: on PASS it confirms mastery; on FAIL it emits the policy's
# ``TransferProbeFailed`` signal, which demotes the learner to S2/S3 (§3.6 row 7).
# The probe itself owns item generation and evaluation (CLAUDE.md §7 boundaries); the
# tutor never re-derives transfer-item logic here.
from app.tutor.transfer_probe import TransferProbeResult, run_transfer_probe

# The surface starts in S1 (the default fluent symbolic-focus state,
# ARCHITECTURE.md §7). From Slice 2.6 the loop may move it via the §3.6 policy.
_INITIAL_SURFACE: SurfaceState = SurfaceState.SYMBOLIC_FOCUS


# ─────────────────── Turn 0: the kid-friendly routing question (0.D.2) ───────────────────


@dataclass(frozen=True)
class RouteOption:
    """One option in the Turn-0 routing question (decision 0.D.2).

    Frozen because the routing menu is fixed configuration, not runtime state. The
    surface renders ``prompt`` (kid-friendly, no curriculum terms, no quiz framing
    — 0.D.2); ``routes_to`` is the KC the option calibrates in at Turn 1.

    ``is_unsure_default`` marks the single de-emphasized "I'm not sure" option. It
    still *routes to* a KC (equivalence) so Turn 1 has a calibration item, but it
    is NOT a self-claim of skill — so it seeds no KC above the unsure default (see
    ``_chosen_kc_for_seeding``). Splitting "where to calibrate" from "what the
    learner claimed to know" is exactly the prior-not-commitment idea: a default
    is not a claim.
    """

    key: str
    prompt: str
    routes_to: KnowledgeComponentId
    is_unsure_default: bool = False


# The three equal-weight KC options + the de-emphasized "I'm not sure" default
# (0.D.2). Prompts are deliberately kid-friendly and free of curriculum terms /
# quiz framing. The three real options span diagnostically distinct KCs the
# calibration items exist for (addition, equivalence, number-line placement); the
# unsure default routes to equivalence (the locked 0.D.2 fallback).
_ADDITION_ROUTE = RouteOption(
    key="combine",
    prompt="Putting two fraction pieces together to see how much you have",
    routes_to=KnowledgeComponentId.ADDITION_UNLIKE,
)
_EQUIVALENCE_ROUTE = RouteOption(
    key="same_amount",
    prompt="Telling when two different-looking fractions are really the same amount",
    routes_to=KnowledgeComponentId.EQUIVALENCE,
)
_NUMBER_LINE_ROUTE = RouteOption(
    key="where_on_line",
    prompt="Finding where a fraction sits on a line between 0 and 1",
    routes_to=KnowledgeComponentId.NUMBER_LINE_PLACEMENT,
)

# The single de-emphasized default. It routes to equivalence for calibration but
# carries no skill claim (0.D.2). Exported so the surface and the tutor agree on
# which option is "I'm not sure" without string-matching.
UNSURE_ROUTE = RouteOption(
    key="not_sure",
    prompt="Not sure yet? Just get me started!",
    routes_to=KnowledgeComponentId.EQUIVALENCE,
    is_unsure_default=True,
)

_ROUTING_CHOICES: tuple[RouteOption, ...] = (
    _ADDITION_ROUTE,
    _EQUIVALENCE_ROUTE,
    _NUMBER_LINE_ROUTE,
    UNSURE_ROUTE,
)


def routing_choices() -> tuple[RouteOption, ...]:
    """The Turn-0 routing menu: three KC options + the de-emphasized default.

    Returned as data so the surface renders them (and visually de-emphasizes the
    ``is_unsure_default`` one) without the tutor knowing anything about layout
    (0.D.2: no diagnostic/quiz framing — that is a presentation choice, here we
    only supply the options and their KC routing).
    """
    return _ROUTING_CHOICES


# ───────────── Turn 1: the LOCKED calibration problems per route (0.D.2) ─────────────
#
# 0.D.2 names the exact Turn-1 calibration item per route. We construct each as a
# ``Problem`` (the shared domain type) with SymPy-correct values, so the same
# verifier and mastery model handle a calibration turn and any later turn
# identically. These are hand-built (not generator-sampled) precisely because the
# decision LOCKS the specific items — the generator's job is bulk problems, not the
# fixed cold-start probes.


def _addition_calibration() -> Problem:
    """0.D.2 addition route: '1/3 + 1/4'. Correct value 7/12 (SymPy)."""
    first, second = Rational(1, 3), Rational(1, 4)
    return Problem(
        problem_id="CALIB-ADD-1_3+1_4",
        kc=KnowledgeComponentId.ADDITION_UNLIKE,
        surface_format=Representation.SYMBOLIC,
        statement="1/3 + 1/4 = ?",
        correct_value=first + second,  # SymPy: 7/12
        representations_available=get_kc(KnowledgeComponentId.ADDITION_UNLIKE).representations,
        operands=(first, second),
    )


def _equivalence_calibration() -> Problem:
    """0.D.2 equivalence route (and the unsure default): 'is 2/3 = 4/6?'.

    A yes/no relational judgment (``answer_kind=YES_NO``): the question asks whether
    the two amounts match, so the learner answers yes/no, NOT a fraction. The truth is
    SymPy equality over the operands (2/3 == 4/6 → YES), computed by the verifier.
    ``correct_value`` keeps the shared magnitude (2/3) as the anchor the diagnostic log
    and number-line scaffold read; the operands carry both fractions in reading order.
    """
    first, second = Rational(2, 3), Rational(4, 6)
    return Problem(
        problem_id="CALIB-EQ-2_3=4_6",
        kc=KnowledgeComponentId.EQUIVALENCE,
        surface_format=Representation.SYMBOLIC,
        statement="Is 2/3 the same amount as 4/6?",
        correct_value=first,  # 2/3 == 4/6; the shared magnitude anchor
        representations_available=get_kc(KnowledgeComponentId.EQUIVALENCE).representations,
        operands=(first, second),
        answer_kind=AnswerKind.YES_NO,
    )


def _number_line_calibration() -> Problem:
    """0.D.2 number-line route: place 3/5 on the 0–1 line. Correct value 3/5."""
    target = Rational(3, 5)
    return Problem(
        problem_id="CALIB-NL-3_5",
        kc=KnowledgeComponentId.NUMBER_LINE_PLACEMENT,
        surface_format=Representation.NUMBER_LINE,
        statement="Drag the marker to where 3/5 belongs on the line from 0 to 1.",
        correct_value=target,
        representations_available=get_kc(
            KnowledgeComponentId.NUMBER_LINE_PLACEMENT
        ).representations,
        operands=(target,),
    )


# Map each calibration-target KC to its LOCKED Turn-1 item builder (0.D.2). Only
# the three routable KCs appear; the unsure default routes to equivalence.
_CALIBRATION_BUILDERS = {
    KnowledgeComponentId.ADDITION_UNLIKE: _addition_calibration,
    KnowledgeComponentId.EQUIVALENCE: _equivalence_calibration,
    KnowledgeComponentId.NUMBER_LINE_PLACEMENT: _number_line_calibration,
}


def _calibration_problem(kc: KnowledgeComponentId) -> Problem:
    """The locked Turn-1 calibration ``Problem`` for a routed KC (0.D.2).

    Raises ``KeyError`` (via the dict) on a KC with no locked calibration item —
    the routing menu only ever offers the three that have one, so reaching this
    with another KC is a programming error, not learner input (fail loudly,
    CLAUDE.md §8.5).
    """
    return _CALIBRATION_BUILDERS[kc]()


# ─────────────────── The metacognitive-calibration signal (0.D.2) ───────────────────


@dataclass(frozen=True)
class CalibrationSignal:
    """Predicted-vs-actual at cold start — a logged signal, NEVER acted on (0.D.2).

    0.D.2: "the self-report is never referenced back to the learner;
    predicted-vs-actual is logged as a metacognitive-calibration signal only."
    This record captures exactly that and nothing more — which KC the learner
    routed into (their implicit "prediction" that they can do it) versus whether
    their first calibration attempt was actually correct. The tutor does NOT read
    this back into any decision (no prior adjustment, no transition, no feedback
    text); it exists so a later analysis slice can study learner calibration
    (García et al. 2015/2016, PROJECT.md §8 citation note).

    ``self_reported_kc`` is ``None`` when the learner took the de-emphasized
    "I'm not sure" default — there was no self-claim to calibrate against.
    """

    self_reported_kc: KnowledgeComponentId | None
    first_attempt_correct: bool


# ─────────────────────────── The turn record (in-memory history) ───────────────────────────


@dataclass(frozen=True)
class TurnResult:
    """What one ``submit_answer`` reports back (the loop's per-turn output).

    Mirrors the deterministic outputs the surface needs (cf. the API
    ``TurnResponse`` shape), but is the tutor's own in-process type — the API/
    route mapping is a later slice (CLAUDE.md §7: routes call services, not the
    reverse). Frozen: a turn's verdict is a fact.

    - ``correct`` / ``error_category``  the verifier's verdict (domain decides).
    - ``feedback``                      one-line, label-shaped learner feedback. It
      never echoes the self-report/route (0.D.2). Rich LLM feedback is a later,
      off-path concern (ARCHITECTURE.md §14 invariant 1).
    - ``surface_state``                 the surface AFTER the turn, AFTER the §3.6
      policy has been applied between problems (Slice 2.6). May differ from the
      state the turn happened in when a transition fired and the refuse-rules
      allowed applying it.
    - ``transition``                    the policy's decision for this turn — the
      ``StateChange`` / ``NoChange`` / ``Nudge`` ``next_transition`` returned. Its
      ``label`` is the §3.8-rule-4 one-line transition copy (always non-empty for a
      ``StateChange``); the caller / log can read *why* the surface moved (or did
      not). Frozen, carried straight through from the policy.
    - ``matched_misconception``         which named misconception fired, if any
      (passed straight through from the verifier for the diagnostic log).
    - ``mastery_snapshot``              per-KC mastery readout after the update.
    """

    correct: bool
    error_category: ErrorCategory
    feedback: str
    surface_state: SurfaceState
    transition: Transition
    matched_misconception: MisconceptionId | None
    mastery_snapshot: tuple[MasterySnapshot, ...]


@dataclass(frozen=True)
class MasterySnapshot:
    """A per-KC mastery readout the tutor returns after an update (ARCHITECTURE §6).

    The tutor's in-process snapshot (distinct from the API Pydantic model of the
    same idea — that wiring is a later slice). ``probability`` is the BKT
    probability; ``mastered`` is the mastery model's *declared* mastery (which
    requires far more than the threshold — the §3.4 rules), so the surface can
    show honest progress without re-running the rules itself.
    """

    kc: KnowledgeComponentId
    probability: float
    mastered: bool


@dataclass(frozen=True)
class Turn:
    """One recorded turn in the in-memory session history.

    Holds everything the §6 checkpoint needs to "read the log and see expected
    behavior" (PROJECT.md §6): the ``Problem`` presented, the raw answer, the
    mastery ``Observation`` the loop built, the ``TurnResult`` returned, and the
    surface state the turn HAPPENED in (the state before this turn's §3.6
    transition applied). Frozen — history is append-only.
    """

    problem: Problem
    submitted: Submitted
    observation: Observation
    result: TurnResult
    surface_state: SurfaceState


# ─────────────────────────────── The session orchestrator ───────────────────────────────


@dataclass
class TutorSession:
    """An in-memory, deterministic tutor session (Slices 1.7, 2.6).

    Owns ALL its state — there is no module-global mutable state, so two sessions
    never interfere and a persona harness can run many in parallel reproducibly
    (PROJECT.md §4.1). State:

    - ``_priors``        per-KC BKT prior P(L0), seeded at cold start from the
      Turn-0 self-report (0.D.2). A prior, not a commitment: a routed KC starts
      modestly higher, everything else at the unsure default, all far below τ.
    - ``current_problem`` the problem currently presented (Turn 1 = the calibration
      item; later turns = whatever ``present_problem`` set).
    - ``surface_state``  the current UI surface state. Starts S1; from Slice 2.6 the
      §3.6 policy may move it between problems (S1↔S2↔S3↔S4).
    - ``_consecutive_correct_no_hint_in_state`` / ``_consecutive_errors`` the two
      running counters the §3.6 rate rules route on (transitions.py
      ``AnswerOutcome``). The tutor owns and maintains them; the policy is stateless
      and reads them off the ``AnswerOutcome`` it is handed.
    - ``_history``       append-only list of completed ``Turn`` records.
    - ``calibration_signal`` the 0.D.2 metacognitive signal, set when the FIRST
      turn after cold start is answered; logged, never acted on.

    Constructed via ``cold_start`` / ``from_route`` (the two-step entry), never by
    hand — the dataclass fields are an implementation detail.
    """

    current_problem: Problem
    _priors: dict[KnowledgeComponentId, float]
    _self_reported_kc: KnowledgeComponentId | None
    _params: BktParams = DEFAULT_BKT_PARAMS
    surface_state: SurfaceState = _INITIAL_SURFACE
    calibration_signal: CalibrationSignal | None = None
    _history: list[Turn] = field(default_factory=list)
    # Slice 3.7: the KCs whose PROVISIONAL mastery the S5 transfer probe has CONFIRMED
    # (PROJECT.md §3.4: mastery is provisional until the probe is passed). A KC enters
    # this set only when ``run_transfer_probe`` passes both §3.9 transfer items; a
    # failed probe never adds it (and routes a demotion instead). Owned by the session
    # so two sessions never share confirmation state (reproducibility, PROJECT.md §4.1).
    _confirmed_kcs: set[KnowledgeComponentId] = field(default_factory=set)
    # The §3.6 counters (transitions.py AnswerOutcome). "In state" means since the
    # last state change: a state change resets the unhinted-correct streak because
    # the fade rule (§3.6 row 3) is about fluency in the CURRENT representation.
    _consecutive_correct_no_hint_in_state: int = 0
    _consecutive_errors: int = 0

    # ── construction: the two-step cold start (0.D.2) ──

    @classmethod
    def cold_start(cls, *, chosen_kc: KnowledgeComponentId | None) -> TutorSession:
        """Begin a session from a Turn-0 routing choice (decision 0.D.2).

        ``chosen_kc`` is the KC the learner routed into, or ``None`` for the
        de-emphasized "I'm not sure" default. We:

          1. seed EVERY KC's BKT prior via the mastery model's
             ``initial_prior_from_self_report`` — the routed KC modestly above the
             unsure default, the rest at the default. This is the prior-not-
             commitment seed (0.D.2); nothing here is at or near τ.
          2. present the LOCKED Turn-1 calibration problem for the route. When
             ``chosen_kc`` is None (unsure default), that is the equivalence
             calibration (0.D.2).

        The surface starts in S1 (the default fluent state); from Slice 2.6 the
        §3.6 policy may move it between problems.
        """
        priors = {
            kc: initial_prior_from_self_report(kc, chosen_kc=chosen_kc)
            for kc in KnowledgeComponentId
        }
        calibration_target = chosen_kc if chosen_kc is not None else UNSURE_ROUTE.routes_to
        return cls(
            current_problem=_calibration_problem(calibration_target),
            _priors=priors,
            _self_reported_kc=chosen_kc,
        )

    @classmethod
    def from_route(cls, option: RouteOption) -> TutorSession:
        """Begin a session from the ``RouteOption`` the surface returned (0.D.2).

        Splits "what KC do we calibrate in" from "what did the learner claim".
        A non-default option is a self-claim, so it seeds that KC's prior up. The
        de-emphasized "I'm not sure" default is NOT a claim, so it seeds nothing
        above the unsure default (``chosen_kc=None``) even though it still routes
        to equivalence for the calibration item. This is the operational meaning of
        prior-not-commitment at the routing boundary.
        """
        chosen_kc = None if option.is_unsure_default else option.routes_to
        session = cls.cold_start(chosen_kc=chosen_kc)
        # The unsure default routes to equivalence for calibration regardless; for a
        # real option the calibration target already matches the chosen KC.
        if option.is_unsure_default:
            session.current_problem = _calibration_problem(option.routes_to)
        return session

    @classmethod
    def for_goal_kc(
        cls,
        kc: KnowledgeComponentId,
        *,
        surface_format: Representation,
        seed: int = 0,
    ) -> TutorSession:
        """Begin a session whose GOAL is ``kc``, presenting a generated first problem (course map).

        This is the course product's "start this skill's lesson" entry (PROJECT.md §3.13), as
        opposed to ``from_route`` (the Turn-0 cold start with its locked calibration item + a
        self-report prior). Choosing to STUDY a skill is not a claim to KNOW it, so priors are
        neutral (``chosen_kc=None`` — no KC seeded above the unsure default), and the first
        problem is GENERATED for ``kc`` in the given live ``surface_format`` (the representation
        the surface can render+answer). The scheduler interleaves from ``kc`` thereafter — the
        service derives the goal KC from the first turn's KC, so seeding it as the first problem
        is all that is needed. Determinism is preserved (generate_problem is seed-only).
        """
        session = cls.cold_start(chosen_kc=None)
        session.current_problem = generate_problem(kc, seed, surface_format)
        return session

    # ── reads ──

    def prior_for(self, kc: KnowledgeComponentId) -> float:
        """The seeded BKT prior P(L0) for ``kc`` (set at cold start; 0.D.2)."""
        return self._priors[kc]

    def seed_priors(self, priors: dict[KnowledgeComponentId, float]) -> None:
        """Override the BKT prior P(L0) for the given KCs (mastery-level resume, Slice PL.1.2).

        Used ONLY when rehydrating a session after a server restart: the persisted per-KC
        ``bkt_probability`` is seeded back as the prior so the learner's progress carries
        forward instead of resetting to the cold-start seed. KCs absent from ``priors`` keep
        their cold-start value. This sets the BKT *prior* (the same lever cold start uses via
        ``initial_prior_from_self_report``); subsequent answers still update the estimate from
        evidence, so a resumed session is not frozen — it resumes from the right starting point.

        This does NOT reconstruct the observation history (that is the flagged exact-resume
        gap): with an empty history, ``mastery_probability`` returns exactly these seeded
        priors until new turns accumulate evidence.
        """
        self._priors.update(priors)

    @property
    def history(self) -> tuple[Turn, ...]:
        """The completed turns, in submission order (append-only, read-only view)."""
        return tuple(self._history)

    @property
    def last_turn(self) -> Turn | None:
        """The most recent completed turn, or ``None`` before any answer is made.

        ``None`` at cold start is also how a caller can assert "no preemptive hint
        / no turn has happened yet" right after presenting the calibration problem.
        """
        return self._history[-1] if self._history else None

    @property
    def consecutive_correct_no_hint_in_state(self) -> int:
        """The current run of correct, unhinted answers in the CURRENT state (§3.6).

        Read-only view of the counter the §3.6 fade rule (row 3) routes on. Resets
        to 0 on a wrong answer, on a hinted answer, or on a state change.
        """
        return self._consecutive_correct_no_hint_in_state

    @property
    def consecutive_errors(self) -> int:
        """The current run of consecutive wrong answers across the session (§3.6).

        Read-only view of the counter the §3.6 stuck rule (row 4: 2+ errors → S4)
        routes on. Resets to 0 on any correct answer.
        """
        return self._consecutive_errors

    def mastery_probability(self, kc: KnowledgeComponentId) -> float:
        """The current in-session BKT probability for ``kc``.

        Before any observation for ``kc`` exists, this is its seeded prior (the
        cold-start value). Once turns exist, it is the mastery model's BKT run over
        this session's observations for ``kc`` — we delegate the math entirely
        (CLAUDE.md §7: orchestrate, don't re-derive). We thread the seeded prior in
        as the BKT ``p_init`` so the self-report prior actually informs the
        estimate (0.D.2), while still letting evidence override it.
        """
        observations = [t.observation for t in self._history]
        if not any(o.kc == kc for o in observations):
            return self._priors[kc]
        params = self._params_with_prior(kc)
        return kc_mastery_probability(kc, observations, params=params)

    # ── the reactive session loop (Slice 2.6) ──

    def present_problem(
        self,
        *,
        kc: KnowledgeComponentId,
        seed: int,
        surface_format: Representation = Representation.SYMBOLIC,
    ) -> Problem:
        """Present a fresh generated problem for ``kc``, deterministically.

        Delegates problem construction to the Layer-1 generator (seeded ⇒
        reproducible). Presenting a problem does NOT change ``surface_state``: state
        transitions are applied at ANSWER time, between problems (refuse-rule 1,
        §3.8). The caller chooses which KC/format to present next (the harness
        interleaves KCs and formats here); the surface state the learner sees is
        whatever the last applied transition left it in. Returns the problem now
        showing so a caller can read its correct value.
        """
        problem = generate_problem(kc, seed, surface_format)
        self.current_problem = problem
        return problem

    def submit_answer(
        self,
        submitted: Submitted,
        *,
        latency_ms: int,
        hint_used: bool = False,
    ) -> TurnResult:
        """Process one learner answer to the current problem (the reactive turn loop).

        The orchestration, in the order ARCHITECTURE.md §10 prescribes (minus the
        LLM surface step, which is off-path — §8.1):

          1. **verify** the answer against the current problem with the DOMAIN
             verifier (SymPy decides; this service never judges math — §8.2);
          2. build a mastery **Observation** from the turn (kc, correct,
             representation = the problem's surface format, hinted, latency_ms);
          3. **update the in-session mastery view** by folding the observation into
             history and asking the mastery model for the fresh probability and
             declaration (no BKT re-derivation here — §7);
          4. **update the §3.6 counters** from this answer, then ask the policy for
             the next transition and APPLY it between problems, gated by the
             refuse-rules (see ``_apply_policy``);
          5. **append** the completed turn to history (recording the state the turn
             HAPPENED in), and return a ``TurnResult`` carrying the verdict, the
             one-line feedback, the policy ``transition``, and the per-KC mastery
             snapshot.

        The ``TurnResult.surface_state`` is the state AFTER the policy applied
        (Slice 2.6): it equals the pre-turn state when the policy did not move, or
        the new state when a ``StateChange`` fired and the refuse-rules allowed it.
        The feedback never echoes the self-report (0.D.2).

        Side effect besides history: on the FIRST answered turn it records the
        0.D.2 ``calibration_signal`` (predicted-vs-actual) — logged, never acted on.
        """
        problem = self.current_problem
        verdict = verify(problem, submitted)

        observation = Observation(
            kc=problem.kc,
            correct=verdict.is_correct,
            representation=problem.surface_format,
            hinted=hint_used,
            latency_ms=latency_ms,
        )

        # The mastery view reflects this turn: fold the new observation into history
        # before computing the snapshot (the update step). History is the session's
        # mastery evidence; we build the Turn after, so it can carry the result.
        provisional_history = [t.observation for t in self._history] + [observation]
        snapshot = self._mastery_snapshot(problem.kc, provisional_history)

        # The state the turn HAPPENED in — recorded on the Turn, and the "current"
        # state the policy routes FROM. The transition (if any) applies AFTER, so the
        # learner answered this problem entirely in one state (refuse-rule 1).
        state_during_turn = self.surface_state

        # §3.6: update the two counters from this answer, then apply the policy
        # between problems (gated by the refuse-rules). This mutates surface_state.
        transition = self._apply_policy(
            is_correct=verdict.is_correct,
            error_category=verdict.error_category,
            hint_used=hint_used,
        )

        result = TurnResult(
            correct=verdict.is_correct,
            error_category=verdict.error_category,
            feedback=_feedback_line(verdict.is_correct, verdict.error_category),
            surface_state=self.surface_state,  # the state AFTER the policy applied
            transition=transition,
            matched_misconception=verdict.matched_misconception,
            mastery_snapshot=snapshot,
        )

        self._history.append(
            Turn(
                problem=problem,
                submitted=submitted,
                observation=observation,
                result=result,
                surface_state=state_during_turn,
            )
        )

        # 0.D.2 metacognitive signal: set once, on the first answered turn (the
        # Turn-1 calibration attempt). Logged only — never read back into a
        # decision, never echoed to the learner.
        if self.calibration_signal is None:
            self.calibration_signal = CalibrationSignal(
                self_reported_kc=self._self_reported_kc,
                first_attempt_correct=verdict.is_correct,
            )

        return result

    def interleaved_set_passed(self, kc: KnowledgeComponentId) -> Transition:
        """Hand the mastery model's interleaved-set-passed signal to the policy (§3.6 row 6).

        Slice 2.6 wires the S1↔S2↔S3↔S4 reactive loop. The S5 transfer probe is
        Slice 3.7; this hook exists so that later slice can feed the
        ``InterleavedSetPassed`` mastery signal in and let the policy route to S5,
        WITHOUT this slice building or running the probe. The mastery model decides
        when the set is passed (ARCHITECTURE.md §6); the tutor does not re-derive
        that here — it forwards the verdict as the policy's ``InterleavedSetPassed``
        input. The resulting ``StateChange`` is applied between problems via the same
        refuse-rule gate as any other transition.
        """
        transition = next_transition(self.surface_state, InterleavedSetPassed(kc=kc))
        self._apply_transition(transition)
        return transition

    def is_confirmed(self, kc: KnowledgeComponentId) -> bool:
        """Whether ``kc``'s provisional mastery has been CONFIRMED by the S5 probe.

        PROJECT.md §3.4: mastery is provisional until the transfer probe (S5) is
        passed. A KC is confirmed only after ``run_transfer_probe`` passed BOTH §3.9
        transfer items for it; a failed probe leaves it unconfirmed (and demoted).
        """
        return kc in self._confirmed_kcs

    def run_transfer_probe(
        self,
        persona: PersonaConfig,
        kc: KnowledgeComponentId,
        *,
        representation_seed: int = 0,
        error_finding_seed: int = 0,
    ) -> TransferProbeResult:
        """Run the S5 transfer probe for ``kc`` and route its verdict (Slice 3.7).

        This is the S5 step the reactive loop reaches after the interleaved set passes
        (``interleaved_set_passed`` moved the surface to S5, §3.6 row 6). It is the
        moment of truth that turns PROVISIONAL mastery into CONFIRMED — or demotes it
        (PROJECT.md §3.4, §3.9; ARCHITECTURE.md §6).

        The surface MUST be in S5 to run the probe: S5 IS the transfer test (§3.5), so
        running it from any other state would be out of sequence. We fail loudly rather
        than silently probe from the wrong state (CLAUDE.md §8.5).

        The probe is presented in a representation DIFFERENT from the learner's recent
        work on this KC (§3.9 representation transfer). We read that recent format from
        the session history (the format of the most recent answered item for ``kc``),
        defaulting to the KC's primary representation if the KC has not been seen — so
        the transfer item is, by construction, not the format the learner just drilled.

        Routing the verdict (the wiring §3.6 row 6 → S5 → probe → confirm/demote):
          - BOTH items passed → mark ``kc`` CONFIRMED. (No state change here: S5 ends
            the run for this KC; the policy's S5 → mastery-confirmed edge is the end of
            the §3.6 walk, ARCHITECTURE.md §7.)
          - either item failed → emit the policy ``TransferProbeFailed(kc)`` signal and
            APPLY the resulting demotion (to S2 for a magnitude KC, S3 for an operation
            KC), gated by the refuse-rules like any transition. ``kc`` is NOT confirmed.

        Deterministic: the probe's items are seeded and the simulator is deterministic,
        so the same (persona, KC, recent format, seeds) yields the same verdict and the
        same routing every call (PROJECT.md §4.1).
        """
        if self.surface_state is not SurfaceState.TRANSFER_PROBE:
            raise ValueError(
                "the transfer probe runs only in S5 (TRANSFER_PROBE); current state is "
                f"{self.surface_state.value}. Reach S5 via interleaved_set_passed first."
            )

        recent_format = self._recent_format_for(kc)
        result = run_transfer_probe(
            persona,
            kc,
            recent_format=recent_format,
            representation_seed=representation_seed,
            error_finding_seed=error_finding_seed,
        )

        if result.passed:
            # CONFIRMED: provisional mastery becomes confirmed (§3.4). The §3.6 S5 →
            # mastery-confirmed edge ends the walk for this KC; no demotion transition.
            self._confirmed_kcs.add(kc)
        else:
            # FAIL → demote. The policy owns the S5 → S2/S3 routing by the failed KC
            # (§3.6 row 7); we forward the signal and apply the move between problems.
            transition = next_transition(self.surface_state, TransferProbeFailed(failed_kc=kc))
            self._apply_transition(transition)

        return result

    def _recent_format_for(self, kc: KnowledgeComponentId) -> Representation:
        """The representation of the most recent answered item for ``kc`` in history.

        Used to choose a DIFFERENT representation for the §3.9 representation-transfer
        item ("a problem from a different representation than recent work", §3.5 S5).
        Falls back to the KC's primary (first advertised) representation when the KC has
        no history yet — so the probe still presents a format the learner has not just
        worked in, by construction (the transfer item generator then picks another).
        """
        for turn in reversed(self._history):
            if turn.problem.kc == kc:
                return turn.problem.surface_format
        return get_kc(kc).representations[0]

    # ── internals: the reactive policy step (Slice 2.6) ──

    def _apply_policy(
        self,
        *,
        is_correct: bool,
        error_category: ErrorCategory,
        hint_used: bool,
    ) -> Transition:
        """Update the §3.6 counters from this answer, route, and apply the transition.

        The order matters and follows the ``AnswerOutcome`` contract (transitions.py):
        the counters describe the session AFTER this answer, so we update them FIRST,
        then build the outcome the policy routes on:

          - ``_consecutive_errors``: +1 on a wrong answer, reset to 0 on a correct one
            (§3.6 row 4: "2+ consecutive errors → S4 from any state").
          - ``_consecutive_correct_no_hint_in_state``: +1 only on a correct, UNHINTED
            answer; reset to 0 on a wrong answer OR a hinted one. This is how "2
            correct without hints" (§3.6 row 3) is enforced — a hinted turn never
            advances the streak, so a hinted run never fades the scaffold.

        ``next_transition`` then decides the move from the CURRENT state. Applying it
        is gated by ``_apply_transition`` on the refuse-rules. Returns the policy's
        decision (a ``StateChange`` / ``NoChange`` / ``Nudge``) so the caller can put
        it on the ``TurnResult`` and the log can read why the surface moved.
        """
        if is_correct:
            self._consecutive_errors = 0
            if not hint_used:
                self._consecutive_correct_no_hint_in_state += 1
            else:
                self._consecutive_correct_no_hint_in_state = 0
        else:
            self._consecutive_errors += 1
            self._consecutive_correct_no_hint_in_state = 0

        outcome = AnswerOutcome(
            is_correct=is_correct,
            error_category=error_category,
            hint_used=hint_used,
            consecutive_correct_no_hint_in_state=self._consecutive_correct_no_hint_in_state,
            consecutive_errors=self._consecutive_errors,
        )
        transition = next_transition(self.surface_state, outcome)
        self._apply_transition(transition)
        return transition

    def _apply_transition(self, transition: Transition) -> None:
        """Apply a policy transition to ``surface_state``, gated by the refuse-rules (§3.8).

        Refuse-rule 1 (transitions.py / refuse_rules.py): a state change applies only
        BETWEEN problems, never mid-problem. ``submit_answer`` calls this AFTER the
        current problem has been answered, so the problem is no longer in progress and
        ``is_state_change_allowed`` is satisfied here — but we route the decision
        through the guard explicitly so the rule is enforced in one place and a future
        mid-problem caller cannot bypass it.

        Only a ``StateChange`` moves the surface. A ``NoChange`` / ``Nudge`` leaves
        the state put (refuse-rule 3: idle never changes state — structurally
        guaranteed upstream because an ``IdleNudge`` can only yield a ``Nudge`` /
        ``NoChange``). Refuse-rule 4 (every applied transition carries a non-empty
        label) is upheld by ``StateChange`` always carrying one; we assert it as a
        guard rather than trusting it silently.

        Applying a state change resets the unhinted-correct streak: "2 correct without
        hints in the CURRENT state" (§3.6 row 3) is per-state, so a fresh state starts
        the count over. The error counter is NOT reset here — "2+ consecutive errors"
        (row 4) spans states and is reset only by a correct answer.
        """
        if not isinstance(transition, StateChange):
            return
        # The problem that triggered this transition has been answered, so no problem
        # is in progress at the point of application (refuse-rule 1).
        if not is_state_change_allowed(problem_in_progress=False):
            return  # pragma: no cover — defensive; submit_answer always applies post-answer
        assert transition.label, "refuse-rule 4: a state change must carry a label"
        self.surface_state = transition.to_state
        # Per-state streak resets on entering a new state (§3.6 row 3 is in-state).
        self._consecutive_correct_no_hint_in_state = 0

    # ── internals ──

    def _params_with_prior(self, kc: KnowledgeComponentId) -> BktParams:
        """The BKT params for ``kc`` with ``p_init`` set to its seeded prior.

        The cold-start self-report seeds P(L0) per KC (0.D.2); BKT consumes the
        prior through ``p_init``. We copy the default params and swap in the
        per-KC seed so the routed KC's elevated prior actually informs its
        estimate, without mutating the shared ``DEFAULT_BKT_PARAMS``.
        """
        base = self._params
        return BktParams(
            p_init=self._priors[kc],
            p_transit=base.p_transit,
            p_slip=base.p_slip,
            p_guess=base.p_guess,
        )

    def _mastery_snapshot(
        self, kc: KnowledgeComponentId, observations: list[Observation]
    ) -> tuple[MasterySnapshot, ...]:
        """Build the per-KC snapshot after an update, for the answered KC.

        We report the answered KC (the one this turn moved). Probability and the
        declaration both come from the mastery model — we only package them. The
        per-KC prior is threaded in as ``p_init`` so the snapshot reflects the
        cold-start seed (0.D.2).
        """
        params = self._params_with_prior(kc)
        probability = kc_mastery_probability(kc, observations, params=params)
        mastered, _reasons = declare_mastery(kc, observations, params=params)
        return (MasterySnapshot(kc=kc, probability=probability, mastered=mastered),)


# ─────────────────────────────── Feedback (S1, non-echoing) ───────────────────────────────


def _feedback_line(correct: bool, error_category: ErrorCategory) -> str:
    """A single-line, learner-facing feedback label for a turn (refuse-rule-4 shape).

    Deliberately plain and short (CLAUDE.md §8.5: write for the reader): the rich,
    LLM-generated surface text is a later, off-the-critical-path concern
    (ARCHITECTURE.md §14 invariant 1). It must NEVER echo the self-report / route
    back to the learner (0.D.2) — so it speaks only about THIS answer, never about
    "the addition route you picked". One line only (no newline), so the surface can
    render it as the transition label.

    The wrong-answer copy is non-judgmental and points at the workspace rather than
    revealing the answer (protects productive struggle, refuse-rule 5). This is the
    per-answer verdict line; the SEPARATE one-line transition copy (when the §3.6
    policy moves the surface) is the ``Transition.label`` carried on the
    ``TurnResult`` (refuse-rule 4 lives there — see ``_apply_transition``).
    """
    if correct:
        return "Correct — nice work."
    if error_category is ErrorCategory.OPERATION:
        return "Not quite — let's look again at how the pieces combine."
    if error_category is ErrorCategory.MAGNITUDE:
        return "Not quite — think about how big this fraction really is."
    return "Not quite — give it another look."


__all__ = [
    "CalibrationSignal",
    "MasterySnapshot",
    "RouteOption",
    "Turn",
    "TurnResult",
    "TutorSession",
    "UNSURE_ROUTE",
    "routing_choices",
]
