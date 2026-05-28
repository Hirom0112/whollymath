"""Tests for the KC prerequisite graph (Slice 6.x — spaced-repetition groundwork).

The graph encodes the algebra-readiness on-ramp (RESEARCH.md: Bailey 2012 — fraction
competence predicts later algebra gains; Siegler — fraction magnitude is the key idea): a
fraction is a NUMBER (number-line magnitude) → equivalent forms (equivalence) → matching
sizes (common denominator) → operating on unlike forms (add/sub). These tests pin that the
graph is a sound DAG and that ``unlocked`` gates new skills on confirmed prerequisites.
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.prerequisites import (
    KC_PREREQUISITES,
    SPINE_ORDER,
    prerequisites_of,
    unlocked,
)

KC = KnowledgeComponentId  # local shorthand (a constant alias; ruff-clean, unlike `import as`)


def test_every_kc_has_a_prerequisite_entry() -> None:
    """The graph is total over the catalog — no KC is missing from the map."""
    assert set(KC_PREREQUISITES) == set(KC)


def test_number_line_is_the_foundational_root() -> None:
    """Number-line placement (a fraction is a number) is the root — it has no prerequisites."""
    assert prerequisites_of(KC.NUMBER_LINE_PLACEMENT) == frozenset()


def test_the_algebra_spine_ordering() -> None:
    """equivalence ← number_line; common_denominator ← equivalence; add/sub ← common_denominator."""
    assert prerequisites_of(KC.EQUIVALENCE) == frozenset({KC.NUMBER_LINE_PLACEMENT})
    assert prerequisites_of(KC.COMMON_DENOMINATOR) == frozenset({KC.EQUIVALENCE})
    assert prerequisites_of(KC.ADDITION_UNLIKE) == frozenset({KC.COMMON_DENOMINATOR})
    assert prerequisites_of(KC.SUBTRACTION_UNLIKE) == frozenset({KC.COMMON_DENOMINATOR})


def test_graph_is_acyclic() -> None:
    """No KC can (transitively) require itself — a curriculum order must be a DAG."""

    def reaches(start: KC, target: KC, seen: set[KC]) -> bool:
        for pre in KC_PREREQUISITES[start]:
            if pre == target or (pre not in seen and reaches(pre, target, seen | {pre})):
                return True
        return False

    for kc in KC:
        assert not reaches(kc, kc, set()), f"{kc} is in a prerequisite cycle"


def test_unlocked_with_nothing_confirmed_is_just_the_root() -> None:
    """A brand-new learner can start only the foundational skill (and anything prereq-free)."""
    assert unlocked(frozenset()) == frozenset({KC.NUMBER_LINE_PLACEMENT})


def test_unlocked_opens_the_next_skill_as_prereqs_confirm() -> None:
    """Confirming number-line unlocks equivalence; confirming equivalence unlocks common-denom."""
    after_nl = unlocked(frozenset({KC.NUMBER_LINE_PLACEMENT}))
    assert KC.EQUIVALENCE in after_nl
    assert KC.COMMON_DENOMINATOR not in after_nl  # its prereq (equivalence) isn't confirmed yet

    after_eq = unlocked(frozenset({KC.NUMBER_LINE_PLACEMENT, KC.EQUIVALENCE}))
    assert KC.COMMON_DENOMINATOR in after_eq
    assert KC.ADDITION_UNLIKE not in after_eq


def test_confirming_common_denominator_unlocks_both_operations() -> None:
    """Common denominator is the gate to both add and subtract (the § rational-expression skill)."""
    after_cd = unlocked(
        frozenset({KC.NUMBER_LINE_PLACEMENT, KC.EQUIVALENCE, KC.COMMON_DENOMINATOR})
    )
    assert {KC.ADDITION_UNLIKE, KC.SUBTRACTION_UNLIKE} <= after_cd


def test_a_confirmed_kc_is_not_returned_as_newly_unlocked() -> None:
    """``unlocked`` returns skills available to LEARN NEXT — not ones already confirmed."""
    assert KC.NUMBER_LINE_PLACEMENT not in unlocked(frozenset({KC.NUMBER_LINE_PLACEMENT}))


def test_spine_order_covers_every_kc_exactly_once() -> None:
    """The canonical teaching order is a permutation of the whole catalog — no gaps, no dupes."""
    assert set(SPINE_ORDER) == set(KC)
    assert len(SPINE_ORDER) == len(set(SPINE_ORDER)) == len(list(KC))


def test_spine_order_is_a_valid_topological_order() -> None:
    """Every KC appears AFTER all of its prerequisites — the order is a DAG linearization.

    This is what lets the planner and the course map share one ordering safely: a skill is never
    presented before the skills it depends on (``prerequisites.py`` algebra-readiness rationale).
    """
    position = {kc: i for i, kc in enumerate(SPINE_ORDER)}
    for kc in SPINE_ORDER:
        for prereq in prerequisites_of(kc):
            assert position[prereq] < position[kc], f"{prereq} must precede {kc} in SPINE_ORDER"


def test_spine_order_starts_at_the_root() -> None:
    """The foundational, prerequisite-free skill (a fraction is a number) comes first."""
    assert SPINE_ORDER[0] == KC.NUMBER_LINE_PLACEMENT
