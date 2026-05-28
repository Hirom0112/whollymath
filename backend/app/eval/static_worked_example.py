"""The static worked-example baseline arm (Slice 5.2).

The third arm in the §3.11 comparison (Slice 5.3), alongside the chat baseline (Slice
5.1) and our adaptive tutor. PROJECT.md §3.11 defines it as "a pre-rendered linear
walkthrough in the visual style of Varsity Tutors' Homework Help (the ``2x + 5 = 13``
rendering pattern, ported to fractions)." This is the *static* control: every problem
gets the SAME fixed walkthrough treatment, shown in full up front, with **none** of our
adaptive machinery.

What this arm deliberately lacks, and what 5.3 measures it against:

- **No adaptivity.** The same linear walkthrough renders for every problem regardless of
  how the learner is doing — no surface morphing (S1/S2/S3), no escalation to a worked
  example only after struggle. Our tutor reaches a worked example *adaptively* (S4, after
  ≥2 errors); the static arm just shows the solution every time.
- **No Socratic prompts.** Our S4 pairs every revealed step with a "why did this work?"
  question (PROJECT.md §3.5). The static arm strips those — a Homework-Help walkthrough
  states the steps, it does not interrogate them. So the walkthrough here is the worked
  example's step *content* only, never its ``why_prompt``.
- **No SymPy verification and no mastery model.** The arm never decides whether the
  learner's answer is right and never tracks or declares mastery (the §3.4 anti-gaming
  rules are entirely absent). It only presents a solution and records what the learner
  submitted; whether that submission is correct, and whether anything was "mastered", is
  left for the 5.3 comparison harness to compute — not this arm.

The correctness of the walkthrough itself is borrowed, not reinvented: it reuses the
domain's canonical worked-example procedure (``tutor.worked_example.worked_example_for``),
so the static baseline shows *correct* math (we do not strawman it with a broken
walkthrough — that would make the comparison dishonest). The difference 5.3 measures is
the PEDAGOGY (static linear solution vs. our adaptive, mastery-defended, transfer-tested
tutor), not the arithmetic.

Boundaries (CLAUDE.md §7, §8): this arm is fully deterministic — there is **no LLM** here
at all (unlike the chat baseline, whose whole point is the model's prose). It imports
neither the SymPy verifier (``domain.verifier``) nor the mastery model — that absence is
what makes it a control. No DB, no network. The persona's answer is produced by the
already-tested Layer-3 simulator (so the SAME personas drive every arm in 5.3), reused,
not reimplemented.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sympy import Rational

from app.domain.problem_generators import Problem
from app.personas.persona_config import PersonaConfig
from app.personas.simulator import simulate_action
from app.tutor.worked_example import worked_example_for


@dataclass(frozen=True)
class StaticTurn:
    """One problem in a static-baseline session: the problem, the pre-rendered linear
    walkthrough the learner was shown, and the answer the learner submitted.

    ``student_answer`` is the raw submitted magnitude (a SymPy ``Rational``), or ``None``
    when the persona submits nothing (a give-up). It is recorded unverified — whether it
    is correct is the 5.3 comparison harness's job, not this arm's (the arm has no
    verifier, by design)."""

    problem_statement: str
    walkthrough: str
    student_answer: Rational | None


def _render_answer(value: Rational) -> str:
    """Render a ``Rational`` the way the walkthrough's final line states the answer:
    a bare integer when whole (``q == 1``), otherwise ``p/q``."""
    return str(value.p) if value.q == 1 else f"{value.p}/{value.q}"


def render_walkthrough(problem: Problem) -> str:
    """Render the pre-rendered linear walkthrough for one problem (Homework-Help style).

    Reuses the domain's canonical worked-example steps (``worked_example_for``) and lays
    them out as a numbered linear solution that ends on the answer — the static format the
    §3.11 baseline calls for. The steps' Socratic ``why_prompt``s are intentionally dropped
    (a static walkthrough states the procedure; it does not ask the learner to justify it —
    that is our adaptive S4's feature, deliberately absent here).
    """
    example = worked_example_for(problem)
    lines = [f"Problem: {problem.statement}"]
    lines += [f"Step {index}: {step.shown}" for index, step in enumerate(example.steps, start=1)]
    lines.append(f"Answer: {_render_answer(example.final_value)}")
    return "\n".join(lines)


def run_static_session(
    persona: PersonaConfig,
    problems: Sequence[Problem],
) -> list[StaticTurn]:
    """Conduct a static worked-example baseline session and return its transcript.

    For each problem in order, the learner is shown the full pre-rendered linear
    walkthrough and the Layer-3 simulator produces the persona's deterministic answer (the
    same answer that persona gives in any arm). Both are recorded. Nothing is verified,
    nothing is tracked, nothing adapts — that is the point of the static control. Pure and
    deterministic: the same persona and problems yield the same transcript every call.
    """
    return [
        StaticTurn(
            problem_statement=problem.statement,
            walkthrough=render_walkthrough(problem),
            student_answer=simulate_action(persona, problem).submitted_answer,
        )
        for problem in problems
    ]


__all__ = ["StaticTurn", "render_walkthrough", "run_static_session"]
