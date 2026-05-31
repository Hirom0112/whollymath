"""Layer-3 behavioral simulator — given a persona + a problem, compute its action.

This is Slice 2.3 of the synthetic-learner harness (ARCHITECTURE.md §5 Layer 3;
PROJECT.md §4.1). Layer 3's whole job: "Given a persona config + a problem from the
tutor, computes the persona's action: what answer they submit, whether they request
a hint, how long they 'think' before answering, what they type if asked to explain.
Pure code. Same input always produces same output" (PROJECT.md §4.1; ARCHITECTURE.md
§5: "given persona + problem ⇒ action", deterministic).

What lives here, and nothing else: the deterministic mapping from a Layer-2
``PersonaConfig`` (``persona_config.py``) plus a Layer-1 ``Problem``
(``problem_generators.py``) to a ``SimulatedAction``. The action is computed from
the persona's ``KnowledgeMode`` on the problem's KC, its named misconceptions, and
the problem's ``surface_format`` — exactly the inputs §4.1 names.

Hard boundaries (CLAUDE.md §8.1, §8.3; ARCHITECTURE.md §14 invariants 1, 3, 4):

  - NO LLM. Layer 3 is pure code; the natural-language surface is Layer 4, a
    separate Week-5 slice that never sees the knowledge state. Nothing here imports
    or calls ``llm/``. The harness must run with Layer 4 disabled and lose only
    chat-naturalness — so all the EVIDENCE (the submitted answer, the hint flag, the
    timing, the justification flag) is produced here, deterministically.
  - NO DB, NO SymPy. Correctness is the verifier's job (``domain/verifier.py``);
    wrong-answer values are the misconception generators' job
    (``domain/misconceptions.py``). This module only chooses WHICH of those a
    persona produces; it never decides correctness itself.
  - DETERMINISTIC. The same (persona, problem, request) yields the same action on
    every call (PROJECT.md §4.1; ARCHITECTURE.md §5 Layer 3). Any probabilistic
    behavioral parameter (``hint_request_probability``, ``engagement_floor``) is
    resolved against a per-(persona, problem) seed derived with a STABLE hash
    (``hashlib`` — not Python's per-process-salted ``hash()``), so reproducibility
    holds across processes and runs, which is what makes the harness's evidence
    repeatable.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum

from sympy import Rational

from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.domain.misconceptions import (
    add_across,
    distributive_error,
    flipped_inequality,
    natural_number_bias_number_line,
    reversed_operands,
    subtract_across,
)
from app.domain.problem_generators import AnswerKind, Problem
from app.personas.persona_config import KnowledgeMode, PersonaConfig

# ─── What the tutor is asking the persona to do this turn ────────────────────


class RequestType(StrEnum):
    """What the tutor/transfer-probe asks the persona for on a given turn.

    The committed Layer-1 ``Problem`` type carries no "is this an explain / error-
    finding item" field, and Slice 2.3 must NOT modify the domain (lane discipline).
    So the *intent* of the turn — solve it, justify it, or judge a claimed answer —
    arrives as DATA the caller supplies, exactly the way the mastery model's "explain
    why" item per KC (PROJECT.md §3.4) and the transfer probe's error-finding item
    (§3.9) decide what to ask. This keeps the persona's action a pure function of
    (persona, problem, request) without inventing a domain field the slice may not add.

      - ANSWER     : routine "solve this" item — the default.
      - EXPLAIN    : "why does this work?" — the conceptual-justification probe (§3.4).
      - FIND_ERROR : "Tim says X; is he right?" — the error-finding probe (§3.9),
                     e.g. SUB-005 / the ¼+¼=2/8 transfer item.
    """

    ANSWER = "answer"
    EXPLAIN = "explain"
    FIND_ERROR = "find_error"


@dataclass(frozen=True)
class SimulationContext:
    """The turn intent the caller supplies (DATA, not behavior).

    Frozen so a context cannot mutate under the simulator and break reproducibility
    (ARCHITECTURE.md §5). Defaults to a routine ANSWER request, which is the common
    case (the tutor mostly presents solve-it items); the mastery harness sets
    ``request=EXPLAIN`` / ``FIND_ERROR`` when it deliberately probes justification.

    ``claimed_answer`` is the answer a FIND_ERROR item attributes to the fictional
    third party ("Tim wrote 4/3"). A persona who cannot judge reasonableness endorses
    it; a persona who can rejects it. It is ignored for ANSWER / EXPLAIN requests.
    """

    request: RequestType = RequestType.ANSWER
    # The (possibly wrong) answer a FIND_ERROR item presents for judgment, as the
    # learner-facing magnitude. None for non-error-finding requests.
    claimed_answer: Rational | None = None


# ─── The action a persona takes ──────────────────────────────────────────────


@dataclass(frozen=True)
class SimulatedAction:
    """One persona's action on one problem — the Layer-3 output (PROJECT.md §4.1).

    Frozen because an action is a recorded fact about a turn, not mutable state; the
    evaluation pipeline reads these and they must not be rewritten downstream
    (ARCHITECTURE.md §14, CLAUDE.md §8.4). The fields are exactly what §4.1 says
    Layer 3 computes — "what answer they submit, whether they request a hint, how
    long they 'think', what they type if asked to explain" — plus the justification
    flag the mastery model needs to tell procedural fluency from understanding (§3.4).

    - ``submitted_answer``  the answer the persona submits — a SymPy ``Rational``
      magnitude for a numeric item, or a ``bool`` for a YES_NO item (the two forms the
      verifier accepts in-process; ``domain/verifier.py`` ``Submitted`` /
      ``_parse_to_bool``). ``None`` only when the turn is purely an EXPLAIN request with
      no submission. For a FIND_ERROR turn this is the value the persona endorses (the
      claimed value when they accept it).
    - ``requested_hint``    whether the persona asked for a hint before answering
      (resolved deterministically from ``hint_request_probability``; Hugo's >0.70
      signature, §4.2 P3; the ≥1-unassisted-attempt mastery rule, §3.4).
    - ``think_time_seconds`` how long the persona "thought", derived from
      ``response_latency_seconds`` (the engagement-floor signal, §3.4; Cleo's sub-2s
      floor, §4.2 P5).
    - ``can_justify``       whether the persona can actually justify / correctly
      endorse on an EXPLAIN or FIND_ERROR turn. This is the procedure-without-concept
      tell (Priya: right answer, ``can_justify=False``; §4.2 P2). For a routine
      ANSWER turn it reports whether the persona *understands* what it answered.
    - ``explanation``       the text the persona "types" when asked to explain, or
      ``None`` if not asked. Layer 3 produces a SHORT canned string (no LLM); Layer 4
      is where an LLM would render this naturally. A persona that cannot justify
      types a non-justifying string ("I just followed the steps"), which is the
      evidence the mastery model reads — never an LLM judgment.
    """

    submitted_answer: Rational | bool | str | None
    requested_hint: bool
    think_time_seconds: float
    can_justify: bool
    explanation: str | None


# A persona at or above this scaffold-dependence rate is modeled as HINT-DEPENDENT:
# on a KC it does not genuinely understand, a requested hint lets it reproduce the
# correct answer mechanically, while WITHOUT a hint it collapses to a wrong guess
# (Hint-hunter Hugo, §4.2 P3: "executes hints mechanically without generalizing;
# struggles when hints are unavailable"). The threshold is deliberately high so that
# only a genuinely scaffold-dependent persona (Hugo's 0.9) trips it; Priya (0.15),
# Sam (0.2), Nate (0.1) and Cleo (0.05) stay well below and are unaffected. The
# value is the load-bearing knob; 0.7 mirrors §4.2 P3's ">70% hint dependence".
_HINT_DEPENDENCE_THRESHOLD: float = 0.7


# ─── Deterministic resolution of probabilistic behavioral params ─────────────


def _unit_draw(persona_id: str, problem_id: str, salt: str) -> float:
    """A stable pseudo-random value in [0, 1) for one (persona, problem, salt).

    Why a custom hash and not ``random``/``hash()``: reproducibility must hold across
    processes and runs (ARCHITECTURE.md §5 Layer 3 — "same input always yields the
    same output"). Python's built-in ``hash()`` of a string is salted per process, so
    it would give different draws between runs; a module-global ``random.Random`` would
    couple unrelated calls through shared state. We instead derive the draw purely from
    the inputs with SHA-256, so the SAME (persona, problem, salt) always maps to the
    SAME float, and different salts give independent draws for distinct decisions
    (hint vs. engagement) on the same turn.

    The salt namespaces the decision: ``"hint"`` and ``"engagement"`` get independent
    streams so they do not move together.
    """
    digest = hashlib.sha256(f"{persona_id}\x00{problem_id}\x00{salt}".encode()).digest()
    # Take 8 bytes -> an unsigned 64-bit int, scaled into [0, 1). 2**64 is the exact
    # number of distinct values, so the quotient is in [0, 1).
    raw = int.from_bytes(digest[:8], "big")
    return raw / 2.0**64


def _resolves_true(persona_id: str, problem_id: str, salt: str, probability: float) -> bool:
    """Resolve a probability into a deterministic yes/no for this exact turn.

    A draw strictly below the probability is a "yes". With probability 0.0 nothing
    fires (draw is always >= 0); with 1.0 it always fires (draw is always < 1). This
    is the deterministic stand-in for a coin flip: the same persona on the same
    problem flips the same way every time.
    """
    return _unit_draw(persona_id, problem_id, salt) < probability


def _is_hint_dependent(persona: PersonaConfig) -> bool:
    """Whether the persona is modeled as hint-dependent (Hint-hunter Hugo, §4.2 P3).

    A persona at/above ``_HINT_DEPENDENCE_THRESHOLD`` scaffold-dependence "executes
    hints mechanically without generalizing" and "struggles when hints are
    unavailable": the simulator makes its routine answer correct only when it
    requested a hint this turn. Read straight off the config (data, not behavior) so
    the decision stays a pure function of the persona.
    """
    return persona.behavior.scaffold_dependence_rate >= _HINT_DEPENDENCE_THRESHOLD


# ─── The core mapping: KnowledgeMode + format + misconception ⇒ action ───────


def _correct_answer(problem: Problem) -> Rational | str:
    """The problem's correct answer (decided in Layer 1, not here).

    Layer 3 never recomputes math (that is the domain's job); it only reads the
    answer the generator/verifier already established as correct and decides whether
    the persona produces it. For an EXPRESSION item the correct answer is the canonical
    expression STRING (graded by SymPy equivalence), not a magnitude; every other item
    is the SymPy ``correct_value``.
    """
    if problem.answer_kind is AnswerKind.EXPRESSION:
        if problem.correct_expression is None:  # construction bug, not learner input
            raise ValueError(f"expression problem {problem.problem_id} has no correct_expression")
        return problem.correct_expression
    if problem.answer_kind is AnswerKind.INEQUALITY:
        if problem.correct_inequality is None:  # construction bug, not learner input
            raise ValueError(f"inequality problem {problem.problem_id} has no correct_inequality")
        return problem.correct_inequality
    return problem.correct_value


def _misconception_wrong_answer(problem: Problem) -> Rational | str | None:
    """The wrong answer a held misconception yields on this problem, or None.

    Replays the Layer-1 misconception generators (``domain/misconceptions.py``) on the
    problem's operands — the simulator chooses WHICH named error fires, the domain
    owns the arithmetic of WHAT that error produces (single source of truth,
    ARCHITECTURE.md §4). The two across-errors yield a clean numeric magnitude on the
    arithmetic KCs, and the natural-number-bias number-line misplacement yields one on
    a single-operand placement item (Natural-number Nate, §4.2 P1); anything else
    returns ``None`` so the caller falls back to a deterministic guess rather than
    fabricating a value the domain doesn't model.

    For an EXPRESSION item the wrong answer is the named misconception's expression STRING: the
    reversed-operands form (e.g. "7 - p" for "p - 7") for write-expressions, or the distributive-
    error form (e.g. "3*x + 2" for the given "3*(x + 2)") for equivalent-expressions. ``None`` when
    the error changes nothing (a commutative phrase, or a source with no distributable structure),
    so a persona holding the error still answers correctly there.
    """
    if problem.answer_kind is AnswerKind.EXPRESSION:
        if problem.kc is KnowledgeComponentId.EQUIVALENT_EXPRESSIONS:
            return distributive_error(problem.source_expression)
        return reversed_operands(problem.correct_expression)

    if problem.answer_kind is AnswerKind.INEQUALITY:
        # The flipped-direction form (same bound, reversed comparison) — always defined for a real
        # inequality, so a persona holding the error answers wrong on every item.
        return flipped_inequality(problem.correct_inequality)

    operands = problem.operands
    if operands is None:
        return None

    # Number-line placement is the single-operand case: the natural-number bias reads
    # the denominator as a whole-number POSITION, dropping the marker far from where
    # the magnitude belongs (Nate "places bigger-denominator fractions further from
    # zero", §4.2 P1). The verifier classifies this biased_position as MAGNITUDE /
    # natural-number-bias (verifier.py _classify_wrong_answer). The domain owns the
    # arithmetic; we only select that this is the error that fires.
    if problem.kc is KnowledgeComponentId.NUMBER_LINE_PLACEMENT and len(operands) == 1:
        (target,) = operands
        return natural_number_bias_number_line(target.p, target.q).biased_position

    if len(operands) != 2:
        return None

    first, second = operands
    if problem.kc is KnowledgeComponentId.ADDITION_UNLIKE:
        # add-across: a/b + c/d -> (a+c)/(b+d). The canonical Surface-Sam error
        # (¼+¼=2/8, §4.2 P4 / §3.5 S3). Reduced to a Rational VALUE so the verifier
        # classifies it as the add-across misconception (verifier.py _classify).
        wrong = add_across(first.p, first.q, second.p, second.q)
    elif problem.kc is KnowledgeComponentId.SUBTRACTION_UNLIKE:
        # subtract-across: the natural-number-bias subtraction analog (verifier maps
        # this to NATURAL_NUMBER_BIAS / OPERATION).
        wrong = subtract_across(first.p, first.q, second.p, second.q)
    else:
        return None

    if wrong.denominator == 0:
        # An undefined raw fraction (e.g. subtracting equal-looking bottoms) has no
        # magnitude to submit; treat as no clean misconception value here.
        return None
    return wrong.as_rational()


def _deterministic_guess(problem: Problem, persona: PersonaConfig) -> Rational:
    """A fixed, plainly-WRONG answer for NEITHER / no-grip turns (deterministic).

    A persona who does not hold the KC and matches no modeled misconception still has
    to submit *something*; PROJECT.md §4.2 (Cleo) describes "types the shortest
    plausible answer — often the digit she sees in the problem". We model the floor
    case as a digit already on screen: the first operand's DENOMINATOR read as a whole
    number (the natural-number-bias "read the bottom as the amount" tell — and for an
    in-scope proper fraction 0 < n/d < 1, a whole number d >= 2 is plainly the wrong
    magnitude). With no operands we fall back to 0.

    The guess MUST NOT accidentally equal the correct answer (a placement item's single
    operand IS its correct value, for instance). So we guarantee distinctness: if the
    candidate equals ``correct_value`` we add 1, which keeps it a deterministic,
    obviously-wrong magnitude. NOT an LLM and NOT random: same persona + problem ⇒ same
    guess (ARCHITECTURE.md §5 Layer 3).
    """
    del persona  # reserved for future per-persona guess styles; not needed for 2.3
    operands = problem.operands
    candidate = Rational(operands[0].q) if operands else Rational(0)
    if candidate == problem.correct_value:
        candidate = candidate + 1
    return candidate


# Short, canned justification strings. Layer 3 emits these as plain evidence; Layer 4
# (LLM, later) would render them naturally. They are NOT graded by an LLM — the
# mastery model reads ``can_justify``; the text is for the log / Layer-4 input only.
_JUSTIFICATION_UNDERSTOOD = (
    "The pieces have to be the same size before you can combine them, "
    "so I rewrote both with a common denominator first."
)
_JUSTIFICATION_PROCEDURAL = "I just followed the steps I memorized; I'm not sure why it works."
_JUSTIFICATION_NONE = "I don't really know."


def simulate_action(
    persona: PersonaConfig,
    problem: Problem,
    *,
    context: SimulationContext | None = None,
) -> SimulatedAction:
    """Compute the persona's deterministic action on one problem (Layer 3).

    The action is a pure function of the persona's ``KnowledgeMode`` on
    ``problem.kc``, its named misconceptions, the problem's ``surface_format``, and
    the turn's ``request`` (PROJECT.md §4.1; ARCHITECTURE.md §5). The mode → action
    map (PROJECT.md §4.1's "procedure-only / concept-only / both / neither /
    with-named-misconception"):

      - BOTH               → the correct answer; can justify; correctly rejects a
                             wrong claimed answer on a FIND_ERROR turn.
      - PROCEDURE_ONLY     → the CORRECT answer on a routine item (Priya is right),
                             but CANNOT justify and FAILS error-finding: on a
                             FIND_ERROR turn she endorses the (wrong) claimed answer
                             because she only checks "did I run a procedure", never
                             reasonableness (§4.2 P2; the procedure-without-concept
                             marker, misconceptions.py). She never fabricates a wrong
                             NUMBER on a routine item — the tell is the missing
                             justification.
      - WITH_MISCONCEPTION → format-tied collapse (Sam, §4.2 P4): WITHIN the KC's
                             ``format_tied_to`` he answers CORRECTLY ("looks fluent in
                             one format"); in ANY OTHER format the same KC collapses to
                             his misconception's wrong answer (add-across), which the
                             verifier classifies OPERATION. This is the crux of Sam and
                             the evidence that defeats blocked-practice mastery (§3.4).
      - CONCEPT_ONLY       → understands the concept (can justify, correctly rejects a
                             wrong claim) but is not procedurally fluent, so on a
                             routine ANSWER turn it may SLIP the procedure and submit a
                             deterministic wrong value. Defined for completeness;
                             neither committed persona uses it (§4.1 enumerates it).
      - NEITHER            → no grip: a deterministic guess, cannot justify. Covers
                             unconfigured KCs (``mode_for`` returns NEITHER).

    Cross-cutting on the no-genuine-understanding modes (NEITHER / WITH_MISCONCEPTION
    / PROCEDURE_ONLY): a HINT-DEPENDENT persona — one whose ``scaffold_dependence_rate``
    is at/above ``_HINT_DEPENDENCE_THRESHOLD`` — answers a routine item CORRECTLY when
    it requested a hint this turn (executing the scaffold mechanically) and WRONG when
    it did not (Hint-hunter Hugo, §4.2 P3). Because Hugo's hint-request probability is
    >0.70 and his correct answers are always hinted, he can never produce an
    unscaffolded correct — the evidence the §3.4 rule-3 gate requires.

    Behavioral params are resolved deterministically (``_resolves_true`` /
    ``think_time``): same (persona, problem) ⇒ same hint decision and think time.
    """
    ctx = context if context is not None else SimulationContext()
    mode = persona.mode_for(problem.kc)

    # Hint request and think time are behavioral, independent of the answer logic, and
    # resolved deterministically from the persona's params keyed on this exact turn.
    requested_hint = _resolves_true(
        persona.persona_id,
        problem.problem_id,
        "hint",
        persona.behavior.hint_request_probability,
    )
    # think_time derives directly from the persona's characteristic latency (§4.1).
    # Layer 3 reports the characteristic latency as the think time; the engagement
    # floor (§3.4) is carried separately on the config and read by the mastery model.
    think_time_seconds = persona.behavior.response_latency_seconds

    # Whether the persona *understands* the KC (drives can_justify / FIND_ERROR /
    # CONCEPT_ONLY rejection). Only BOTH and CONCEPT_ONLY carry genuine concept.
    understands = mode in (KnowledgeMode.BOTH, KnowledgeMode.CONCEPT_ONLY)

    submitted, can_justify = _resolve_answer_and_justification(
        persona, problem, mode, ctx, requested_hint=requested_hint
    )

    explanation = _explanation_for(ctx.request, understands, mode)

    return SimulatedAction(
        submitted_answer=submitted,
        requested_hint=requested_hint,
        think_time_seconds=think_time_seconds,
        can_justify=can_justify,
        explanation=explanation,
    )


def _resolve_answer_and_justification(
    persona: PersonaConfig,
    problem: Problem,
    mode: KnowledgeMode,
    ctx: SimulationContext,
    *,
    requested_hint: bool,
) -> tuple[Rational | bool | str | None, bool]:
    """The submitted answer + the can_justify flag for this (mode, request).

    Split out of ``simulate_action`` to keep each function under the §6 length
    guidance and to make the mode → (answer, justify) table readable in one place.
    ``requested_hint`` is threaded in so the hint-dependent path (Hugo, §4.2 P3) can
    make a routine answer correct only WHEN a hint was requested this turn.
    """
    # FIND_ERROR is its own path: the persona judges a claimed answer rather than
    # producing a fresh one. Whether they endorse the (typically wrong) claim is the
    # error-finding signal the mastery model needs (§3.9). A conceptual learner
    # rejects it (submits the correct value); a procedural/no-grip learner endorses it.
    if ctx.request is RequestType.FIND_ERROR:
        return _resolve_find_error(problem, mode, ctx)

    # EXPLAIN with no answer expectation: the turn is purely a justification probe.
    # We still report can_justify so the mastery model sees whether the explanation
    # is genuine; no numeric answer is submitted on a pure-explain turn.
    if ctx.request is RequestType.EXPLAIN:
        return None, mode in (KnowledgeMode.BOTH, KnowledgeMode.CONCEPT_ONLY)

    # A YES_NO item (the number-line "is a > b?" comparison, or the transfer probe's
    # error-finding "is this right?" step) is a JUDGMENT, not a numeric solve — answered
    # with a bool, per the persona's grip on the magnitude, for EVERY mode. Intercepts
    # before the numeric mode branches so a yes/no item never collapses to a Rational the
    # verifier scores wrong regardless of knowledge.
    if problem.answer_kind is AnswerKind.YES_NO:
        return _resolve_yes_no(persona, problem, mode, requested_hint=requested_hint)

    # ANSWER (routine solve-it) — the common case.
    if mode is KnowledgeMode.BOTH:
        return _correct_answer(problem), True

    # Hint-dependent persona (Hugo, §4.2 P3) on a mode without genuine understanding:
    # WITH a hint he reproduces the correct answer mechanically; WITHOUT one he is
    # wrong. This sits BEFORE the per-mode branches so it overrides the routine answer
    # for NEITHER / WITH_MISCONCEPTION / PROCEDURE_ONLY. He still cannot justify — the
    # scaffold supplies the answer, not understanding — so can_justify is False.
    if _is_hint_dependent(persona) and mode not in (
        KnowledgeMode.BOTH,
        KnowledgeMode.CONCEPT_ONLY,
    ):
        if requested_hint:
            return _correct_answer(problem), False
        return _deterministic_guess(problem, persona), False

    if mode is KnowledgeMode.PROCEDURE_ONLY:
        # Priya: routine answer is CORRECT, but she cannot justify it (§4.2 P2). No
        # fabricated wrong number on a routine item.
        return _correct_answer(problem), False

    if mode is KnowledgeMode.CONCEPT_ONLY:
        # Understands but may slip the procedure: a deterministic wrong value on the
        # routine item, yet able to justify the concept. (No committed persona uses
        # this; defined for completeness per §4.1.)
        return _deterministic_guess(problem, persona), True

    if mode is KnowledgeMode.WITH_MISCONCEPTION:
        return _resolve_with_misconception(persona, problem), False

    # NEITHER (incl. unconfigured KCs): a deterministic guess, no justification.
    return _deterministic_guess(problem, persona), False


def _yes_no_truth(problem: Problem) -> bool:
    """The truth value of a YES_NO item — the same judgment the verifier scores against.

    Mirrors ``domain.verifier._verify_yes_no`` so the simulator and the oracle agree:
    a ``"greater"`` item is ``operands[0] > operands[1]``; any other relation
    (``"equal"``) is ``operands[0] == operands[1]``. A malformed item (no operand pair)
    is a construction bug, not learner input, so we fail loudly (CLAUDE.md §8.5), exactly
    as the verifier does.
    """
    operands = problem.operands
    if operands is None or len(operands) != 2:
        raise ValueError(
            f"yes/no problem {problem.problem_id!r} needs exactly two operands to judge"
        )
    if problem.yes_no_relation == "greater":
        return bool(operands[0] > operands[1])
    return bool(operands[0] == operands[1])


def _resolve_yes_no(
    persona: PersonaConfig,
    problem: Problem,
    mode: KnowledgeMode,
    *,
    requested_hint: bool,
) -> tuple[bool, bool]:
    """The yes/no judgment + can_justify for a YES_NO item, per the persona's mode.

    The truth is what SymPy computes in the verifier (``_yes_no_truth``). The mode → action
    map mirrors the numeric path's philosophy (deterministic, §4.1):

      - BOTH / CONCEPT_ONLY (genuine concept) → the correct judgment; can justify.
      - hint-dependent (Hugo) WITH a hint this turn → the correct judgment, reproduced
        mechanically (no justification) — the same scaffold-supplies-the-answer rule the
        numeric path uses.
      - otherwise (PROCEDURE_ONLY / WITH_MISCONCEPTION / NEITHER, no genuine concept) →
        the WRONG judgment. On the probe's error-finding "is this right?" item that is the
        §4.2 P2 / §3.9 endorse-the-error failure (they accept a wrong claim); on a plain
        comparison it is a misjudged magnitude (verifier ErrorCategory.MAGNITUDE). Never a
        justification.
    """
    truth = _yes_no_truth(problem)
    if mode in (KnowledgeMode.BOTH, KnowledgeMode.CONCEPT_ONLY):
        return truth, True
    if _is_hint_dependent(persona) and requested_hint:
        return truth, False
    return (not truth), False


def _resolve_with_misconception(persona: PersonaConfig, problem: Problem) -> Rational | str:
    """Surface Sam's format-tied collapse (PROJECT.md §4.2 Persona 4).

    The crux of Sam: his grip on the KC is tied to ONE representation
    (``KnowledgeState.format_tied_to``). WITHIN that tied format he "looks fluent" and
    answers CORRECTLY; the moment the SAME KC appears in a DIFFERENT format his grip
    collapses to the misconception's wrong answer (add-across), which the verifier
    classifies as an OPERATION error (§3.5 S3). This is the evidence that distinguishes
    real mastery from block-fluency and defeats blocked practice (§3.4 rule 4).

    Determinism is structural here: the collapse depends only on whether
    ``problem.surface_format`` equals the tied format — no draw needed.
    """
    state = persona.knowledge[problem.kc]
    tied_format: Representation | None = state.format_tied_to

    if tied_format is not None and problem.surface_format == tied_format:
        # In his comfort format he reproduces the correct answer (fluent-looking).
        return _correct_answer(problem)

    # Out of his tied format: the misconception's wrong value if the domain models one
    # for this KC; otherwise a deterministic guess (no clean misconception magnitude).
    wrong = _misconception_wrong_answer(problem)
    if wrong is not None:
        return wrong
    return _deterministic_guess(problem, persona)


def _resolve_find_error(
    problem: Problem,
    mode: KnowledgeMode,
    ctx: SimulationContext,
) -> tuple[Rational | str | None, bool]:
    """Resolve a FIND_ERROR turn: does the persona catch the claimed wrong answer?

    The error-finding probe (§3.9) presents a third party's claimed answer
    (``ctx.claimed_answer``) and asks "is this right?". A learner who understands the
    concept rejects a wrong claim and supplies the correct value (``can_justify=True``).
    A procedural / no-grip / misconception learner cannot judge reasonableness and
    ENDORSES the claim — submitting the claimed (wrong) value with ``can_justify=False``.
    This is exactly how Priya "fails error-finding" (§4.2 P2) and how the transfer
    probe catches procedural fluency masquerading as mastery.
    """
    understands = mode in (KnowledgeMode.BOTH, KnowledgeMode.CONCEPT_ONLY)
    if understands:
        # Rejects the wrong claim, gives the correct answer, and can say why.
        return _correct_answer(problem), True

    # Cannot judge reasonableness → endorses the claimed answer if one was presented;
    # if none was, falls back to the correct value but still cannot justify (the tell
    # is the missing justification, not necessarily a wrong number — §4.2 P2).
    endorsed = ctx.claimed_answer if ctx.claimed_answer is not None else _correct_answer(problem)
    return endorsed, False


def _explanation_for(
    request: RequestType,
    understands: bool,
    mode: KnowledgeMode,
) -> str | None:
    """The short canned explanation string, or None when no explanation was asked for.

    Layer 3 emits plain evidence text — NOT an LLM rendering (CLAUDE.md §8.1, §8.3).
    A persona that understands types a genuine justification; a procedural learner
    types a non-justifying "I followed the steps" string; a no-grip learner types
    "I don't know". The mastery model never parses this text for correctness (that
    would be the §8.2 anti-pattern); it reads ``can_justify``. The text exists for the
    diagnostic log and as the input Layer 4 would render naturally.
    """
    if request is RequestType.ANSWER:
        # A routine solve-it turn does not ask for words; no explanation produced.
        return None
    if understands:
        return _JUSTIFICATION_UNDERSTOOD
    if mode is KnowledgeMode.PROCEDURE_ONLY:
        return _JUSTIFICATION_PROCEDURAL
    return _JUSTIFICATION_NONE


__all__ = [
    "RequestType",
    "SimulatedAction",
    "SimulationContext",
    "simulate_action",
]
