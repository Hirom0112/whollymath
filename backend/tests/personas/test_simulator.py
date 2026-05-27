"""Behavioral tests for the Layer-3 persona simulator (Slice 2.3).

These are the MANDATORY-TDD persona behavioral tests CLAUDE.md §2 quotes verbatim:
"Procedure Priya correctly answers symbolic addition, fails error-finding. Surface
Sam correctly handles blocked practice, fails interleaved. ... These tests are
deterministic — same input, same output, every time."

They exercise the simulator through the SAME oracle the tutor uses — the Layer-1
SymPy verifier (``domain/verifier.py``) — so "correct" / "wrong" here means exactly
what it means in production (ARCHITECTURE.md §9: SymPy decides). The tests assert the
five ``KnowledgeMode`` → action mappings (PROJECT.md §4.1), Sam's format-tied collapse
(§4.2 P4), Priya's procedure-without-concept (§4.2 P2), and determinism (§4.1).

No LLM, no DB, no randomness without a seed — the simulator is pure code (§8.1, §8.3).
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.domain.misconceptions import MisconceptionId
from app.domain.problem_generators import Problem, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.personas.persona_config import (
    BehavioralParameters,
    KnowledgeMode,
    KnowledgeState,
    PersonaConfig,
)
from app.personas.priya import PRIYA
from app.personas.sam import SAM
from app.personas.simulator import (
    RequestType,
    SimulatedAction,
    SimulationContext,
    simulate_action,
)
from sympy import Rational

# ─── Shared fixtures (deterministic problems built from fixed seeds) ─────────
#
# A fixed seed makes the underlying operands and correct answer reproducible, so a
# test that says "Priya is correct" is checking a stable, known problem every run.

_ADD_SEED = 1  # 3/4 + 2/3 = 17/12; add-across -> 5/7 (a clean, distinct wrong value)


def _symbolic_addition() -> Problem:
    return generate_problem(
        KnowledgeComponentId.ADDITION_UNLIKE, _ADD_SEED, Representation.SYMBOLIC
    )


def _area_model_addition() -> Problem:
    """The SAME addition KC, in a DIFFERENT format — the interleaving/transfer crux."""
    return generate_problem(
        KnowledgeComponentId.ADDITION_UNLIKE, _ADD_SEED, Representation.AREA_MODEL
    )


# ─── Procedure Priya: correct on symbolic addition, fails error-finding ──────
# (CLAUDE.md §2 mandatory test #1; PROJECT.md §4.2 Persona 2.)


def test_priya_correctly_answers_symbolic_addition() -> None:
    """§4.2 P2: 'slow but correct on standard-form problems.'

    PROCEDURE_ONLY on KC_addition_unlike → she submits the CORRECT sum on a routine
    symbolic item, confirmed by the domain verifier (the tutor's own oracle).
    """
    problem = _symbolic_addition()
    action = simulate_action(PRIYA, problem)

    result = verify(problem, action.submitted_answer)
    assert result.is_correct, "Priya must get a routine symbolic addition right"
    assert result.error_category is ErrorCategory.NONE
    # The tell is the MISSING justification, not a wrong number (§4.2 P2).
    assert action.can_justify is False


def test_priya_fails_error_finding() -> None:
    """§4.2 P2 / §3.9: Priya cannot judge reasonableness, so she ENDORSES a wrong claim.

    On a FIND_ERROR turn she only checks 'did I run a procedure' and accepts the
    presented-but-wrong answer (e.g. SUB-005's 'yes (4/3)'). She submits the claimed
    wrong value and cannot justify — exactly the error-finding failure the transfer
    probe is designed to catch.
    """
    problem = _symbolic_addition()
    claimed_wrong = Rational(5, 7)  # the add-across value for 3/4 + 2/3, not the sum
    action = simulate_action(
        PRIYA,
        problem,
        context=SimulationContext(request=RequestType.FIND_ERROR, claimed_answer=claimed_wrong),
    )

    assert action.can_justify is False, "Priya cannot justify an error-finding judgment"
    # She endorses the wrong claim rather than rejecting it...
    assert action.submitted_answer == claimed_wrong
    # ...and the verifier confirms her endorsed answer is WRONG (she failed to find it).
    assert verify(problem, action.submitted_answer).is_correct is False


def test_priya_cannot_explain_why() -> None:
    """§4.2 P2: 'cannot explain why she did each step.'

    On an EXPLAIN turn she produces a non-justifying string and ``can_justify`` is
    False. The mastery model reads the flag, never the text (CLAUDE.md §8.2).
    """
    problem = _symbolic_addition()
    action = simulate_action(PRIYA, problem, context=SimulationContext(request=RequestType.EXPLAIN))

    assert action.can_justify is False
    assert action.explanation is not None
    # No numeric answer is submitted on a pure-explain turn.
    assert action.submitted_answer is None


# ─── Surface Sam: correct in his tied format, collapses on format change ─────
# (CLAUDE.md §2 mandatory test #2; PROJECT.md §4.2 Persona 4.)


def test_sam_correct_in_tied_format_blocked_practice() -> None:
    """§4.2 P4: 'accuracy climbs to near-100% within a single homogeneous format block.'

    Sam's addition KC is tied to the symbolic format. A symbolic item is inside his
    block, so he reproduces the CORRECT answer — block-fluency that LOOKS like mastery.
    """
    problem = _symbolic_addition()
    assert problem.surface_format is Representation.SYMBOLIC
    action = simulate_action(SAM, problem)

    result = verify(problem, action.submitted_answer)
    assert result.is_correct, "Sam looks fluent inside his tied (symbolic) format"


def test_sam_fails_when_format_changes_interleaved() -> None:
    """§4.2 P4 / §3.4 rule 4: the SAME KC in a DIFFERENT format collapses Sam.

    Present KC_addition_unlike in the area model (not his tied symbolic format). His
    grip collapses to the add-across wrong answer, which the verifier classifies as an
    OPERATION error matching add-across-error — the evidence that distinguishes real
    mastery from blocked-practice fluency and defeats interleaving.
    """
    problem = _area_model_addition()
    assert problem.surface_format is Representation.AREA_MODEL
    action = simulate_action(SAM, problem)

    result = verify(problem, action.submitted_answer)
    assert result.is_correct is False, "Sam must fail the SAME KC in a new format"
    assert result.error_category is ErrorCategory.OPERATION
    assert result.matched_misconception is MisconceptionId.ADD_ACROSS_ERROR


def test_sam_blocked_vs_interleaved_differ_on_same_problem_math() -> None:
    """The collapse is purely format-driven: same operands, opposite outcomes.

    Same seed ⇒ identical operands and correct answer in both formats; only the
    presentation differs. Sam is right in one and wrong in the other — the cross-format
    drop §4.2 P4 names, with the math held constant so format is the only variable.
    """
    symbolic = _symbolic_addition()
    area_model = _area_model_addition()
    assert symbolic.operands == area_model.operands
    assert symbolic.correct_value == area_model.correct_value

    symbolic_correct = verify(symbolic, simulate_action(SAM, symbolic).submitted_answer).is_correct
    area_correct = verify(area_model, simulate_action(SAM, area_model).submitted_answer).is_correct
    assert symbolic_correct is True
    assert area_correct is False


# ─── The KnowledgeMode → action map (PROJECT.md §4.1) ────────────────────────


def _persona_with_single_kc(
    mode: KnowledgeMode,
    *,
    persona_id: str,
    misconceptions: tuple[MisconceptionId, ...] = (),
    format_tied_to: Representation | None = None,
) -> PersonaConfig:
    """A minimal one-KC persona for exercising a single mode in isolation.

    Built on the addition KC so the misconception generators have operands to replay.
    Used for BOTH / CONCEPT_ONLY / NEITHER which no committed persona exercises.
    """
    return PersonaConfig(
        persona_id=persona_id,
        name=persona_id,
        knowledge={
            KnowledgeComponentId.ADDITION_UNLIKE: KnowledgeState(
                kc_id=KnowledgeComponentId.ADDITION_UNLIKE,
                mode=mode,
                format_tied_to=format_tied_to,
            )
        },
        misconceptions=misconceptions,
        behavior=BehavioralParameters(
            response_latency_seconds=5.0,
            hint_request_probability=0.0,
            engagement_floor=0.8,
            scaffold_dependence_rate=0.1,
        ),
    )


def test_both_mode_answers_correctly_and_can_justify() -> None:
    """BOTH = genuine mastery: correct answer AND able to justify (§4.1)."""
    persona = _persona_with_single_kc(KnowledgeMode.BOTH, persona_id="both_persona")
    problem = _symbolic_addition()

    answer_action = simulate_action(persona, problem)
    assert verify(problem, answer_action.submitted_answer).is_correct is True

    explain_action = simulate_action(
        persona, problem, context=SimulationContext(request=RequestType.EXPLAIN)
    )
    assert explain_action.can_justify is True


def test_both_mode_rejects_wrong_claim_on_error_finding() -> None:
    """BOTH correctly REJECTS a wrong claimed answer and supplies the correct one."""
    persona = _persona_with_single_kc(KnowledgeMode.BOTH, persona_id="both_persona")
    problem = _symbolic_addition()
    action = simulate_action(
        persona,
        problem,
        context=SimulationContext(request=RequestType.FIND_ERROR, claimed_answer=Rational(5, 7)),
    )
    assert action.can_justify is True
    assert verify(problem, action.submitted_answer).is_correct is True


def test_concept_only_can_justify_but_slips_procedure() -> None:
    """CONCEPT_ONLY: understands (can justify) but may slip the routine procedure (§4.1).

    No committed persona uses this mode; the test pins the defined-for-completeness
    behavior so the mapping is enforced, not merely documented.
    """
    persona = _persona_with_single_kc(KnowledgeMode.CONCEPT_ONLY, persona_id="concept_persona")
    problem = _symbolic_addition()
    action = simulate_action(persona, problem)

    assert action.can_justify is True
    # Slips the procedure on the routine item → not the correct sum.
    assert verify(problem, action.submitted_answer).is_correct is False


def test_neither_mode_guesses_and_cannot_justify() -> None:
    """NEITHER (incl. unconfigured KCs): a deterministic wrong guess, no justification."""
    persona = _persona_with_single_kc(KnowledgeMode.NEITHER, persona_id="neither_persona")
    problem = _symbolic_addition()
    action = simulate_action(persona, problem)

    assert action.can_justify is False
    assert verify(problem, action.submitted_answer).is_correct is False


def test_unconfigured_kc_is_treated_as_neither() -> None:
    """A KC the persona says nothing about defaults to NEITHER (mode_for); it guesses.

    Priya is configured only on operational KCs; on number-line placement she has no
    grip, so she does not produce the correct placement.
    """
    problem = generate_problem(
        KnowledgeComponentId.NUMBER_LINE_PLACEMENT, 3, Representation.NUMBER_LINE
    )
    assert PRIYA.mode_for(problem.kc) is KnowledgeMode.NEITHER
    action = simulate_action(PRIYA, problem)
    assert action.can_justify is False
    assert verify(problem, action.submitted_answer).is_correct is False


# ─── Determinism (CLAUDE.md §2: same input, same output, every time) ─────────


def test_simulate_action_is_deterministic_across_calls() -> None:
    """Same (persona, problem) ⇒ identical SimulatedAction, every call (§4.1)."""
    problem = _symbolic_addition()
    first = simulate_action(SAM, problem)
    second = simulate_action(SAM, problem)
    assert first == second
    assert isinstance(first, SimulatedAction)


def test_determinism_holds_for_all_personas_and_request_types() -> None:
    """Determinism across both committed personas and all three request types."""
    problem = _symbolic_addition()
    for persona in (PRIYA, SAM):
        for request in RequestType:
            ctx = SimulationContext(request=request, claimed_answer=Rational(5, 7))
            assert simulate_action(persona, problem, context=ctx) == simulate_action(
                persona, problem, context=ctx
            )


def test_hint_decision_is_deterministic_and_in_range() -> None:
    """The probabilistic hint flag resolves to the SAME bool for a given turn.

    With Priya's low hint_request_probability (0.1) and Sam's (0.2), the flag is a
    stable boolean — never a fresh coin flip — keyed on (persona, problem).
    """
    problem = _symbolic_addition()
    for persona in (PRIYA, SAM):
        flags = {simulate_action(persona, problem).requested_hint for _ in range(5)}
        assert len(flags) == 1  # identical every call


def test_think_time_derives_from_response_latency() -> None:
    """think_time comes from the persona's response_latency_seconds (§4.1)."""
    problem = _symbolic_addition()
    assert simulate_action(PRIYA, problem).think_time_seconds == (
        PRIYA.behavior.response_latency_seconds
    )
    assert simulate_action(SAM, problem).think_time_seconds == (
        SAM.behavior.response_latency_seconds
    )


def test_certain_hint_probability_fires_uncertain_never() -> None:
    """A 1.0 hint probability always requests a hint; 0.0 never does (resolution edges).

    Confirms the deterministic resolver maps the probability bounds correctly, the
    property Hugo's >0.70 signature (§4.2 P3) will rely on in a later slice.
    """
    problem = _symbolic_addition()
    always = _persona_with_single_kc(KnowledgeMode.BOTH, persona_id="always_hint")
    object.__setattr__(
        always,
        "behavior",
        BehavioralParameters(
            response_latency_seconds=5.0,
            hint_request_probability=1.0,
            engagement_floor=0.8,
            scaffold_dependence_rate=0.1,
        ),
    )
    never = _persona_with_single_kc(KnowledgeMode.BOTH, persona_id="never_hint")
    assert simulate_action(always, problem).requested_hint is True
    assert simulate_action(never, problem).requested_hint is False


# ─── No-LLM invariant (ARCHITECTURE.md §14 invariant 1; CLAUDE.md §8.1) ──────


def test_simulator_imports_no_llm() -> None:
    """Layer 3 is pure code: the simulator module never imports the llm package.

    Guards ARCHITECTURE.md §14 invariant 1 / CLAUDE.md §8.1 structurally — if someone
    later wires an LLM into the deterministic action computation, this test fails.
    """
    import app.personas.simulator as simulator_module

    source = simulator_module.__file__
    assert source is not None
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    assert "app.llm" not in text
    assert "import openai" not in text
    assert "anthropic" not in text
