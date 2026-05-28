"""The false-positive-mastery defense, asserted (Slice 4.1.2; PROJECT.md §3.11, §4).

Each persona attacks a different mastery rule; the defense holds when NONE of them
reaches CONFIRMED mastery on its attacked KC. These tests are the mastery model's
integration suite (CLAUDE.md §9): if any persona could be confirmed-mastered, the
corresponding rule is broken. We assert both the verdict (denied) AND the mechanism
(which stage/rule caught it), so a regression that denies mastery for the WRONG
reason is also caught.
"""

from __future__ import annotations

from app.eval.false_positive_harness import (
    PersonaMasteryResult,
    run_false_positive_harness,
)


def _by_id() -> dict[str, PersonaMasteryResult]:
    return {r.persona_id: r for r in run_false_positive_harness()}


def test_no_persona_reaches_confirmed_mastery() -> None:
    """THE defense (PROJECT.md §3.11): every persona is denied confirmed mastery."""
    results = run_false_positive_harness()
    assert len(results) == 5
    confirmed = [r.persona_name for r in results if r.confirmed_mastery]
    assert confirmed == [], f"false-positive mastery for: {confirmed}"


def test_sam_blocked_at_provisional_by_diversity_and_interleaving() -> None:
    """Surface Sam: fluent only in his tied format → rules 2 & 4 block at provisional."""
    sam = _by_id()["surface_sam"]
    assert sam.confirmed_mastery is False
    assert sam.blocked_at == "provisional"
    blob = " ".join(sam.reasons).lower()
    assert "representation diversity" in blob  # rule 2
    assert "interleaving" in blob  # rule 4


def test_nate_blocked_by_single_representation() -> None:
    """Natural-number Nate: correct in one representation only → rule 2 blocks."""
    nate = _by_id()["natural_number_nate"]
    assert nate.confirmed_mastery is False
    assert nate.blocked_at == "provisional"
    assert "representation diversity" in " ".join(nate.reasons).lower()


def test_hugo_blocked_by_scaffolding_rule() -> None:
    """Hint-hunter Hugo: every correct attempt was hinted → rule 3 blocks."""
    hugo = _by_id()["hint_hunter_hugo"]
    assert hugo.confirmed_mastery is False
    assert hugo.blocked_at == "provisional"
    assert "scaffolding" in " ".join(hugo.reasons).lower()


def test_cleo_blocked_by_engagement_floor() -> None:
    """Click-through Cleo: every turn below the engagement floor → no engaged evidence."""
    cleo = _by_id()["click_through_cleo"]
    assert cleo.confirmed_mastery is False
    assert cleo.blocked_at == "provisional"
    assert "engagement floor" in " ".join(cleo.reasons).lower()


def test_priya_reaches_provisional_but_fails_the_transfer_probe() -> None:
    """Procedure Priya: looks fluent (PROVISIONAL), but the S5 transfer probe catches
    her procedure-without-concept — confirmed mastery denied at the probe, not earlier.

    This is the demonstration that the transfer probe is LOAD-BEARING: declare_mastery
    alone would pass her; only the error-finding+justification gate denies her.
    """
    priya = _by_id()["procedure_priya"]
    assert priya.provisional_mastery is True, "Priya should look fluent enough to reach provisional"
    assert priya.confirmed_mastery is False
    assert priya.blocked_at == "transfer_probe"
    assert "error_finding" in " ".join(priya.reasons).lower()


def test_harness_is_deterministic() -> None:
    """Same harness ⇒ identical verdicts (PROJECT.md §4.1) — a trustworthy integration suite."""
    first = run_false_positive_harness()
    second = run_false_positive_harness()
    assert [(r.persona_id, r.confirmed_mastery, r.blocked_at) for r in first] == [
        (r.persona_id, r.confirmed_mastery, r.blocked_at) for r in second
    ]
