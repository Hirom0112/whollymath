"""Unit tests for the deterministic dashboard trend/sparkline series (dashboard upgrade).

These pin the CONTRACT the frontend mirrors (exact lengths, value ranges) and — critically — the
DETERMINISM the harness requires (CLAUDE.md §9): the synthetic series are a pure function of their
inputs, so the SAME input always yields the SAME list, with no randomness. Each series also ends ON
the current value it is drawn next to, which is the property the dashboard relies on.
"""

from __future__ import annotations

from app.teacher.trends import (
    accuracy_history,
    accuracy_sparkline,
    bucket_trend,
    remediation_estimate_minutes,
    skill_gap_series,
)


def test_accuracy_sparkline_length_and_range() -> None:
    series = accuracy_sparkline(0.4)
    assert len(series) == 10
    assert all(0 <= v <= 100 for v in series)


def test_accuracy_sparkline_ends_on_current_accuracy() -> None:
    # error_rate 0.25 → current accuracy 75% → the last point is exactly 75.
    assert accuracy_sparkline(0.25)[-1] == 75


def test_accuracy_sparkline_is_deterministic() -> None:
    assert accuracy_sparkline(0.6) == accuracy_sparkline(0.6)


def test_accuracy_sparkline_flat_neutral_without_recent_answers() -> None:
    assert accuracy_sparkline(None) == [50] * 10


def test_accuracy_history_matches_sparkline_length() -> None:
    assert accuracy_history(0.3) == accuracy_sparkline(0.3)
    assert len(accuracy_history(0.3)) == 10


def test_bucket_trend_length_and_endpoint() -> None:
    series = bucket_trend(5)
    assert len(series) == 12
    assert series[-1] == 5  # ramps up TO the current count


def test_bucket_trend_empty_bucket_is_all_zero() -> None:
    assert bucket_trend(0) == [0] * 12


def test_bucket_trend_is_deterministic() -> None:
    assert bucket_trend(7) == bucket_trend(7)


def test_skill_gap_series_length_range_and_endpoint() -> None:
    series = skill_gap_series(30.0)
    assert len(series) == 14
    assert all(0 <= v <= 100 for v in series)
    assert series[-1] == 30


def test_skill_gap_series_clamps_and_is_deterministic() -> None:
    assert skill_gap_series(120.0)[-1] == 100  # clamped to 100
    assert skill_gap_series(45.0) == skill_gap_series(45.0)


def test_remediation_estimate_none_when_no_lessons() -> None:
    assert remediation_estimate_minutes(0) is None


def test_remediation_estimate_scales_with_lesson_count() -> None:
    # 3 lessons × 12 min/lesson = 36.
    assert remediation_estimate_minutes(3) == 36
