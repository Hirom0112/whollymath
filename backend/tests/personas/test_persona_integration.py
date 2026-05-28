"""Week-2 persona integration checkpoint — Priya & Sam, end-to-end (PROJECT.md §6).

These are the §6 Week-2 checkpoint asserted as code: "Priya and Sam can each take a
tutor session end-to-end; we can read the logs and see expected adversarial
behavior." They are ALSO the mastery model's integration suite (CLAUDE.md §9: "the
five personas serve as integration tests for the mastery model — if Surface Sam can
hit 'mastered', the interleaving rule is broken").

They drive each persona through the REACTIVE ``TutorSession`` (Slice 2.6) via the
persona-run driver (``personas/run.py``), then assert on the recorded run:

  - Surface Sam: across an INTERLEAVED, multi-format addition sequence he is correct
    in his tied SYMBOLIC format and produces the add-across error (verifier-confirmed
    OPERATION) in every other format — so ``declare_mastery`` returns NOT mastered,
    blocked by rule 2 (representation diversity) and rule 4 (interleaving). This IS
    the false-positive-mastery defense working (PROJECT.md §3.11).
  - Procedure Priya: she answers routine operation items CORRECTLY (looks fluent),
    but on a FIND_ERROR turn she ENDORSES the wrong claimed answer with
    ``can_justify=False`` — the procedure-without-concept signature (§4.2 P2).

Correctness here means exactly what it means in production: the tutor's own SymPy
verifier decided it (ARCHITECTURE.md §9). No LLM, no DB, no randomness without a
seed — the whole path is deterministic (PROJECT.md §4.1).
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.domain.misconceptions import MisconceptionId
from app.domain.verifier import ErrorCategory
from app.mastery.mastery_model import declare_mastery
from app.personas.priya import PRIYA
from app.personas.run import ProblemSpec, run_persona
from app.personas.sam import SAM
from app.personas.simulator import RequestType, SimulationContext
from app.policy.surface_states import SurfaceState
from sympy import Rational

_KC_ADD = KnowledgeComponentId.ADDITION_UNLIKE
_KC_SUB = KnowledgeComponentId.SUBTRACTION_UNLIKE


# ─── Surface Sam: interleaved, multi-format → NOT mastered (§3.11, §4.2 P4) ──


def _sam_interleaved_sequence() -> list[ProblemSpec]:
    """An INTERLEAVED, multi-format addition sequence for Sam.

    Addition appears in his tied SYMBOLIC format (where he is fluent) AND in the
    AREA_MODEL and NUMBER_LINE formats (where the SAME KC collapses to add-across).
    A SUBTRACTION item is interleaved in so the run is genuinely mixed-KC, not a
    blocked addition run — exactly the practice shape the §3.4 rule-4 interleaving
    gate is defined over (and which a blocked run would game). Distinct seeds keep
    each problem a distinct, deterministic item.
    """
    return [
        ProblemSpec(kc=_KC_ADD, seed=1, surface_format=Representation.SYMBOLIC),
        ProblemSpec(kc=_KC_SUB, seed=2, surface_format=Representation.SYMBOLIC),
        ProblemSpec(kc=_KC_ADD, seed=3, surface_format=Representation.AREA_MODEL),
        ProblemSpec(kc=_KC_ADD, seed=4, surface_format=Representation.NUMBER_LINE),
        ProblemSpec(kc=_KC_ADD, seed=5, surface_format=Representation.SYMBOLIC),
    ]


def test_sam_correct_in_tied_format_addcross_elsewhere_verifier_confirmed() -> None:
    """Sam answers CORRECTLY in his tied symbolic format and makes the add-across
    OPERATION error in every other format — confirmed by the tutor's SymPy verifier
    and the named misconception (§4.2 P4 / §3.5 S3)."""
    run = run_persona(SAM, _sam_interleaved_sequence())

    add_turns = [t for t in run.turns if t.problem.kc == _KC_ADD]
    for turn in add_turns:
        assert turn.result is not None
        if turn.problem.surface_format == Representation.SYMBOLIC:
            # His tied format: fluent-looking, verifier says correct.
            assert turn.result.correct is True, "Sam must look fluent in his tied format"
            assert turn.result.error_category is ErrorCategory.NONE
        else:
            # Any other format: the SAME KC collapses to the add-across wrong answer,
            # which the verifier classifies OPERATION and names add-across-error.
            assert turn.result.correct is False
            assert turn.result.error_category is ErrorCategory.OPERATION
            assert turn.result.matched_misconception is MisconceptionId.ADD_ACROSS_ERROR


def test_sam_is_not_mastered_blocked_by_rules_2_and_4() -> None:
    """THE false-positive-mastery defense (PROJECT.md §3.11; CLAUDE.md §2): driving
    Sam through an interleaved, multi-format addition sequence does NOT let him reach
    mastery on KC_addition_unlike. declare_mastery returns False, and the reasons name
    BOTH rule 2 (correct in only one representation) and rule 4 (no interleaved
    mastery set across ≥2 KCs) — if Sam could hit 'mastered', the interleaving rule
    would be broken."""
    run = run_persona(SAM, _sam_interleaved_sequence())

    mastered, reasons = declare_mastery(_KC_ADD, run.observations)

    assert mastered is False, "Sam must NOT reach mastery — that is the §3.11 defense"
    blob = " ".join(reasons).lower()
    assert "representation" in blob, "rule 2 must block: only one correct representation"
    assert "interleav" in blob, "rule 4 must block: not an interleaved set across ≥2 KCs"


def test_sam_run_drives_the_reactive_surface() -> None:
    """The run drives the §3.6 reactive surface: Sam's cross-format add-across errors
    move the surface off S1 (an OPERATION error routes toward the fraction bars, S3),
    so the recorded walk is not a flat S1 — the loop really is reactive (Slice 2.6)."""
    run = run_persona(SAM, _sam_interleaved_sequence())

    assert run.states_visited[0] == SurfaceState.SYMBOLIC_FOCUS  # starts in S1
    # At least one of his errors moved the surface to a scaffolded state.
    assert any(s != SurfaceState.SYMBOLIC_FOCUS for s in run.states_visited)


# ─── Procedure Priya: fluent routine, fails error-finding (§4.2 P2) ──────────


def _priya_routine_then_error_finding() -> list[ProblemSpec]:
    """Priya on her operation KCs: two routine ANSWER items (addition then
    subtraction), then a FIND_ERROR addition item whose claimed answer is the
    add-across wrong value (5/7 for the seed-1 item 3/4 + 2/3).

    NOTE — the FULL catch (demotion to scaffolded practice on error-finding failure)
    is the transfer probe (S5, Slice 3.7), which does NOT exist yet. At Week 2 we
    assert the captured EVIDENCE: she gets routine items right but endorses the wrong
    claim and cannot justify it. We do NOT build the transfer probe here.
    """
    return [
        ProblemSpec(kc=_KC_ADD, seed=1, surface_format=Representation.SYMBOLIC),
        ProblemSpec(kc=_KC_SUB, seed=2, surface_format=Representation.SYMBOLIC),
        ProblemSpec(
            kc=_KC_ADD,
            seed=1,  # same item as turn 1, so the claimed wrong answer is its add-across
            surface_format=Representation.SYMBOLIC,
            context=SimulationContext(
                request=RequestType.FIND_ERROR,
                claimed_answer=Rational(5, 7),  # add-across of 3/4 + 2/3
            ),
        ),
    ]


def test_priya_answers_routine_operation_items_correctly() -> None:
    """§4.2 P2 'slow but correct on standard-form problems': Priya's routine ANSWER
    turns verify correct (the tutor's SymPy verdict), looking fluent."""
    run = run_persona(PRIYA, _priya_routine_then_error_finding())

    routine = [t for t in run.turns if t.context.request is RequestType.ANSWER]
    assert len(routine) == 2
    for turn in routine:
        assert turn.result is not None
        assert turn.result.correct is True, "Priya must get routine operation items right"
        assert turn.result.error_category is ErrorCategory.NONE


def test_priya_endorses_the_wrong_answer_on_find_error_without_justification() -> None:
    """§4.2 P2 'fails error-finding': on a FIND_ERROR turn Priya ENDORSES the wrong
    claimed answer and cannot justify it (can_justify=False) — the procedure-without-
    concept signature. The endorsed answer is the (wrong) claim, so the tutor's
    verifier rightly marks the turn incorrect: the captured evidence is that she
    accepted a wrong answer she should have rejected.

    NOTE: the FULL catch — demotion to scaffolded practice — is the transfer probe
    (S5, Slice 3.7), not built yet. Week 2 asserts only the captured evidence."""
    run = run_persona(PRIYA, _priya_routine_then_error_finding())

    find_error = [t for t in run.turns if t.context.request is RequestType.FIND_ERROR]
    assert len(find_error) == 1
    turn = find_error[0]

    # She endorsed the claimed (wrong) answer rather than rejecting it.
    assert turn.action.submitted_answer == Rational(5, 7)
    # The tell of procedure-without-concept: she cannot justify (§4.2 P2).
    assert turn.action.can_justify is False
    # Endorsing the wrong claim is, by the verifier, an incorrect turn.
    assert turn.result is not None
    assert turn.result.correct is False


# ─── Determinism (PROJECT.md §4.1; CLAUDE.md §9) ─────────────────────────────


def test_persona_runs_are_deterministic() -> None:
    """Same persona + same sequence ⇒ identical run: same submitted answers, same
    correctness verdicts, same surface walk, same final state. This reproducibility
    is what makes the persona suite a trustworthy integration suite."""
    for persona, sequence in (
        (SAM, _sam_interleaved_sequence()),
        (PRIYA, _priya_routine_then_error_finding()),
    ):
        first = run_persona(persona, sequence)
        second = run_persona(persona, sequence)

        assert first.final_state == second.final_state
        assert first.states_visited == second.states_visited
        assert [t.action.submitted_answer for t in first.turns] == [
            t.action.submitted_answer for t in second.turns
        ]
        assert [(t.result.correct if t.result is not None else None) for t in first.turns] == [
            (t.result.correct if t.result is not None else None) for t in second.turns
        ]
