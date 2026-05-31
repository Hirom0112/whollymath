"""Behavioral tests for KC_statistical_questions — a Grade-6 (Unit 7) lesson (2026-05-30).

Exercises the new KC through the SAME oracle the tutor uses (the SymPy verifier), so
"correct"/"wrong" means exactly what it means in production (ARCHITECTURE.md §9). Pins:
the generator builds a clean, in-scope YES/NO "is this a statistical question?" item over a
curated bank of statistical (anticipates variability → YES) and non-statistical (a single
value → NO) question templates; the verifier confirms the correct yes/no and (per the existing
YES_NO contract) scores a wrong judgment MAGNITUDE with no operand-classified misconception;
the worked example lands on the canonical verdict; and generation is deterministic
(PROJECT.md §4.1). Mandatory-TDD domain Layer 1 (CLAUDE.md §2). Skill: CCSS 6.SP.1 — recognize
a statistical question as one that anticipates variability in the data.

NOTE on the YES/NO wrong-answer path (build-brief flag): the YES_NO answer kind does NOT use the
operand-based ``_WRONG_ANSWER_MODELS`` mechanism. ``_verify_yes_no`` computes truth by SymPy over
the two operands and, on a wrong judgment, returns ``ErrorCategory.MAGNITUDE`` with
``matched_misconception=None`` — it never over-claims a specific misconception (exactly how the
existing EQUIVALENCE/NUMBER_LINE YES_NO KCs behave). The "treats any question as statistical"
misconception is therefore modeled in the registry/enum for catalog completeness and hint framing,
but is NOT classified by the verifier; this test pins the actual MAGNITUDE/None behavior.
"""

from __future__ import annotations

from app.domain.knowledge_components import (
    LIVE_KCS,
    KnowledgeComponentId,
    Representation,
    get_kc,
)
from app.domain.lesson_spec import LESSON_SPEC_REGISTRY
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for

_KC = KnowledgeComponentId.STATISTICAL_QUESTIONS


def _problem(seed: int) -> Problem:
    return generate_problem(_KC, seed)


def _is_statistical(problem: Problem) -> bool:
    """The item's truth, read from operands exactly as ``_verify_yes_no`` does (equal → YES)."""
    assert problem.operands is not None and len(problem.operands) == 2
    return bool(problem.operands[0] == problem.operands[1])


def test_statistical_questions_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_generated_item_is_a_clean_in_scope_yes_no_problem() -> None:
    """The generator yields a YES/NO judgment with a two-operand truth carrier and question text."""
    problem = _problem(7)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.YES_NO
    assert problem.operands is not None and len(problem.operands) == 2
    # The statement is a real question (ends with '?') the learner classifies.
    assert problem.statement.strip().endswith("?")
    # The two operands encode the truth (equal ⇒ statistical/YES): they are either equal or not.
    assert problem.operands[0] in (problem.operands[1], problem.operands[1] + 1)


def test_correct_verdict_verifies_correct() -> None:
    """The canonical yes/no (yes iff statistical) is graded correct by the tutor's own oracle."""
    for seed in range(1, 40):
        problem = _problem(seed)
        truth = "yes" if _is_statistical(problem) else "no"
        result = verify(problem, truth)
        assert result.is_correct, f"seed {seed}: {truth} should be correct"
        assert result.error_category is ErrorCategory.NONE


def test_wrong_verdict_is_magnitude_with_no_misconception() -> None:
    """A flipped judgment is wrong → MAGNITUDE, NO operand-classified misconception (YES_NO path).

    Build-brief flag: YES_NO does not use ``_WRONG_ANSWER_MODELS``; ``_verify_yes_no`` returns
    MAGNITUDE with ``matched_misconception=None`` on any wrong judgment (it never over-claims a
    misconception), exactly like the existing EQUIVALENCE / NUMBER_LINE_PLACEMENT YES_NO KCs.
    """
    for seed in range(1, 40):
        problem = _problem(seed)
        flipped = "no" if _is_statistical(problem) else "yes"
        result = verify(problem, flipped)
        assert not result.is_correct, f"seed {seed}: {flipped} should be wrong"
        assert result.error_category is ErrorCategory.MAGNITUDE
        assert result.matched_misconception is None


def test_both_verdicts_are_generated() -> None:
    """Across seeds the bank yields BOTH statistical (YES) and non-statistical (NO) questions."""
    verdicts = {_is_statistical(_problem(s)) for s in range(1, 60)}
    assert verdicts == {True, False}


def test_generation_is_deterministic() -> None:
    """Same seed ⇒ identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).operands == generate_problem(_KC, 42).operands


def test_word_problem_surface_is_the_same_judgment() -> None:
    """The KC advertises SYMBOLIC + WORD_PROBLEM; the WORD_PROBLEM surface is the same yes/no item.

    The question text IS a word problem, so the two advertised reps render the SAME judgment
    (the answer kind and truth do not change with the surface) — the ≥2-rep advertisement that
    satisfies the LessonSpec contract.
    """
    advertised = get_kc(_KC).representations
    assert Representation.SYMBOLIC in advertised
    assert Representation.WORD_PROBLEM in advertised
    word = generate_problem(_KC, 11, Representation.WORD_PROBLEM)
    assert word.answer_kind is AnswerKind.YES_NO
    assert word.statement.strip().endswith("?")


def test_worked_example_names_the_verdict() -> None:
    """The worked example's last step states the canonical verdict (a non-magnitude answer).

    Like KC_classify_number_sets (a set answer), the YES/NO verdict is not a Rational magnitude,
    so the final step carries ``revealed_value=None`` and names the verdict in its ``shown`` text.
    """
    for seed in (3, 4):
        problem = _problem(seed)
        example = worked_example_for(problem)
        verdict_word = "is" if _is_statistical(problem) else "is not"
        assert verdict_word in example.steps[-1].shown.lower()
        assert example.steps[-1].revealed_value is None


def test_nudge_bank_covers_statistical_questions() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text


def test_lesson_spec_advertises_two_reps_and_routes_errors_off_word_problem() -> None:
    """The lesson advertises ≥2 reps and routes every error to a rep WITH a surface state.

    WORD_PROBLEM has no surface state, so error routes must never target it — they stay on the
    live SYMBOLIC surface (practice-only: SYMBOLIC is the only live answer surface).
    """
    spec = LESSON_SPEC_REGISTRY.get(_KC)
    assert len(spec.representations) >= 2
    for route in spec.error_routes:
        assert route.representation is not Representation.WORD_PROBLEM
        assert route.representation is Representation.SYMBOLIC
