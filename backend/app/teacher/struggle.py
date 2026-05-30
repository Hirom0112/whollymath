"""Struggle + WHY: the templated, plain-language diagnostic a teacher reads (Slice TCH.B4).

Pure and NO LLM (CLAUDE.md §8.2 — the LLM never decides a diagnosis): the "why" is assembled from
real signals — the student's weakest KC, the misconception the bank maps to that KC, the recent
error rate, and the behavioral need-help trend — into a fixed template. The match is deliberately
explainable: we name the misconception the registry associates with the KC the student is weakest
on, rather than guessing from free text.

Data honesty: ``Turn`` carries no per-KC tag and HelpNeed scores are not persisted, so the trend
is APPROXIMATED from the need-help signal (a turn "needed help" if it was wrong or used a hint),
comparing the earlier vs. later half of the recent window. This is stated, not hidden — it is a
behavioral proxy for the predictor's trend, computed from the same stream the predictor scores.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.api.schemas import HelpNeedTrend, KcMasteryView, StruggleSummaryView
from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.misconceptions import MISCONCEPTION_REGISTRY
from app.teacher.evidence import TurnFact

# Trailing answers that count as "recent" for the error rate and the trend proxy.
_RECENT_N = 8
# Need at least this many recent answers before reporting a trend (else it is noise → None).
_TREND_MIN = 4
# Earlier vs. later half need-help rates must differ by at least this to read as rising/falling.
_TREND_EPSILON = 0.15


def _needs_help(turn: TurnFact) -> bool:
    """A turn 'needed help' if it was wrong or leaned on a hint — the behavioral proxy stream."""
    return (not turn.correct) or turn.hint_used


def recent_error_rate(turns: Sequence[TurnFact]) -> float | None:
    """Fraction of the recent window answered incorrectly, or ``None`` with no recent answers."""
    recent = turns[-_RECENT_N:]
    if not recent:
        return None
    return sum(1 for t in recent if not t.correct) / len(recent)


def helpneed_trend(turns: Sequence[TurnFact]) -> HelpNeedTrend | None:
    """Approximate the behavioral HelpNeed direction over the recent window (proxy; see module).

    Compares the need-help rate of the earlier half vs. the later half of the recent answers:
    rising when the later half needs more help, falling when it needs less, steady in between.
    ``None`` when there are too few recent answers to judge.
    """
    recent = turns[-_RECENT_N:]
    if len(recent) < _TREND_MIN:
        return None
    half = len(recent) // 2
    earlier = sum(_needs_help(t) for t in recent[:half]) / half
    later = sum(_needs_help(t) for t in recent[half:]) / (len(recent) - half)
    if later - earlier >= _TREND_EPSILON:
        return HelpNeedTrend.RISING
    if earlier - later >= _TREND_EPSILON:
        return HelpNeedTrend.FALLING
    return HelpNeedTrend.STEADY


def _misconception_for_kc(kc_id: str) -> str | None:
    """The named misconception the bank maps to a KC, or ``None`` if none applies.

    Iterates the registry (it has no KC index) and returns the first misconception whose
    ``applicable_kcs`` includes this KC — the explainable "this KC tends to fail via X" link.
    """
    try:
        kc = KnowledgeComponentId(kc_id)
    except ValueError:
        return None
    for misconception in MISCONCEPTION_REGISTRY.all():
        if kc in misconception.applicable_kcs:
            return misconception.name
    return None


def build_struggle_summary(
    turns: Sequence[TurnFact],
    weaknesses: Sequence[KcMasteryView],
) -> StruggleSummaryView:
    """Assemble the "what + WHY struggling" summary from the weakest KC + behavioral signals.

    ``weaknesses`` is the weakest-first list from the overview projection. When there is a clear
    weakest KC we name its associated misconception and lead with it; otherwise we report a benign
    on-track summary (the field is always present on the student view). Always templated, no LLM.
    """
    error_rate = recent_error_rate(turns)
    trend = helpneed_trend(turns)

    if not weaknesses:
        return StruggleSummaryView(
            headline="No specific struggle right now.",
            detail="Recent work looks on track — keep monitoring as new skills unlock.",
            matched_misconception=None,
            helpneed_trend=trend,
            recent_error_rate=error_rate,
        )

    weakest = weaknesses[0]
    misconception = _misconception_for_kc(weakest.kc_id)
    rate_phrase = (
        f"Recent accuracy on this work is {round((1 - error_rate) * 100)}%."
        if error_rate is not None
        else "There isn't much recent work to read yet."
    )

    if misconception is not None:
        headline = f"{misconception} is showing up in {weakest.skill_name}."
        detail = (
            f"{weakest.skill_name} is the weakest skill (p(known) "
            f"{round(weakest.probability * 100)}%), and the error pattern matches "
            f"{misconception.lower()}. {rate_phrase}"
        )
    else:
        headline = f"Struggling with {weakest.skill_name}."
        detail = (
            f"{weakest.skill_name} is the weakest skill (p(known) "
            f"{round(weakest.probability * 100)}%). {rate_phrase}"
        )

    return StruggleSummaryView(
        headline=headline,
        detail=detail,
        matched_misconception=misconception,
        helpneed_trend=trend,
        recent_error_rate=error_rate,
    )


__all__ = [
    "build_struggle_summary",
    "helpneed_trend",
    "recent_error_rate",
]
