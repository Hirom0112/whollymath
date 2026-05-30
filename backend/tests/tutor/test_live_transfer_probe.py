"""Unit tests for the LIVE S5 transfer-probe builder (Slice AR.3).

``tutor.live_transfer_probe`` assembles the §3.9 confirm-gate items a REAL learner
answers before declared mastery is CONFIRMED. The research panel's "a single item is
not transfer" finding and PROJECT.md §3.4's ≥2-representations principle (AUDIT.md §7,
§3 cap 5) require that passing the probe is impossible on one lucky item: the probe must
span ≥2 items across ≥2 DISTINCT representations, and the verdict must be reconstructable
from a per-step audit trail.

These are pure/deterministic unit tests over the builder and the audit helper — no LLM,
no DB; SymPy still judges answers in the live loop (CLAUDE.md §8.1/§8.2). The end-to-end
wiring (the service serving the steps and deciding confirm/demote) is covered by
``tests/api/test_transfer_probe_live.py``; here we pin the builder's contract directly.
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.domain.problem_generators import Problem
from app.policy.scheduler import is_masterable_live, live_representations
from app.tutor.live_transfer_probe import (
    ProbeAuditEntry,
    build_live_probe_steps,
    build_probe_audit_trail,
)

# Every KC the live surface can actually carry to declared mastery (≥2 live representations).
# These are the KCs whose probe must be a genuine multi-representation transfer gate.
_MASTERABLE_KCS: tuple[KnowledgeComponentId, ...] = tuple(
    kc for kc in KnowledgeComponentId if is_masterable_live(kc)
)


def _distinct_representations(steps: list[Problem]) -> set[Representation]:
    return {step.surface_format for step in steps}


# ─── (a) ≥2 steps spanning ≥2 distinct representations, for EVERY masterable KC ──


def test_every_masterable_kc_probe_has_at_least_two_steps() -> None:
    """A single item can never be the whole probe: each masterable KC yields ≥2 steps,
    so passing requires more than one correct answer (research panel: single item ≠
    transfer; AUDIT.md §7)."""
    assert _MASTERABLE_KCS, "expected at least one live-masterable KC"
    for kc in _MASTERABLE_KCS:
        recent = live_representations(kc)[0]
        steps = build_live_probe_steps(kc, recent_format=recent)
        assert len(steps) >= 2, f"{kc.value} probe must have >=2 steps, got {len(steps)}"


def test_every_masterable_kc_probe_spans_at_least_two_representations() -> None:
    """The ≥2 steps must span ≥2 DISTINCT representations (PROJECT.md §3.4 rule 2): a
    format-tied grip cannot pass a probe that demands the skill in two surfaces."""
    for kc in _MASTERABLE_KCS:
        recent = live_representations(kc)[0]
        steps = build_live_probe_steps(kc, recent_format=recent)
        reps = _distinct_representations(steps)
        assert len(reps) >= 2, f"{kc.value} probe only spanned {reps}; need >=2 representations"


def test_representation_only_kcs_now_get_a_second_distinct_step() -> None:
    """Equivalence and number-line placement have no modeled wrong-claim, so historically
    their probe was a SINGLE representation item — a lucky one-item pass. They must now also
    carry a second step in a distinct representation."""
    for kc in (
        KnowledgeComponentId.EQUIVALENCE,
        KnowledgeComponentId.NUMBER_LINE_PLACEMENT,
    ):
        recent = live_representations(kc)[0]
        steps = build_live_probe_steps(kc, recent_format=recent)
        assert len(steps) >= 2
        assert len(_distinct_representations(steps)) >= 2


def test_first_step_avoids_the_recently_worked_format() -> None:
    """The opening transfer item is in a representation the learner did NOT just work, so the
    probe tests transfer, not the format they were drilling (the §3.9 representation-transfer)."""
    for kc in _MASTERABLE_KCS:
        live = live_representations(kc)
        recent = live[0]
        steps = build_live_probe_steps(kc, recent_format=recent)
        # Only meaningful when the KC has an alternative live format to move to.
        if len(live) >= 2:
            assert steps[0].surface_format != recent


def test_number_line_placement_keeps_an_honest_placement_step() -> None:
    """The number-line skill's placement item must remain a real mark-on-a-line item (its
    answer is a position), not be silently swapped for a symbolic-only pair. Its probe spans
    NUMBER_LINE and SYMBOLIC so the placement representation is genuinely present."""
    kc = KnowledgeComponentId.NUMBER_LINE_PLACEMENT
    # Drive from a SYMBOLIC recent format so the gate still must include the line.
    steps = build_live_probe_steps(kc, recent_format=Representation.SYMBOLIC)
    reps = _distinct_representations(steps)
    assert Representation.NUMBER_LINE in reps
    assert Representation.SYMBOLIC in reps


# ─── (b) one item right does NOT pass — the trail records a single pass as NOT-confirmed ──


def test_only_one_correct_step_does_not_confirm() -> None:
    """Passing exactly ONE of a multi-step probe does not pass the probe: the audit trail's
    verdict reconstruction requires EVERY step correct (research panel: single item ≠
    transfer). Asserted across every masterable KC, for each single-correct position."""
    for kc in _MASTERABLE_KCS:
        recent = live_representations(kc)[0]
        steps = build_live_probe_steps(kc, recent_format=recent)
        assert len(steps) >= 2
        for lucky in range(len(steps)):
            outcomes = [i == lucky for i in range(len(steps))]
            trail = build_probe_audit_trail(
                steps, submitted_answers=["x"] * len(steps), corrects=outcomes
            )
            assert not trail.passed, (
                f"{kc.value}: getting only step {lucky} right must NOT pass the probe"
            )


def test_all_steps_correct_passes() -> None:
    """The positive control: every step correct passes the probe (so the gate is not
    trivially always-fail)."""
    for kc in _MASTERABLE_KCS:
        recent = live_representations(kc)[0]
        steps = build_live_probe_steps(kc, recent_format=recent)
        trail = build_probe_audit_trail(
            steps, submitted_answers=["x"] * len(steps), corrects=[True] * len(steps)
        )
        assert trail.passed


# ─── (c) the per-step audit trail is populated and reconstructable ──


def test_audit_trail_records_one_entry_per_step_with_item_rep_answer_outcome() -> None:
    """Each step yields a reconstructable audit entry: the item (id + statement), the
    representation, the submitted answer, and correct/incorrect (AUDIT.md §7)."""
    kc = KnowledgeComponentId.ADDITION_UNLIKE
    steps = build_live_probe_steps(kc, recent_format=Representation.SYMBOLIC)
    answers = [f"answer-{i}" for i in range(len(steps))]
    corrects = [True] * len(steps)
    trail = build_probe_audit_trail(steps, submitted_answers=answers, corrects=corrects)

    assert len(trail.entries) == len(steps)
    for step, answer, entry in zip(steps, answers, trail.entries, strict=True):
        assert isinstance(entry, ProbeAuditEntry)
        assert entry.problem_id == step.problem_id
        assert entry.statement == step.statement
        assert entry.representation == step.surface_format
        assert entry.submitted_answer == answer
        assert entry.is_correct is True
        assert entry.kc == step.kc


def test_audit_trail_verdict_matches_per_step_correctness() -> None:
    """The trail's verdict is reconstructable from its entries alone: passed iff every entry
    is_correct, and the representations spanned are exactly the entries' representations."""
    kc = KnowledgeComponentId.ADDITION_UNLIKE
    steps = build_live_probe_steps(kc, recent_format=Representation.NUMBER_LINE)
    corrects = [True, True, False][: len(steps)]
    while len(corrects) < len(steps):
        corrects.append(True)
    trail = build_probe_audit_trail(
        steps, submitted_answers=["x"] * len(steps), corrects=corrects
    )
    assert trail.passed == all(corrects)
    assert trail.representations_covered == {e.representation for e in trail.entries}
    # Reconstructable: the verdict can be recomputed from the entries with no extra state.
    assert trail.passed == all(e.is_correct for e in trail.entries)


def test_audit_trail_rejects_mismatched_lengths() -> None:
    """A trail built with the wrong number of answers/outcomes is a programming error and
    fails loudly (CLAUDE.md §8.5), so a malformed audit can never silently look valid."""
    kc = KnowledgeComponentId.EQUIVALENCE
    steps = build_live_probe_steps(kc, recent_format=Representation.SYMBOLIC)
    bad_answers = ["x"]  # too few
    try:
        build_probe_audit_trail(steps, submitted_answers=bad_answers, corrects=[True] * len(steps))
    except ValueError:
        pass
    else:  # pragma: no cover - the assert below reports the failure
        raise AssertionError("mismatched audit lengths must raise ValueError")
