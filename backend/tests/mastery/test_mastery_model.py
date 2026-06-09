"""Tests for the mastery model (Slices 1.5 + 1.6), written TEST-FIRST.

CLAUDE.md §2 makes TDD mandatory here and is explicit: "Every rule in
PROJECT.md §3.4 ... gets a test that asserts the rule is enforced." The
mastery model is load-bearing — if BKT-over-threshold alone could declare
mastery, every adversarial persona (Nate, Hugo, Sam, Cleo) would slip through
and the false-positive-mastery headline metric (PROJECT.md §3.9) would be a
lie. So each test below sets up the case where the raw BKT probability is ABOVE
τ and asserts that the corresponding §3.4 rule still BLOCKS the declaration.
These are the unit-level analogs of the persona integration tests that arrive
in Week 2 (PROJECT.md §4.2; ARCHITECTURE.md §5).

No LLM, no DB, no SymPy here (CLAUDE.md §8.1): the mastery model is pure,
deterministic logic over BKT parameters and an attempt log.

Sources pinned by these tests:
  - PROJECT.md §3.4 (the four declaration rules), §3.6 (interleaving cadence),
    §4.2 (the personas each rule defeats), §8 0.D.5 (τ=0.85, cadence=3 across
    ≥2 KCs, productive-struggle window 60s), §8 0.D.2 (cold-start self-report
    is a BKT prior, not a commitment).
  - ARCHITECTURE.md §6 (the mastery model spec).
"""

from __future__ import annotations

import pytest
from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.mastery.mastery_model import (
    DEFAULT_BKT_PARAMS,
    ENGAGEMENT_FLOOR_MS,
    HINTED_CORRECT_WEIGHT,
    INTERLEAVE_CADENCE,
    INTERLEAVE_MIN_KCS,
    MASTERY_THRESHOLD,
    MIN_ATTEMPTS_FOR_MASTERY,
    MIN_REPRESENTATIONS,
    BktParams,
    Observation,
    bkt_update,
    declare_mastery,
    initial_prior_from_self_report,
    kc_mastery_probability,
)

KC = KnowledgeComponentId.EQUIVALENCE
OTHER_KC = KnowledgeComponentId.COMMON_DENOMINATOR


def _obs(
    *,
    kc: KnowledgeComponentId = KC,
    correct: bool = True,
    representation: Representation = Representation.SYMBOLIC,
    hinted: bool = False,
    latency_ms: int = 8_000,
) -> Observation:
    """Build an Observation with sane, well-above-floor defaults.

    Defaults are an *engaged, unhinted, correct* attempt so each test only has
    to vary the one dimension the rule under test cares about.
    """
    return Observation(
        kc=kc,
        correct=correct,
        representation=representation,
        hinted=hinted,
        latency_ms=latency_ms,
    )


def _interleaved_mastery_log() -> list[Observation]:
    """A clean happy-path log: BKT well over τ, ≥2 reps, an unhinted correct,
    the KC's correct items interleaved across ≥2 KCs at cadence, and ≥ the
    minimum-attempts floor (MIN_ATTEMPTS_FOR_MASTERY) of scored attempts on KC.

    Correct EQUIVALENCE items appear in two representations (symbolic + area
    model) and are separated by correct COMMON_DENOMINATOR items, so the KC's
    successes are interleaved, not a blocked run. Five EQUIVALENCE attempts clear
    the minimum-attempts floor (a genuine learner accumulates more than two
    corrects before mastery).
    """
    return [
        _obs(kc=KC, representation=Representation.SYMBOLIC),
        _obs(kc=OTHER_KC, representation=Representation.SYMBOLIC),
        _obs(kc=KC, representation=Representation.AREA_MODEL),
        _obs(kc=OTHER_KC, representation=Representation.AREA_MODEL),
        _obs(kc=KC, representation=Representation.SYMBOLIC),
        _obs(kc=OTHER_KC, representation=Representation.SYMBOLIC),
        _obs(kc=KC, representation=Representation.AREA_MODEL),
        _obs(kc=OTHER_KC, representation=Representation.SYMBOLIC),
        _obs(kc=KC, representation=Representation.SYMBOLIC),
    ]


# ─────────────────────────────── BKT (Slice 1.5) ───────────────────────────────


def test_bkt_update_increases_prior_on_correct() -> None:
    """A correct observation must raise the posterior mastery probability."""
    prior = 0.3
    posterior = bkt_update(prior, correct=True, params=DEFAULT_BKT_PARAMS)
    assert posterior > prior


def test_bkt_update_decreases_prior_on_incorrect() -> None:
    """An incorrect observation must lower the posterior mastery probability."""
    prior = 0.6
    posterior = bkt_update(prior, correct=False, params=DEFAULT_BKT_PARAMS)
    assert posterior < prior


def test_bkt_update_stays_in_unit_interval() -> None:
    """Posterior is a probability — must remain within [0, 1] for any input."""
    for prior in (0.0, 0.01, 0.5, 0.99, 1.0):
        for correct in (True, False):
            posterior = bkt_update(prior, correct=correct, params=DEFAULT_BKT_PARAMS)
            assert 0.0 <= posterior <= 1.0


def test_bkt_update_matches_hand_computed_value() -> None:
    """Pin the exact standard-BKT arithmetic so the formula can't silently drift.

    With p_slip=0.1, p_guess=0.2, p_transit=0.1 and prior=0.5:
      correct evidence: P(L|obs) = 0.5*0.9 / (0.5*0.9 + 0.5*0.2) = 0.45/0.55
      then transit:     P(L') = 0.8181... + (1-0.8181...)*0.1 = 0.836363...
    """
    params = BktParams(p_init=0.5, p_transit=0.1, p_slip=0.1, p_guess=0.2)
    posterior = bkt_update(0.5, correct=True, params=params)
    assert posterior == pytest.approx(0.8363636, abs=1e-6)


def test_bkt_repeated_correct_converges_above_threshold() -> None:
    """Enough correct evidence must be able to push a KC over τ.

    Sanity check that the parameters allow mastery to be reached at all — a
    model that can never cross τ would make every persona a (trivial) pass.
    """
    prob = DEFAULT_BKT_PARAMS.p_init
    for _ in range(8):
        prob = bkt_update(prob, correct=True, params=DEFAULT_BKT_PARAMS)
    assert prob > MASTERY_THRESHOLD


def test_kc_mastery_probability_only_counts_target_kc() -> None:
    """Per-KC BKT: other KCs' observations must not move this KC's probability."""
    log = [_obs(kc=OTHER_KC) for _ in range(5)]
    prob = kc_mastery_probability(KC, log, params=DEFAULT_BKT_PARAMS)
    assert prob == pytest.approx(DEFAULT_BKT_PARAMS.p_init)


# ───────────────── Cold-start prior hook (Slice 1.5; 0.D.2) ─────────────────


def test_self_report_seeds_prior_but_does_not_commit() -> None:
    """0.D.2: the routing self-report is a BKT PRIOR, not a commitment.

    Choosing a KC at routing seeds a higher prior than the de-emphasized
    "not sure" default, but subsequent WRONG evidence must be able to drag the
    probability back below where an unseeded learner started — i.e. turn-1
    performance can override the self-report.
    """
    chosen_prior = initial_prior_from_self_report(KC, chosen_kc=KC)
    unsure_prior = initial_prior_from_self_report(KC, chosen_kc=None)
    assert chosen_prior > unsure_prior

    # Evidence overrides the prior: a wrong answer pulls the seeded prior down.
    after_wrong = bkt_update(chosen_prior, correct=False, params=DEFAULT_BKT_PARAMS)
    assert after_wrong < chosen_prior


def test_self_report_prior_is_a_valid_probability() -> None:
    """The seeded prior must still be a probability (the rest of BKT assumes it)."""
    for chosen in (KC, None):
        prior = initial_prior_from_self_report(KC, chosen_kc=chosen)
        assert 0.0 <= prior <= 1.0


# ─────────────── §3.4 augmentation rules (Slice 1.6) — each BLOCKS ───────────────


def test_happy_path_declares_mastery() -> None:
    """All four §3.4 rules satisfied + BKT>τ + engaged → mastered.

    This is the reference for what a genuine mastery looks like; the blocking
    tests below each remove exactly one ingredient.
    """
    mastered, reasons = declare_mastery(KC, _interleaved_mastery_log())
    assert mastered, reasons
    assert reasons == []


def test_rule2_single_representation_blocks_mastery() -> None:
    """§3.4 rule 2 (defeats Natural-number Nate): BKT>τ but only ONE
    representation → NOT mastered.

    Nate can pass symbolic equivalence yet fail magnitude reasoning; mastery
    from a single representation is exactly the false positive this rule kills.
    """
    # Many correct symbolic-only items: BKT will clear τ, but rep-count == 1.
    log = [
        _obs(kc=KC if i % 2 == 0 else OTHER_KC, representation=Representation.SYMBOLIC)
        for i in range(12)
    ]
    assert kc_mastery_probability(KC, log) > MASTERY_THRESHOLD
    mastered, reasons = declare_mastery(KC, log)
    assert not mastered
    assert any("representation" in r.lower() for r in reasons)


def test_rule3_all_hinted_blocks_mastery() -> None:
    """§3.4 rule 3 (defeats Hint-hunter Hugo): BKT>τ but EVERY correct attempt
    was hinted → NOT mastered (needs ≥1 unscaffolded correct).
    """
    log = [
        _obs(
            kc=KC if i % 2 == 0 else OTHER_KC,
            representation=Representation.SYMBOLIC if i % 4 < 2 else Representation.AREA_MODEL,
            hinted=True,
        )
        for i in range(12)
    ]
    mastered, reasons = declare_mastery(KC, log)
    assert not mastered
    assert any("scaffold" in r.lower() or "hint" in r.lower() for r in reasons)


def test_rule3_hinted_correct_is_downweighted_in_bkt() -> None:
    """§3.4 rule 3: hinted correct attempts are DOWNWEIGHTED, not full evidence.

    Two identical correct logs that differ only in `hinted` must yield a lower
    KC probability for the hinted one — the scaffold did part of the reasoning.
    """
    unhinted = [_obs(kc=KC, hinted=False) for _ in range(4)]
    hinted = [_obs(kc=KC, hinted=True) for _ in range(4)]
    assert HINTED_CORRECT_WEIGHT < 1.0
    assert kc_mastery_probability(KC, hinted) < kc_mastery_probability(KC, unhinted)


def test_rule4_single_representation_blocked_run_blocks_mastery() -> None:
    """§3.4 rule 4 (defeats Surface Sam): a BLOCKED run in ONE representation must NOT reach
    mastery, however many corrects. This is Sam's signature — near-100% inside one format,
    no evidence he can reason any other way.

    NOTE (2026-05-29): rule 4 was relaxed for single-skill lessons — a single KC across ≥2
    representations now counts as varied practice (see
    ``test_single_skill_lesson_masters_via_two_representations``). So the Surface-Sam guard now
    rests on representation diversity (rule 2) + the S5 transfer probe, which this
    one-representation run still fails. A blocked run in a SINGLE format is the case that must
    keep failing.
    """
    log = [_obs(kc=KC, representation=Representation.SYMBOLIC) for _ in range(10)]
    mastered, reasons = declare_mastery(KC, log)
    assert not mastered
    assert any(
        "interleav" in r.lower() or "block" in r.lower() or "representation" in r.lower()
        for r in reasons
    )


def test_rule4_blocked_run_counts_for_less_than_interleaved() -> None:
    """§3.4 rule 4: a blocked correct run contributes LESS weight than the same
    number of correct answers interleaved across KCs.
    """
    blocked = [_obs(kc=KC) for _ in range(4)]
    interleaved = [
        _obs(kc=KC),
        _obs(kc=OTHER_KC),
        _obs(kc=KC),
        _obs(kc=OTHER_KC),
        _obs(kc=KC),
        _obs(kc=OTHER_KC),
        _obs(kc=KC),
    ]  # same 4 KC corrects, but interleaved
    assert kc_mastery_probability(KC, blocked) < kc_mastery_probability(KC, interleaved)


def test_single_skill_lesson_masters_via_two_representations() -> None:
    """Within-skill interleaving (2026-05-29 single-skill lessons): a lesson on ONE KC reaches
    mastery when its correct, engaged items span ≥2 representations of that KC (e.g. number-line
    PLACING + COMPARING), with NO second KC. Rule 4's cross-KC requirement is satisfied by the
    representation mix instead."""
    nl = KnowledgeComponentId.NUMBER_LINE_PLACEMENT
    two_rep = []
    for _ in range(5):  # alternate the two representations, enough attempts to clear τ + the floor
        two_rep.append(_obs(kc=nl, representation=Representation.NUMBER_LINE))
        two_rep.append(_obs(kc=nl, representation=Representation.SYMBOLIC))
    mastered, reasons = declare_mastery(nl, two_rep)
    assert mastered, f"single-skill two-representation lesson should master; blocked by: {reasons}"


def test_interleave_cadence_traces_to_locked_tuning() -> None:
    """0.D.5: interleaving cadence = 3 items across ≥2 KCs."""
    assert INTERLEAVE_CADENCE == 3
    assert INTERLEAVE_MIN_KCS == 2


def test_engagement_floor_flags_sub_floor_latency() -> None:
    """Engagement floor (defeats Click-through Cleo): a sub-floor response is
    flagged and does NOT count as mastery evidence.

    Cleo answers in under ~2s, picking the first option; if a lucky-correct
    sub-floor run could declare mastery, that's the disengagement false positive.
    """
    log = [
        _obs(
            kc=KC if i % 2 == 0 else OTHER_KC,
            representation=Representation.SYMBOLIC if i % 4 < 2 else Representation.AREA_MODEL,
            latency_ms=ENGAGEMENT_FLOOR_MS - 1,
        )
        for i in range(12)
    ]
    assert all(o.is_low_engagement() for o in log)
    mastered, reasons = declare_mastery(KC, log)
    assert not mastered
    assert any("engagement" in r.lower() for r in reasons)


def test_engagement_floor_constant_traces_to_locked_tuning() -> None:
    """0.D.5 / §3.4: the floor exists and is a positive sub-second-to-seconds
    threshold (Cleo's sub-2s signature lives below it)."""
    assert ENGAGEMENT_FLOOR_MS > 0
    # A genuine attempt at a fraction item is seconds, not milliseconds.
    assert _obs(latency_ms=8_000).is_low_engagement() is False


def test_threshold_traces_to_locked_tuning() -> None:
    """τ = 0.90 (raised from the 0.D.5 lock of 0.85 on 2026-05-29, product-owner
    authorized: crossing τ in two corrects was too easy)."""
    assert MASTERY_THRESHOLD == 0.90
    assert MIN_REPRESENTATIONS == 2


def test_minimum_attempts_floor_blocks_mastery() -> None:
    """Minimum-attempts floor (2026-05-29): BKT > τ and every other §3.4 rule
    satisfied, but FEWER than MIN_ATTEMPTS_FOR_MASTERY scored attempts on the KC
    → NOT mastered. "Two right != mastered": a lucky short streak that clears the
    threshold must still be denied until enough attempts have accumulated.
    """
    assert MIN_ATTEMPTS_FOR_MASTERY == 5
    # Three engaged, unhinted, interleaved, multi-rep corrects on KC: enough to
    # clear τ AND satisfy rules 2/3/4, but only 3 scored attempts on KC. The
    # floor must be the lone blocker — proving it bites independently of τ.
    log = [
        _obs(kc=KC, representation=Representation.SYMBOLIC),
        _obs(kc=OTHER_KC, representation=Representation.AREA_MODEL),
        _obs(kc=KC, representation=Representation.AREA_MODEL),
        _obs(kc=OTHER_KC, representation=Representation.SYMBOLIC),
        _obs(kc=KC, representation=Representation.SYMBOLIC),
    ]
    assert kc_mastery_probability(KC, log) > MASTERY_THRESHOLD  # τ is satisfied
    assert sum(1 for o in log if o.kc == KC) < MIN_ATTEMPTS_FOR_MASTERY
    mastered, reasons = declare_mastery(KC, log)
    assert not mastered
    assert any("minimum attempt" in r.lower() for r in reasons)
    # And ONLY the floor blocks: no other rule's reason is present.
    assert len(reasons) == 1


def test_minimum_attempts_floor_counts_only_engaged_attempts() -> None:
    """The minimum-attempts floor is a QUANTITY-OF-EVIDENCE gate, so disengaged
    (sub-floor) clicks must not pad it. A Click-through-Cleo with only three genuine
    engaged corrects (enough for rules 1–4) plus two sub-floor clicks must STILL be
    blocked by the floor — otherwise non-evidence (a click that counts for nothing in
    BKT or any quality rule) is allowed to satisfy an evidence gate.
    """
    log = [
        _obs(kc=KC, representation=Representation.SYMBOLIC),
        _obs(kc=OTHER_KC, representation=Representation.AREA_MODEL),
        _obs(kc=KC, representation=Representation.AREA_MODEL),
        _obs(kc=OTHER_KC, representation=Representation.SYMBOLIC),
        _obs(kc=KC, representation=Representation.SYMBOLIC),
        # Two sub-floor clicks on KC (latency below the 2000 ms engagement floor):
        # five RAW attempts on KC, but only three of engaged evidence.
        _obs(kc=KC, representation=Representation.SYMBOLIC, latency_ms=500),
        _obs(kc=KC, representation=Representation.SYMBOLIC, latency_ms=500),
    ]
    assert sum(1 for o in log if o.kc == KC) == 5  # raw attempts clear 5…
    mastered, reasons = declare_mastery(KC, log)
    assert not mastered  # …but disengaged clicks don't count, so the floor still bites
    assert any("minimum attempt" in r.lower() for r in reasons)


def test_below_threshold_blocks_even_with_all_rules_met() -> None:
    """Rule 1: if BKT ≤ τ, mastery is blocked regardless of the other rules.

    A short interleaved, multi-rep, unhinted, engaged log can satisfy rules
    2–4 yet not have accumulated enough evidence to clear τ.
    """
    log = [
        _obs(kc=KC, representation=Representation.SYMBOLIC),
        _obs(kc=OTHER_KC),
        _obs(kc=KC, representation=Representation.AREA_MODEL),
    ]
    prob = kc_mastery_probability(KC, log)
    if prob <= MASTERY_THRESHOLD:
        mastered, reasons = declare_mastery(KC, log)
        assert not mastered
        assert any("threshold" in r.lower() or "bkt" in r.lower() for r in reasons)


def test_mastery_is_provisional_until_transfer_probe() -> None:
    """§3.4 / ARCHITECTURE §6: even a clean pass is PROVISIONAL until S5.

    The transfer probe is a later slice; here we only assert this slice does
    not over-claim — `declare_mastery` returns provisional mastery, signalled
    by the documented flag/field, never "confirmed".
    """
    mastered, _ = declare_mastery(KC, _interleaved_mastery_log())
    # The function name and docstring must mark this provisional; we assert the
    # boolean is the provisional declaration, not a transfer-confirmed one.
    assert mastered is True
    # No transfer-confirmation API exists in this slice (guard against scope creep).
    import app.mastery.mastery_model as mm

    assert not hasattr(mm, "confirm_transfer")
