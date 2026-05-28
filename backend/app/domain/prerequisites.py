"""The KC prerequisite graph — the fractions→algebra on-ramp (spaced-repetition groundwork).

WHY this exists and why this exact ordering: the project teaches fractions *because* fraction
competence is the documented predictor of later algebra/math achievement (PROJECT.md §3.1;
RESEARCH.md — Bailey, Hoard, Nugent & Geary 2012, fraction concepts predict one-year math
gains over and above whole-number knowledge; Siegler's work on fraction *magnitude* as the
key idea). Two fraction ideas carry that algebra readiness, and they fix the order:

  1. **A fraction is a NUMBER with a magnitude** — not just "pieces of a pizza". This is
     ``NUMBER_LINE_PLACEMENT``; in algebra it is the number-line / quantity sense. It is the
     ROOT (no prerequisite) because everything else assumes a fraction names an amount.
  2. **A quantity can be REWRITTEN into an equivalent form** — ``EQUIVALENCE``; in algebra
     this is "equivalent expressions". It needs idea 1 (you can only see two names as the
     same *amount* once a fraction is an amount).

From there the chain is the algebra of rational expressions in miniature:

    NUMBER_LINE_PLACEMENT  (a fraction is a number)
            ↓
    EQUIVALENCE            (same number, different name)
            ↓
    COMMON_DENOMINATOR     (use equivalence to match sizes)
          ↓        ↓
    ADDITION_UNLIKE   SUBTRACTION_UNLIKE   (operate on unlike forms — exactly x/2 + x/3)

So this is a small DAG, NOT a curriculum: it says which skill *unlocks* which, which is all
spaced repetition + new-skill sequencing need (it does not prescribe a day-by-day lesson plan).
Pure data + pure functions: no DB, no LLM, no SymPy (CLAUDE.md §7, §8.1). Deterministic.
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId

_KC = KnowledgeComponentId

# Each KC → the set of KCs that must be CONFIRMED (mastered) before it is the right next thing
# to introduce. The root carries an empty set. See the module docstring for the algebra
# rationale behind each edge.
KC_PREREQUISITES: dict[KnowledgeComponentId, frozenset[KnowledgeComponentId]] = {
    _KC.NUMBER_LINE_PLACEMENT: frozenset(),
    _KC.EQUIVALENCE: frozenset({_KC.NUMBER_LINE_PLACEMENT}),
    _KC.COMMON_DENOMINATOR: frozenset({_KC.EQUIVALENCE}),
    _KC.ADDITION_UNLIKE: frozenset({_KC.COMMON_DENOMINATOR}),
    _KC.SUBTRACTION_UNLIKE: frozenset({_KC.COMMON_DENOMINATOR}),
}


# The canonical teaching order along the algebra-readiness spine — a topological linearization
# of the DAG above (every skill follows all of its prerequisites). This is the single source of
# truth for "in what order do these KCs come", shared by the study planner (which new skill to
# suggest) and the course map (how to lay out the path), so the two can never drift. A test
# pins that it stays a valid topological order covering every KC (test_prerequisites.py).
SPINE_ORDER: tuple[KnowledgeComponentId, ...] = (
    _KC.NUMBER_LINE_PLACEMENT,  # a fraction is a NUMBER (root, no prerequisite)
    _KC.EQUIVALENCE,  # same number, different name
    _KC.COMMON_DENOMINATOR,  # use equivalence to match sizes
    _KC.ADDITION_UNLIKE,  # operate on unlike forms …
    _KC.SUBTRACTION_UNLIKE,  # … (add/sub both gated on common denominator)
)


def prerequisites_of(kc: KnowledgeComponentId) -> frozenset[KnowledgeComponentId]:
    """The KCs that must be confirmed before ``kc`` is the right next skill to introduce."""
    return KC_PREREQUISITES[kc]


def unlocked(confirmed: frozenset[KnowledgeComponentId]) -> frozenset[KnowledgeComponentId]:
    """The skills available to LEARN NEXT, given the set of already-confirmed KCs.

    A KC is unlocked when ALL its prerequisites are confirmed AND it is not itself confirmed
    (a confirmed skill is no longer "next to learn" — it's a candidate for *review* instead,
    which the retention model handles). With nothing confirmed this is just the root skill.
    This is advisory sequencing for the scheduler — it never blocks the learner's chosen
    cold-start route (the route is the entry point; the graph orders what comes after).
    """
    return frozenset(
        kc
        for kc, prereqs in KC_PREREQUISITES.items()
        if kc not in confirmed and prereqs <= confirmed
    )


__all__ = ["KC_PREREQUISITES", "SPINE_ORDER", "prerequisites_of", "unlocked"]
