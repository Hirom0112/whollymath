"""Unit tests for the struggle + WHY summary (Slice TCH.B4).

Pins the matched-misconception link (weakest KC → named misconception), the recent-error-rate and
the behavioral trend proxy, and the benign on-track fallback.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.api.schemas import HelpNeedTrend, KcMasteryView, KcStatus
from app.domain.knowledge_components import KnowledgeComponentId, get_kc
from app.teacher.evidence import TurnFact
from app.teacher.struggle import build_struggle_summary, helpneed_trend, recent_error_rate

_NOW = datetime(2026, 5, 30, 12, 0, tzinfo=UTC)
_EQ = KnowledgeComponentId.EQUIVALENCE


def _t(correct: bool, *, hint: bool = False) -> TurnFact:
    return TurnFact(
        correct=correct,
        error_category=None if correct else "magnitude",
        hint_used=hint,
        created_at=_NOW,
    )


def _weak(kc: KnowledgeComponentId, prob: float) -> KcMasteryView:
    return KcMasteryView(
        kc_id=kc.value,
        skill_name=get_kc(kc).skill_name,
        probability=prob,
        status=KcStatus.IN_PROGRESS,
    )


def test_recent_error_rate_none_without_turns() -> None:
    assert recent_error_rate([]) is None


def test_recent_error_rate_counts_incorrect() -> None:
    assert recent_error_rate([_t(True), _t(False), _t(False), _t(True)]) == 0.5


def test_helpneed_trend_rising_when_later_needs_more_help() -> None:
    turns = [_t(True), _t(True), _t(False), _t(False, hint=True)]
    assert helpneed_trend(turns) is HelpNeedTrend.RISING


def test_helpneed_trend_none_with_too_few_turns() -> None:
    assert helpneed_trend([_t(True), _t(False)]) is None


def test_struggle_names_misconception_for_weakest_kc() -> None:
    """Equivalence is a KC the misconception bank maps (natural-number bias); it must be named."""
    summary = build_struggle_summary([_t(False), _t(False), _t(True)], [_weak(_EQ, 0.22)])
    assert summary.matched_misconception is not None
    assert summary.matched_misconception in summary.headline
    assert get_kc(_EQ).skill_name in summary.headline
    assert summary.recent_error_rate is not None


def test_struggle_benign_when_no_weaknesses() -> None:
    summary = build_struggle_summary([_t(True), _t(True)], [])
    assert summary.matched_misconception is None
    assert "on track" in summary.detail.lower()
