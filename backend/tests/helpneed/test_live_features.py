"""Tests for the live HelpNeed feature adapter (Slice 4.4 — adapter half).

These pin the contract that the live tutor's completed-turn history produces the
SAME ``HelpNeedFeatures`` shape the model trained on (Slice 3.3/3.5), under the
documented train/serve proxy mapping (the §7.2 cross-tutor gap):

  - ``recent_attempts_mean`` is the constant 1.0 — the live loop is one submit per
    turn, so there is no multi-attempt count to average.
  - ``recent_request_answer_rate`` proxies to the live hint-request rate — the live
    tutor has no "show answer / give up" action, so the closest help-seeking signal
    is the hint request (decision 2026-05-28, approved by the team).
  - ``prior_unproductive_rate`` is computed FAITHFULLY (NOT via the proxy), so the
    locked §3.4 label definition is not distorted: with attempts==1 and hints<2 and
    no give-up action, a live turn is unproductive iff it was not correct.

The parity test is the load-bearing one: an ``EdmCupTurn`` session built to mirror
live turns (attempt_count=1, requested_answer==hinted, hint_count==hinted) must yield
byte-identical features to the live adapter, proving the adapter reproduces the
training-time computation rather than reimplementing it differently.
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId
from app.helpneed.features import FEATURE_NAMES, RECENT_WINDOW, HelpNeedFeatures, _features_at
from app.helpneed.live_features import LiveTurn, live_features
from app.helpneed.parse_edmcup import EdmCupTurn

KC = KnowledgeComponentId.ADDITION_UNLIKE


def _live(correct: bool, *, hinted: bool = False, latency_ms: int = 4000) -> LiveTurn:
    return LiveTurn(correct=correct, hinted=hinted, latency_ms=latency_ms)


def test_empty_history_is_all_neutral() -> None:
    """No completed turns yet ⇒ neutral features (the cold-start row)."""
    feats = live_features([], KC)
    assert feats == HelpNeedFeatures(
        recent_latency_ms_mean=0.0,
        recent_attempts_mean=0.0,
        recent_hint_rate=0.0,
        recent_error_rate=0.0,
        recent_request_answer_rate=0.0,
        turns_since_last_correct=0.0,
        prior_unproductive_rate=0.0,
        session_position=0.0,
        kc=KC,
    )
    # The vector still has the full width the model expects.
    assert len(feats.to_vector()) == len(FEATURE_NAMES)


def test_attempts_mean_is_constant_one_when_history_present() -> None:
    """One submit per turn ⇒ the attempts column is a constant 1.0 (documented proxy)."""
    feats = live_features([_live(True), _live(False)], KC)
    assert feats.recent_attempts_mean == 1.0


def test_request_answer_rate_proxies_the_hint_rate() -> None:
    """No give-up action live ⇒ request_answer_rate mirrors the hint-request rate."""
    history = [_live(True, hinted=True), _live(False, hinted=False), _live(False, hinted=True)]
    feats = live_features(history, KC)
    assert feats.recent_hint_rate == 2 / 3
    assert feats.recent_request_answer_rate == feats.recent_hint_rate


def test_hand_computed_feature_values() -> None:
    """Each numeric feature equals its hand-computed value over the history."""
    history = [
        _live(True, hinted=False, latency_ms=2000),
        _live(False, hinted=True, latency_ms=6000),
        _live(False, hinted=False, latency_ms=10000),
    ]
    feats = live_features(history, KC)
    assert feats.recent_latency_ms_mean == (2000 + 6000 + 10000) / 3
    assert feats.recent_hint_rate == 1 / 3
    assert feats.recent_error_rate == 2 / 3  # two of three wrong
    # last correct was turn 0 (offset 3 back from the in-progress current problem)
    assert feats.turns_since_last_correct == 3.0
    assert feats.prior_unproductive_rate == 2 / 3  # unproductive == not correct, live
    assert feats.session_position == 3.0
    assert feats.kc is KC


def test_turns_since_last_correct_counts_back_to_recent_correct() -> None:
    """A correct immediately-preceding turn ⇒ distance 1."""
    history = [_live(False), _live(False), _live(True)]
    feats = live_features(history, KC)
    assert feats.turns_since_last_correct == 1.0


def test_recent_window_bounds_recent_features_but_not_unproductive_rate() -> None:
    """Recent-* use the last RECENT_WINDOW turns; prior_unproductive_rate uses ALL prior."""
    # RECENT_WINDOW correct turns, then one wrong: the window features see only the
    # most recent RECENT_WINDOW, while the unproductive rate averages over everything.
    history = [_live(True) for _ in range(RECENT_WINDOW)] + [_live(False)]
    feats = live_features(history, KC)
    # window = last RECENT_WINDOW turns: the trailing wrong one + (RECENT_WINDOW-1) correct
    assert feats.recent_error_rate == 1 / RECENT_WINDOW
    # prior = all RECENT_WINDOW+1 turns: exactly one wrong
    assert feats.prior_unproductive_rate == 1 / (RECENT_WINDOW + 1)
    assert feats.session_position == float(RECENT_WINDOW + 1)


def test_parity_with_training_features_except_the_one_proxied_column() -> None:
    """The adapter reproduces training-time ``_features_at`` on every FAITHFUL column.

    Build a FAITHFUL EdmCup mirror of the live turns (attempt_count=1, no give-up,
    hint_count==hinted, first_attempt_correct==correct), plus a dummy CURRENT turn so
    ``_features_at`` computes the row for an in-progress problem at
    ``index == len(history)``. Every column must match the live adapter EXCEPT
    ``recent_request_answer_rate`` — the one intentionally-proxied column, which the
    faithful mirror leaves at 0 while the live adapter sets it to the hint rate. This
    proves (a) the adapter is the same computation as training, not a drifting
    parallel one, and (b) the proxy is confined to exactly one column (the locked
    §3.4 unproductive label is NOT distorted by it). Hinted turns are included so the
    proxied column genuinely differs.
    """
    live_history = [
        _live(True, hinted=True, latency_ms=3000),  # correct AND hinted — the tricky case
        _live(False, hinted=True, latency_ms=7000),
        _live(False, hinted=False, latency_ms=12000),
        _live(True, hinted=False, latency_ms=2500),
    ]

    def _mirror(t: LiveTurn, idx: int) -> EdmCupTurn:
        return EdmCupTurn(
            assignment_log_id="sess",
            problem_id=f"p{idx}",
            ccss_code="5.NF.A.1",
            kc=KC,
            correct=t.correct,
            first_attempt_correct=t.correct,
            attempt_count=1,
            hint_count=1 if t.hinted else 0,
            requested_answer=False,  # faithful: the live tutor has no give-up action
            latency_ms_to_first_response=t.latency_ms,
            total_latency_ms=t.latency_ms if t.correct else None,
        )

    mirrored = [_mirror(t, i) for i, t in enumerate(live_history)]
    # a dummy in-progress current turn so _features_at builds the row from the prior
    current = _mirror(_live(False), len(live_history))
    training_row = _features_at([*mirrored, current], index=len(live_history))
    live_row = live_features(live_history, KC)

    # Every faithful column matches the training-time computation exactly...
    proxied = "recent_request_answer_rate"
    faithful = {f: v for f, v in vars(training_row).items() if f != proxied}
    assert {f: v for f, v in vars(live_row).items() if f != proxied} == faithful
    # ...including the correct-AND-hinted turn NOT being counted unproductive (it stays
    # productive under §3.4: one hint is fine), so the rates agree.
    assert live_row.prior_unproductive_rate == training_row.prior_unproductive_rate
    # ...and only the proxied column differs: live = hint rate, faithful mirror = 0.
    assert training_row.recent_request_answer_rate == 0.0
    assert live_row.recent_request_answer_rate == live_row.recent_hint_rate
    assert live_row.recent_request_answer_rate > 0.0
