"""View assembly for the three-arm comparison dashboard (Slice 5.3, on-screen).

Maps the raw eval outcomes (``app.eval.three_arm_comparison``) to the display schemas the
surface renders. This is the api presentation seam: it carries no eval logic of its own — it
calls the offline comparison (real adaptive + static, predicted chat, no LLM cost) and turns
each arm's outcome into a label + tone the frontend shows verbatim (CLAUDE.md §7; the surface
stays presentation-only). No SymPy, no LLM, no DB here.
"""

from __future__ import annotations

from app.api.schemas import (
    ArmVerdictView,
    PersonaComparisonView,
    ThreeArmComparisonView,
)
from app.domain.problem_generators import generate_problem
from app.eval.false_positive_harness import harness_cases
from app.eval.three_arm_comparison import (
    ArmOutcome,
    ComparisonRow,
    run_comparison_offline,
)

_ARM_LABEL = {"adaptive": "Adaptive (ours)", "chat": "Chat baseline", "static": "Static baseline"}


def _verdict_view(outcome: ArmOutcome) -> ArmVerdictView:
    """Render one arm's outcome as a display label + tone.

    - Adaptive/Chat with a real result: ``denied`` (good) vs. ``false positive`` (bad).
    - Chat before the live run: ``predicted`` (pending).
    - Static: ``N/A`` (neutral) — it has no mastery construct.
    """
    label = _ARM_LABEL.get(outcome.arm, outcome.arm)
    if outcome.claimed_mastery is None:
        if outcome.arm == "chat":
            verdict, tone = "Predicted: over-claims", "pending"
        else:
            verdict, tone = "N/A — certifies nothing", "neutral"
    elif outcome.claimed_mastery:
        verdict, tone = "Mastered ✗ (false positive)", "bad"
    else:
        verdict, tone = "Denied ✓", "good"
    return ArmVerdictView(arm=label, verdict=verdict, tone=tone, detail=outcome.note)


def _problems_for_persona(persona_id: str) -> list[str]:
    """The problem statements a persona was shown (the same set fed every arm)."""
    case = next(c for c in harness_cases() if c.persona.persona_id == persona_id)
    return [generate_problem(s.kc, s.seed, s.surface_format).statement for s in case.sequence]


def _row_view(row: ComparisonRow) -> PersonaComparisonView:
    return PersonaComparisonView(
        persona_name=row.persona_name,
        attacks=row.attacked_dimension,
        problems=_problems_for_persona(row.persona_id),
        adaptive=_verdict_view(row.adaptive),
        chat=_verdict_view(row.chat),
        static=_verdict_view(row.static),
    )


def build_three_arm_comparison_view() -> ThreeArmComparisonView:
    """Assemble the on-screen three-arm comparison (offline: real adaptive + static, predicted
    chat). Free to call — no LLM, deterministic."""
    rows = run_comparison_offline()
    adaptive_fp = sum(bool(r.adaptive.claimed_mastery) for r in rows)
    return ThreeArmComparisonView(
        rows=[_row_view(r) for r in rows],
        total=len(rows),
        adaptive_false_positives=adaptive_fp,
        chat_live=False,
        headline=(
            "Five adversarial learners, the same problems, three tutors. Our adaptive tutor "
            "denies false mastery to all five; a chat tutor is predicted to certify learners "
            "who haven't mastered the skill; a static walkthrough certifies nothing."
        ),
    )


__all__ = ["build_three_arm_comparison_view"]
