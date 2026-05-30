"""Tests for the sustained-signal proactive-intervention gate (Slice 4.5.1).

The gate is the decision rule that turns the per-turn HelpNeed probability stream into
a fire / don't-fire verdict for a proactive intervention. PROJECT.md §3.7 (sustained
gate, added 2026-05-28): the intervention fires only after **K consecutive turns at
P ≥ threshold**, resetting on any dip — never on a single high reading. This guards the
§7.5 finding-2 failure mode (a correct answer right after an error streak can still read
high, because `turns_since_last_correct` dominates) and the Razzaq & Heffernan (2010)
over-firing risk. K and threshold are provisional here and swept by the Slice 5.4 A/B.

Pure decision logic, deterministic (PROJECT.md §4.1): same probability history ⇒ same
verdict. No SymPy/LLM/DB (CLAUDE.md §8.1/§8.2). These tests are written first (§2).
"""

from __future__ import annotations

import pytest
from app.policy.intervention_gate import SustainedHelpNeedGate


def test_defaults_are_the_documented_provisional_values() -> None:
    """Provisional defaults: K=3 consecutive turns, threshold=0.5 (locked §3.7)."""
    gate = SustainedHelpNeedGate()
    assert gate.k == 3
    assert gate.threshold == 0.5


def test_fires_when_last_k_turns_all_clear_threshold() -> None:
    """K consecutive readings at or above threshold trip the gate."""
    gate = SustainedHelpNeedGate(k=3, threshold=0.5)
    assert gate.should_intervene([0.91, 0.88, 0.93]) is True


def test_does_not_fire_on_a_single_high_turn() -> None:
    """One high reading is never enough — the whole point of the sustained gate."""
    gate = SustainedHelpNeedGate(k=3, threshold=0.5)
    assert gate.should_intervene([0.99]) is False


def test_does_not_fire_before_k_turns_exist() -> None:
    """Fewer than K scored turns cannot yet form a sustained signal."""
    gate = SustainedHelpNeedGate(k=3, threshold=0.5)
    assert gate.should_intervene([0.9, 0.9]) is False


def test_a_dip_within_the_last_k_resets_the_signal() -> None:
    """A single sub-threshold turn inside the window blocks the fire (reset semantics).

    finding 2: a correct answer mid-recovery should suppress the intervention, even if
    surrounding turns read high. Here the last 3 = [0.4, 0.9, 0.9] — the 0.4 dip blocks.
    """
    gate = SustainedHelpNeedGate(k=3, threshold=0.5)
    assert gate.should_intervene([0.9, 0.4, 0.9, 0.9]) is False


def test_only_the_most_recent_k_matter() -> None:
    """An older sustained run that has since dipped must not fire now.

    The gate asks 'is the signal sustained right NOW', so it looks only at the most
    recent K turns — a high run followed by a dip is resolved, not a standing alarm.
    """
    gate = SustainedHelpNeedGate(k=3, threshold=0.5)
    assert gate.should_intervene([0.9, 0.9, 0.9, 0.4]) is False  # last 3 = [0.9,0.9,0.4]


def test_threshold_boundary_is_inclusive() -> None:
    """A reading exactly at threshold counts as clearing it (>=, not >)."""
    gate = SustainedHelpNeedGate(k=2, threshold=0.5)
    assert gate.should_intervene([0.5, 0.5]) is True


def test_construction_rejects_bad_parameters() -> None:
    """K < 1 or a threshold outside [0, 1] is a programming error — fail loud (§8.5)."""
    with pytest.raises(ValueError):
        SustainedHelpNeedGate(k=0)
    with pytest.raises(ValueError):
        SustainedHelpNeedGate(threshold=1.5)
    with pytest.raises(ValueError):
        SustainedHelpNeedGate(threshold=-0.1)


# ── Tier-2 trustworthy-KC guard (T1_T2_COORDINATION §"Tier-2") ───────────────────────
#
# The proactive arm may only fire on a KC whose validated per-KC AUC clears the bar
# (``helpneed.per_kc_validation.trustworthy_kcs``). On a weak/guarded KC the sustained
# window can still be high, but the gate must STAY SILENT so the deterministic reactive
# layer (SymPy verdict → morph + misconception) handles the turn — the model isn't
# trustworthy enough there to drive a proactive nudge. The window check is unchanged; this
# is an ADDITIVE filter, off by default (``trustworthy_kcs=None`` ⇒ no filter), so the
# observe-only default and the existing window semantics above are untouched.


def test_default_trustworthy_set_is_none_no_kc_filter() -> None:
    """No trustworthy set configured ⇒ the KC-aware check is exactly the window check.

    This is what keeps the default behavior unchanged: a gate with no set behaves on the
    KC-aware path identically to ``should_intervene`` (the A/B sweep + existing tests).
    """
    gate = SustainedHelpNeedGate(k=3, threshold=0.5)
    assert gate.trustworthy_kcs is None
    assert gate.should_intervene_for_kc([0.91, 0.88, 0.93], kc="KC_anything") is True
    assert gate.should_intervene_for_kc([0.99], kc="KC_anything") is False


def test_trustworthy_kc_can_fire_when_window_trips() -> None:
    """A KC in the trustworthy set fires exactly when the sustained window trips."""
    gate = SustainedHelpNeedGate(
        k=3, threshold=0.5, trustworthy_kcs=frozenset({"KC_multiply_fractions"})
    )
    assert gate.should_intervene_for_kc([0.91, 0.88, 0.93], kc="KC_multiply_fractions") is True


def test_guarded_kc_never_fires_even_with_sustained_signal() -> None:
    """A weak/guarded KC stays silent (reactive fallback) even on a clear sustained signal.

    ``KC_rate_problems`` is one of the genuinely weak topics (AUC ~0.74) the Tier-2 guard
    excludes; the window trips but the proactive arm must not fire on it.
    """
    gate = SustainedHelpNeedGate(
        k=3, threshold=0.5, trustworthy_kcs=frozenset({"KC_multiply_fractions"})
    )
    # The window itself is satisfied — only the KC guard suppresses the fire.
    assert gate.should_intervene([0.91, 0.88, 0.93]) is True
    assert gate.should_intervene_for_kc([0.91, 0.88, 0.93], kc="KC_rate_problems") is False


def test_kc_filter_does_not_override_the_window() -> None:
    """A trustworthy KC still requires the sustained window — the filter only ANDs in.

    A single high turn on a trustworthy KC must not fire: the trustworthiness gate widens
    *where* the arm may fire, never *when* (the §3.7 sustained rule still governs).
    """
    gate = SustainedHelpNeedGate(
        k=3, threshold=0.5, trustworthy_kcs=frozenset({"KC_multiply_fractions"})
    )
    assert gate.should_intervene_for_kc([0.99], kc="KC_multiply_fractions") is False


def test_empty_trustworthy_set_suppresses_every_kc() -> None:
    """An empty (but not None) set means 'nothing validated yet' — fire on nothing.

    Distinct from ``None`` (no filter). An explicit empty frozenset is a real, if extreme,
    Tier-2 verdict (no KC cleared the AUC bar), and the gate must honor it rather than
    treating it as 'allow all'.
    """
    gate = SustainedHelpNeedGate(k=3, threshold=0.5, trustworthy_kcs=frozenset())
    assert gate.should_intervene_for_kc([0.91, 0.88, 0.93], kc="KC_multiply_fractions") is False
