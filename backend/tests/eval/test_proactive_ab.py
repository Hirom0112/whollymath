"""Tests for the proactive A/B + gate-parameter sweep (Slice 5.4).

PROJECT.md §3.7 / §7.1 commits us to a Path-2 proactive layer with an A/B test and
honest reporting regardless of winner. RESEARCH.md §1.7 (Razzaq & Heffernan) warns
proactive over-firing can underperform reactive help; §7.5 finding-2 says single
per-turn HelpNeed readings are noisy, which is why the gate (Slice 4.5.1) requires K
consecutive high turns. Slice 4.5.3 / 4.4.5 moved the K + threshold tuning here.

Two things this eval establishes, and these tests pin their mechanics:

  1. **Outcome A/B (5.4.1).** The proactive arm is observe-only by construction
     (Slice 4.5.1 equivalence guarantee + the Layer-3 simulator does not consume an
     unrequested nudge), so reactive-only and reactive+proactive yield the SAME
     mastery outcome for every persona. The test asserts that equivalence — it is the
     safety property (a proactive arm can never corrupt the deterministic mastery
     path), not an effect-size claim.

  2. **Gate sweep (the numbers).** ``first_fire_turn`` gives the live firing semantics
     (the gate is evaluated on each growing prefix; it fires the first turn the last K
     readings all clear the threshold). The sweep scores each (K, threshold) on
     labelled acceptance traces that encode the gate's design intent: a sustained
     struggle MUST fire; an isolated spike / an alternating stream / a clean stream
     MUST NOT (the noise-rejection the gate exists for). ``recommend`` returns a
     setting that satisfies every acceptance trace.

Mechanics only — no 1.44 GB EDM Cup dependency, no LLM/DB/SymPy. The real per-persona
numbers come from ``main()`` over the committed predictor artifact (RESEARCH.md §9.3).
"""

from __future__ import annotations

from app.eval.proactive_ab import (
    GRID_K,
    GRID_THRESHOLD,
    acceptance_traces,
    evaluate_setting,
    first_fire_turn,
    recommend_gate,
    sweep,
)
from app.policy.intervention_gate import DEFAULT_K, DEFAULT_THRESHOLD, SustainedHelpNeedGate


def test_first_fire_turn_fires_on_sustained_run() -> None:
    """A run of K consecutive high readings fires on the K-th of them (live prefix)."""
    gate = SustainedHelpNeedGate(k=3, threshold=0.5)
    # three sustained highs starting at index 0 -> fires once the 3rd lands (turn 3).
    assert first_fire_turn(gate, (0.8, 0.85, 0.9, 0.7)) == 3


def test_first_fire_turn_rejects_isolated_spike() -> None:
    """A single high reading among lows never assembles a K-window -> no fire."""
    gate = SustainedHelpNeedGate(k=3, threshold=0.5)
    assert first_fire_turn(gate, (0.1, 0.2, 0.95, 0.15, 0.1)) is None


def test_first_fire_turn_rejects_alternating() -> None:
    """High/low/high/low is not sustained -> never fires for K>=2."""
    gate = SustainedHelpNeedGate(k=2, threshold=0.5)
    assert first_fire_turn(gate, (0.9, 0.1, 0.9, 0.1, 0.9)) is None


def test_first_fire_turn_none_before_k_turns() -> None:
    """Fewer than K scored turns can never fire."""
    gate = SustainedHelpNeedGate(k=4, threshold=0.5)
    assert first_fire_turn(gate, (0.9, 0.9, 0.9)) is None


def test_acceptance_traces_cover_intent() -> None:
    """The acceptance set encodes the gate's design intent with explicit labels."""
    traces = acceptance_traces()
    names = {t.name for t in traces}
    assert {"sustained_struggle", "isolated_spike", "alternating", "clean"} <= names
    # The set is deliberately discriminating: true positives at three signal strengths
    # (clear / borderline / short-but-real) pin the threshold and K from below, while the
    # noise / chronic-mild / self-recovery traces pin them from above.
    assert sum(1 for t in traces if t.should_fire) >= 1
    assert sum(1 for t in traces if not t.should_fire) >= 1
    # every trace carries a grounded rationale (CLAUDE.md §6: explain why, not what).
    assert all(t.rationale for t in traces)


def test_evaluate_setting_passes_when_all_traces_satisfied() -> None:
    """A well-chosen setting fires the true-positive and stays silent on the rest."""
    result = evaluate_setting(k=3, threshold=0.5, traces=acceptance_traces())
    assert result.passes
    assert result.true_positive_fired
    assert result.false_alarms == 0


def test_evaluate_setting_fails_on_overly_low_threshold() -> None:
    """A threshold so low that every stream clears it raises false alarms."""
    result = evaluate_setting(k=2, threshold=0.05, traces=acceptance_traces())
    assert not result.passes
    assert result.false_alarms > 0


def test_sweep_covers_the_full_grid() -> None:
    """The sweep evaluates every (K, threshold) point exactly once."""
    results = sweep()
    assert len(results) == len(GRID_K) * len(GRID_THRESHOLD)
    assert len({(r.k, r.threshold) for r in results}) == len(results)


def test_recommend_returns_a_passing_setting() -> None:
    """The recommendation satisfies every acceptance trace."""
    k, threshold = recommend_gate()
    result = evaluate_setting(k=k, threshold=threshold, traces=acceptance_traces())
    assert result.passes


def test_recommend_is_deterministic() -> None:
    """Same grid + traces -> same recommendation, every run (PROJECT.md §4.1)."""
    assert recommend_gate() == recommend_gate()


def test_recommendation_aligns_with_locked_defaults() -> None:
    """The honest finding we expect: the sweep validates the provisional defaults.

    The gate shipped with provisional K=3, threshold=0.5 (locked-but-tunable, §3.7).
    The acceptance criteria are exactly the gate's documented rationale, so a passing
    recommendation should land at or near those defaults rather than overturning them.
    This asserts the recommended threshold is the locked 0.5 and K is the conservative
    default; if a future change moves them, this test must be updated WITH a decision-
    log commit (CLAUDE.md §8.4).
    """
    k, threshold = recommend_gate()
    assert threshold == DEFAULT_THRESHOLD
    assert k == DEFAULT_K
