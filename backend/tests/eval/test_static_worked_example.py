"""Tests for the static worked-example baseline arm (Slice 5.2).

The static arm is deterministic — no LLM, no SymPy verification, no mastery model — so
unlike the chat baseline these tests CAN assert on its full output. We pin three things:
the transcript shape, that the walkthrough is a correct linear solution that drops the
Socratic prompts (the static contrast), and — structurally — that the arm imports none of
the machinery (verifier, mastery, LLM) whose ABSENCE is what makes it the §3.11 control.
"""

from __future__ import annotations

from pathlib import Path

from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.problem_generators import Problem, generate_problem
from app.eval.static_worked_example import StaticTurn, render_walkthrough, run_static_session
from app.personas.registry import get_persona
from app.personas.simulator import simulate_action
from app.tutor.worked_example import worked_example_for

_PERSONA_IDS = (
    "natural_number_nate",
    "procedure_priya",
    "hint_hunter_hugo",
    "surface_sam",
    "click_through_cleo",
)


def _two_problems() -> list[Problem]:
    return [
        generate_problem(KnowledgeComponentId.ADDITION_UNLIKE, seed=1),
        generate_problem(KnowledgeComponentId.ADDITION_UNLIKE, seed=2),
    ]


def test_one_turn_per_problem_in_order() -> None:
    """The transcript has one StaticTurn per problem, statements in the problems' order."""
    problems = _two_problems()
    turns = run_static_session(get_persona("procedure_priya"), problems)
    assert len(turns) == len(problems)
    assert [t.problem_statement for t in turns] == [p.statement for p in problems]
    assert all(isinstance(t, StaticTurn) for t in turns)


def test_walkthrough_is_a_linear_solution_landing_on_the_correct_answer() -> None:
    """The walkthrough is a numbered linear solution that ends on the problem's answer.

    The final ``Answer:`` line states ``problem.correct_value`` — the static walkthrough
    shows correct math (we do not strawman the baseline). Correctness here is a property of
    the reused canonical procedure, asserted via the problem's own ``correct_value``, not by
    re-deriving it through the verifier (which this arm does not import)."""
    problem = generate_problem(KnowledgeComponentId.ADDITION_UNLIKE, seed=7)
    walkthrough = render_walkthrough(problem)

    assert walkthrough.startswith(f"Problem: {problem.statement}")
    assert "Step 1:" in walkthrough
    value = problem.correct_value
    expected_answer = str(value.p) if value.q == 1 else f"{value.p}/{value.q}"
    assert walkthrough.strip().endswith(f"Answer: {expected_answer}")


def test_walkthrough_drops_the_socratic_why_prompts() -> None:
    """The static arm states the steps but strips the "why did this work?" prompts.

    Those Socratic prompts are our adaptive S4's feature (PROJECT.md §3.5); a Homework-Help
    walkthrough does not interrogate the learner. None of the worked example's why_prompts
    appear in the rendered walkthrough — that omission IS the static-vs-adaptive contrast."""
    problem = generate_problem(KnowledgeComponentId.ADDITION_UNLIKE, seed=7)
    walkthrough = render_walkthrough(problem)
    example = worked_example_for(problem)
    for step in example.steps:
        assert step.why_prompt not in walkthrough


def test_walkthrough_reuses_the_canonical_step_content() -> None:
    """Proof the arm reuses the domain procedure rather than reinventing one: every
    canonical step's shown text appears verbatim in the walkthrough."""
    problem = generate_problem(KnowledgeComponentId.SUBTRACTION_UNLIKE, seed=3)
    walkthrough = render_walkthrough(problem)
    for step in worked_example_for(problem).steps:
        assert step.shown in walkthrough


def test_student_answer_is_exactly_the_simulated_persona_action() -> None:
    """The recorded answer is exactly the Layer-3 simulator's submission for every persona
    (the same answer that persona gives in any arm), carried raw — including ``None`` when
    a persona submits nothing. Proof the arm reuses the simulator, not a guess."""
    problem = generate_problem(KnowledgeComponentId.ADDITION_UNLIKE, seed=7)
    for persona_id in _PERSONA_IDS:
        persona = get_persona(persona_id)
        expected = simulate_action(persona, problem).submitted_answer
        turns = run_static_session(persona, [problem])
        assert turns[0].student_answer == expected


def test_run_is_deterministic() -> None:
    """Same persona and problems → identical transcript every call (PROJECT.md §4.1)."""
    persona = get_persona("surface_sam")
    problems = _two_problems()
    assert run_static_session(persona, problems) == run_static_session(persona, problems)


def test_render_answer_renders_whole_values_without_a_denominator() -> None:
    """A whole-number answer (e.g. a common-denominator result) is shown bare, not as p/1."""
    problem = generate_problem(KnowledgeComponentId.COMMON_DENOMINATOR, seed=4)
    walkthrough = render_walkthrough(problem)
    assert problem.correct_value.q == 1  # common-denominator answers are whole numbers
    assert f"Answer: {problem.correct_value.p}" in walkthrough
    assert f"{problem.correct_value.p}/1" not in walkthrough


def test_static_arm_imports_no_verifier_mastery_or_llm() -> None:
    """Structural guard: the static control imports neither the SymPy verifier nor the
    mastery model — that absence is what it contrasts against (RESEARCH.md §3.11). And,
    unlike the chat baseline, it reaches NO LLM at all: it is fully deterministic."""
    source = Path("app/eval/static_worked_example.py").read_text()
    assert "app.domain.verifier" not in source
    assert "app.mastery" not in source
    assert "app.llm" not in source
    assert "anthropic" not in source
