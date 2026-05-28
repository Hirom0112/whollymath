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
    load_recorded_chat_run,
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


def _chat_outcome(row: ComparisonRow, recorded_run: dict[str, object] | None) -> ArmOutcome:
    """The chat arm's outcome for a persona: the recorded LIVE result if we have one, else the
    pre-registered prediction (``row.chat``)."""
    if recorded_run is None:
        return row.chat
    results = recorded_run.get("results", {})
    assert isinstance(results, dict)
    rec = results.get(row.persona_id)
    if rec is None:
        return row.chat
    return ArmOutcome(
        arm="chat",
        claimed_mastery=bool(rec["claimed_mastery"]),
        note=f"live self-assessment: {rec['self_assessment']!r}",
    )


def _row_view(row: ComparisonRow, chat: ArmOutcome) -> PersonaComparisonView:
    return PersonaComparisonView(
        persona_name=row.persona_name,
        attacks=row.attacked_dimension,
        problems=_problems_for_persona(row.persona_id),
        adaptive=_verdict_view(row.adaptive),
        chat=_verdict_view(chat),
        static=_verdict_view(row.static),
    )


def build_three_arm_comparison_view() -> ThreeArmComparisonView:
    """Assemble the on-screen three-arm comparison. Adaptive + static are computed live and
    deterministically (free, no LLM). The chat column uses the recorded LIVE run if one is
    committed (``artifacts/chat_baseline_run.json``), otherwise the §9 prediction. Either way
    this is free to call — it never makes an LLM call."""
    rows = run_comparison_offline()
    recorded_run = load_recorded_chat_run()
    chat_outcomes = [_chat_outcome(r, recorded_run) for r in rows]

    adaptive_fp = sum(bool(r.adaptive.claimed_mastery) for r in rows)
    chat_live = recorded_run is not None
    chat_fp = sum(bool(c.claimed_mastery) for c in chat_outcomes) if chat_live else None

    if chat_live:
        headline = (
            f"Five adversarial learners, the same problems, three tutors. Our adaptive tutor "
            f"denied false mastery to all five ({adaptive_fp}/{len(rows)}); the chat tutor "
            f"over-claimed mastery for {chat_fp}/{len(rows)} — fooled by the learners who give "
            f"right answers without real understanding; the static walkthrough certifies nothing."
        )
    else:
        headline = (
            "Five adversarial learners, the same problems, three tutors. Our adaptive tutor "
            "denies false mastery to all five; a chat tutor is predicted to certify learners "
            "who haven't mastered the skill; a static walkthrough certifies nothing."
        )

    return ThreeArmComparisonView(
        rows=[_row_view(r, c) for r, c in zip(rows, chat_outcomes, strict=True)],
        total=len(rows),
        adaptive_false_positives=adaptive_fp,
        chat_false_positives=chat_fp,
        chat_live=chat_live,
        headline=headline,
    )


__all__ = ["build_three_arm_comparison_view"]
