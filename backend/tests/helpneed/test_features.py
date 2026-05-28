"""Tests for HelpNeed feature extraction (Slice 3.3).

Features are built from a session's PRIOR turns (the recent window) — never the
current turn's own outcome — so the label (derived from the current turn) cannot
leak into the features. These tests hand-compute the windowed statistics on a
crafted session and assert the builder reproduces them (TDD — mandatory for the
HelpNeed pipeline, CLAUDE.md §2).
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId
from app.helpneed.features import (
    FEATURE_NAMES,
    RECENT_WINDOW,
    build_examples,
    session_examples,
)
from app.helpneed.parse_edmcup import EdmCupTurn

_KC = KnowledgeComponentId.ADDITION_UNLIKE


def _turn(
    *,
    correct: bool,
    first_attempt_correct: bool,
    attempt_count: int,
    hint_count: int,
    requested_answer: bool,
    latency: int | None,
    assignment: str = "s1",
) -> EdmCupTurn:
    return EdmCupTurn(
        assignment_log_id=assignment,
        problem_id="p",
        ccss_code="5.NF.A.1",
        kc=_KC,
        correct=correct,
        first_attempt_correct=first_attempt_correct,
        attempt_count=attempt_count,
        hint_count=hint_count,
        requested_answer=requested_answer,
        latency_ms_to_first_response=latency,
        total_latency_ms=latency if correct else None,
    )


def _session() -> list[EdmCupTurn]:
    """Six turns with known stats (see the per-index hand computations below)."""
    return [
        _turn(
            correct=True,
            first_attempt_correct=True,
            attempt_count=1,
            hint_count=0,
            requested_answer=False,
            latency=1000,
        ),  # t0 productive
        _turn(
            correct=True,
            first_attempt_correct=False,
            attempt_count=2,
            hint_count=0,
            requested_answer=False,
            latency=2000,
        ),  # t1 productive (1 wrong)
        _turn(
            correct=False,
            first_attempt_correct=False,
            attempt_count=2,
            hint_count=0,
            requested_answer=False,
            latency=3000,
        ),  # t2 unproductive (never solved)
        _turn(
            correct=True,
            first_attempt_correct=False,
            attempt_count=1,
            hint_count=0,
            requested_answer=True,
            latency=4000,
        ),  # t3 unproductive (gave up)
        _turn(
            correct=True,
            first_attempt_correct=False,
            attempt_count=1,
            hint_count=3,
            requested_answer=False,
            latency=5000,
        ),  # t4 unproductive (hints)
        _turn(
            correct=True,
            first_attempt_correct=True,
            attempt_count=1,
            hint_count=0,
            requested_answer=False,
            latency=6000,
        ),  # t5 productive
    ]


def test_feature_names_match_vector_length() -> None:
    """FEATURE_NAMES must line up with to_vector() so SHAP labels the right column."""
    examples = session_examples(_session())
    assert len(examples[0].features.to_vector()) == len(FEATURE_NAMES)


def test_labels_follow_the_unproductive_rule() -> None:
    """The per-turn labels match the 3.4 definition on the crafted session."""
    labels = [ex.label for ex in session_examples(_session())]
    assert labels == [False, False, True, True, True, False]


def test_window_statistics_at_last_turn() -> None:
    """Hand-computed recent-window features for t5 (window = t0..t4, RECENT_WINDOW=5)."""
    assert RECENT_WINDOW == 5
    feats = session_examples(_session())[5].features
    assert feats.recent_latency_ms_mean == 3000.0  # mean(1000..5000)
    assert feats.recent_attempts_mean == 1.4  # mean(1,2,2,1,1)
    assert feats.recent_hint_rate == 0.6  # mean(0,0,0,0,3)
    assert feats.recent_error_rate == 0.8  # 4/5 not first_attempt_correct
    assert feats.recent_request_answer_rate == 0.2  # 1/5 requested
    assert feats.turns_since_last_correct == 1.0  # t4 was correct
    assert feats.prior_unproductive_rate == 0.6  # 3/5 prior turns unproductive
    assert feats.session_position == 5.0
    assert feats.kc is _KC


def test_first_turn_has_neutral_history() -> None:
    """Turn 0 has no prior turns — every history feature is zero/neutral."""
    feats = session_examples(_session())[0].features
    assert feats.recent_latency_ms_mean == 0.0
    assert feats.recent_attempts_mean == 0.0
    assert feats.recent_hint_rate == 0.0
    assert feats.recent_error_rate == 0.0
    assert feats.recent_request_answer_rate == 0.0
    assert feats.turns_since_last_correct == 0.0
    assert feats.prior_unproductive_rate == 0.0
    assert feats.session_position == 0.0


def test_features_use_only_prior_turns_no_leakage() -> None:
    """A turn's own outcome must not change its features (leakage guard).

    Flip the LAST turn's outcome wildly; the features for that turn (built from the
    unchanged prior turns) must be identical.
    """
    base = _session()
    feats_a = session_examples(base)[5].features

    flipped = base[:5] + [
        _turn(
            correct=False,
            first_attempt_correct=False,
            attempt_count=9,
            hint_count=9,
            requested_answer=True,
            latency=99999,
        )
    ]
    feats_b = session_examples(flipped)[5].features
    assert feats_a.to_vector() == feats_b.to_vector()


def test_build_examples_groups_by_session() -> None:
    """build_examples splits turns into per-assignment sessions before windowing."""
    s1 = _session()
    s2 = [
        _turn(
            correct=True,
            first_attempt_correct=True,
            attempt_count=1,
            hint_count=0,
            requested_answer=False,
            latency=500,
            assignment="s2",
        )
    ]
    examples = build_examples(s1 + s2)
    assert len(examples) == len(s1) + len(s2)
    # The s2 turn is the first of its OWN session → neutral history, not influenced by s1.
    s2_example = examples[-1]
    assert s2_example.features.session_position == 0.0
    assert s2_example.features.prior_unproductive_rate == 0.0
