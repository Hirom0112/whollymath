"""The S4 worked-example backend tests (Slice 3.6).

These cover ``worked_example_for`` — the function that, given the ``Problem`` a
learner got stuck on (≥2 consecutive errors, PROJECT.md §3.6 row 133 → S4), builds
the S4 surface content: a solved problem revealed step-by-step, each step carrying
a one-line "why did this work?" prompt (PROJECT.md §3.5 S4 row; ARCHITECTURE.md §7).

What is asserted (the load-bearing properties):

  - **Step ordering is the canonical procedure order** for each KC (ARCHITECTURE.md
    §4 "each KC carries its canonical correct procedure"): common denominator →
    rewrite → combine → simplify for the arithmetic KCs.
  - **Self-consistency**: the final step's revealed value equals ``problem.correct_value``
    for many generated problems — checked WITHOUT calling the SymPy verifier (that
    correctness authority stays in ``domain/``; CLAUDE.md §8.2, ARCHITECTURE.md §14
    invariant 2). The worked example must agree with the problem it explains.
  - **Determinism** (PROJECT.md §4.1): the same ``Problem`` yields an identical
    ``WorkedExample`` every call, tested by equality.
  - **Every step has a non-empty "why?" prompt** (the §3.5 S4 requirement that each
    revealed step is "accompanied by a 'why did this work?' question").
  - **Each supported KC produces a sensible step count.**
  - **NUMBER_LINE_PLACEMENT** produces a single "locate by magnitude" step (the
    chosen coverage — there is no multi-step arithmetic procedure to reveal).

No LLM, no DB, no network, no ``verify()`` (CLAUDE.md §8.1/§8.2). The "why?" prompts
are plain conceptual copy carrying no claim that needs a source.
"""

from __future__ import annotations

import pytest
from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.domain.problem_generators import Problem, generate_problem
from app.tutor.worked_example import WorkedExample, WorkedStep, worked_example_for
from sympy import Rational

_KC_EQ = KnowledgeComponentId.EQUIVALENCE
_KC_CD = KnowledgeComponentId.COMMON_DENOMINATOR
_KC_ADD = KnowledgeComponentId.ADDITION_UNLIKE
_KC_SUB = KnowledgeComponentId.SUBTRACTION_UNLIKE
_KC_NL = KnowledgeComponentId.NUMBER_LINE_PLACEMENT

# The KCs that have a clean canonical multi-step (or, for NL, single-step) procedure.
_SUPPORTED_KCS = (_KC_EQ, _KC_CD, _KC_ADD, _KC_SUB, _KC_NL)

# A spread of seeds so the self-consistency / determinism properties are exercised
# across many distinct generated operand pairs, not one lucky problem.
_SEEDS = tuple(range(20))


# ─── Shape ───────────────────────────────────────────────────────────────────


def test_returns_worked_example_with_steps() -> None:
    problem = generate_problem(_KC_ADD, seed=1)
    example = worked_example_for(problem)
    assert isinstance(example, WorkedExample)
    assert len(example.steps) >= 1
    assert all(isinstance(step, WorkedStep) for step in example.steps)


def test_worked_example_carries_the_source_problem() -> None:
    problem = generate_problem(_KC_SUB, seed=2)
    example = worked_example_for(problem)
    # The example is about the problem it was built from (so the surface can show
    # the original statement alongside the steps).
    assert example.problem == problem


# ─── Every step has a non-empty "why?" prompt (§3.5 S4) ──────────────────────


@pytest.mark.parametrize("kc", _SUPPORTED_KCS)
def test_every_step_has_a_nonempty_why_prompt(kc: KnowledgeComponentId) -> None:
    problem = generate_problem(kc, seed=3)
    example = worked_example_for(problem)
    for step in example.steps:
        assert step.shown.strip(), "a worked step must show content"
        assert step.why_prompt.strip(), "every step needs a 'why did this work?' prompt"
        assert step.why_prompt.strip().endswith("?"), "the why-prompt is phrased as a question"


# ─── Self-consistency: final step value == problem.correct_value (no verify) ──


@pytest.mark.parametrize("kc", _SUPPORTED_KCS)
@pytest.mark.parametrize("seed", _SEEDS)
def test_final_step_value_equals_correct_value(kc: KnowledgeComponentId, seed: int) -> None:
    problem = generate_problem(kc, seed=seed)
    example = worked_example_for(problem)
    # The worked example must land on exactly the problem's correct answer. Checked
    # by Rational equality, NOT by calling the SymPy verifier (CLAUDE.md §8.2).
    assert example.final_value == problem.correct_value
    assert example.steps[-1].revealed_value == problem.correct_value


# ─── Determinism (PROJECT.md §4.1) ───────────────────────────────────────────


@pytest.mark.parametrize("kc", _SUPPORTED_KCS)
def test_same_problem_yields_identical_worked_example(kc: KnowledgeComponentId) -> None:
    problem = generate_problem(kc, seed=4)
    first = worked_example_for(problem)
    second = worked_example_for(problem)
    # Frozen dataclasses with tuple steps ⇒ value equality is identity of content.
    assert first == second


# ─── Canonical procedure order + sensible step count, per KC ─────────────────


def test_addition_procedure_order_and_step_count() -> None:
    # 1/3 + 1/4 → common denom 12 → rewrite → add tops → simplify-check.
    problem = generate_problem(_KC_ADD, seed=5)
    example = worked_example_for(problem)
    # Four canonical steps: common denominator, rewrite, combine, simplify/check.
    assert len(example.steps) == 4
    shown = [step.shown.lower() for step in example.steps]
    assert "common denominator" in shown[0]
    assert "rewrite" in shown[1] or "same" in shown[1]
    assert "add" in shown[2]
    assert "simplest" in shown[3] or "simplif" in shown[3]


def test_subtraction_procedure_order_and_step_count() -> None:
    problem = generate_problem(_KC_SUB, seed=6)
    example = worked_example_for(problem)
    assert len(example.steps) == 4
    shown = [step.shown.lower() for step in example.steps]
    assert "common denominator" in shown[0]
    assert "subtract" in shown[2]
    assert "simplest" in shown[3] or "simplif" in shown[3]


def test_common_denominator_step_count() -> None:
    problem = generate_problem(_KC_CD, seed=7)
    example = worked_example_for(problem)
    # CD has a short canonical procedure: name the two piece sizes, then the LCM.
    assert 2 <= len(example.steps) <= 3
    assert example.final_value == problem.correct_value


def test_equivalence_step_count_and_final_value() -> None:
    problem = generate_problem(_KC_EQ, seed=8)
    example = worked_example_for(problem)
    assert 2 <= len(example.steps) <= 3
    # The equivalent form names the same amount as the base fraction (correct_value).
    assert example.final_value == problem.correct_value


def test_number_line_is_single_locate_by_magnitude_step() -> None:
    problem = generate_problem(_KC_NL, seed=9)
    example = worked_example_for(problem)
    # Coverage decision: NUMBER_LINE_PLACEMENT has no multi-step arithmetic; it gets
    # ONE defensible "locate by magnitude" step. S4 is reachable from any state on
    # ≥2 consecutive errors (PROJECT.md §3.6 row 133), so the surface must have
    # honest content rather than raise.
    assert len(example.steps) == 1
    assert example.final_value == problem.correct_value
    assert example.steps[0].why_prompt.strip().endswith("?")


# ─── A KC that genuinely has no procedure here is refused loudly ─────────────


def test_unsupported_problem_raises_loudly() -> None:
    # Fabricate a Problem with a real KC but no operands where the builder needs them:
    # an addition problem missing its operand pair cannot be worked through.
    broken = Problem(
        problem_id="BROKEN-ADD",
        kc=_KC_ADD,
        surface_format=Representation.SYMBOLIC,
        statement="? + ? = ?",
        correct_value=Rational(1, 2),
        representations_available=(Representation.SYMBOLIC,),
        operands=None,
    )
    with pytest.raises(ValueError):
        worked_example_for(broken)
