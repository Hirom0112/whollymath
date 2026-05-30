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
    # Grade-6 Unit 1: ratio language reads a ratio as a fraction relationship (part-of-the-whole),
    # so it builds on equivalent fractions — the conceptual entry to the ratio strand.
    _KC.RATIO_LANGUAGE: frozenset({_KC.EQUIVALENCE}),
    # Grade-6 Unit 1: a unit rate is a ratio relationship, so it builds on equivalent fractions.
    _KC.UNIT_RATE: frozenset({_KC.EQUIVALENCE}),
    _KC.EQUIVALENT_RATIOS: frozenset({_KC.EQUIVALENCE}),
    # Percent forward-unlocks on equivalence (a percent is a per-100 ratio). Its decimal-ops
    # prereq (REMEDIATION_ROUTING) isn't a forward edge — that KC isn't live yet.
    _KC.PERCENT: frozenset({_KC.EQUIVALENCE}),
    # Grade-6 Unit 2 (T2): multiplying fractions builds on naming the same number (you reduce
    # the product), so it forward-unlocks on equivalence.
    _KC.MULTIPLY_FRACTIONS: frozenset({_KC.EQUIVALENCE}),
    # Grade-6 Unit 1: a unit conversion via proportions IS unit-rate reasoning applied to a
    # known factor, so it forward-unlocks on the unit rate.
    _KC.UNIT_CONVERSION: frozenset({_KC.UNIT_RATE}),
    # Grade-6 Unit 2: GCF/LCM generalizes finding a shared denominator (the LCM IS the least
    # common denominator), so it forward-unlocks on common-denominator — matching its
    # REMEDIATION_ROUTING drop target.
    _KC.GCF_LCM: frozenset({_KC.COMMON_DENOMINATOR}),
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
    _KC.RATIO_LANGUAGE,  # Grade-6 Unit 1: read a ratio (part-part vs part-whole), on equivalence
    _KC.UNIT_RATE,  # Grade-6 Unit 1: a ratio relationship, built on equivalence
    _KC.EQUIVALENT_RATIOS,  # Grade-6 Unit 1: scale a ratio multiplicatively
    _KC.PERCENT,  # Grade-6 Unit 1: a per-100 ratio
    _KC.MULTIPLY_FRACTIONS,  # Grade-6 Unit 2: multiply fractions, built on equivalence
    _KC.UNIT_CONVERSION,  # Grade-6 Unit 1: convert via proportions, built on the unit rate
    _KC.GCF_LCM,  # Grade-6 Unit 2: GCF/LCM, generalizes the common denominator (LCM = LCD)
)


# ─── Reactive-remediation routing table (CURRICULUM_STANDARD.md §11.1) ───
#
# A SEPARATE graph from KC_PREREQUISITES above. That one is the 5-KC forward-unlock spine (what to
# teach NEXT). This is the Grade-6 reactive DROP-DOWN map: when the help gate trips inside a
# grade-level lesson, which prerequisite ONE LEVEL DOWN to remediate (§11). Kept separate so the
# forward graph (and its course-map / unlocked() consumers) is untouched. Each grade-6 KC → its
# direct prerequisite(s); the §11.3 selector picks ONE from the tuple (error-category bias +
# lowest mastery). The five FOUNDATION fraction KCs are deliberately ABSENT — they are terminal
# (§11.1: no auto-drop below the foundation; a learner struggling there stays and works it).
# Entries cover the lessons §11.1 enumerates; KCs not yet routed get no drop until content lands.
_KC_ = KnowledgeComponentId
REMEDIATION_ROUTING: dict[KnowledgeComponentId, tuple[KnowledgeComponentId, ...]] = {
    # U1 — Ratios & Rates → equivalent fractions (ratio = a fraction relationship). NOTE: a
    # grade-6 KC stays a remediation SOURCE even after it is built/live — only the FIVE FOUNDATION
    # fraction KCs are terminal (§11.1). A struggling percent learner still drops to equivalence.
    _KC_.RATIO_LANGUAGE: (_KC_.EQUIVALENCE,),
    _KC_.EQUIVALENT_RATIOS: (_KC_.EQUIVALENCE,),
    _KC_.UNIT_RATE: (_KC_.EQUIVALENCE,),
    _KC_.RATE_PROBLEMS: (_KC_.EQUIVALENCE,),
    _KC_.PERCENT: (_KC_.EQUIVALENCE, _KC_.DECIMAL_OPERATIONS),
    _KC_.UNIT_CONVERSION: (_KC_.UNIT_RATE,),
    # U2 — Fractions & Decimals
    _KC_.DIVIDE_FRACTIONS: (_KC_.ADDITION_UNLIKE, _KC_.SUBTRACTION_UNLIKE, _KC_.EQUIVALENCE),
    _KC_.MULTIPLY_FRACTIONS: (_KC_.EQUIVALENCE,),
    _KC_.GCF_LCM: (_KC_.COMMON_DENOMINATOR,),
    _KC_.DECIMAL_OPERATIONS: (_KC_.MULTI_DIGIT_DIVISION,),
    # U3 — Rational Numbers
    _KC_.RATIONALS_ON_LINE: (_KC_.NUMBER_LINE_PLACEMENT,),
    _KC_.ORDERING_INEQUALITIES: (_KC_.NUMBER_LINE_PLACEMENT, _KC_.SIGNED_NUMBERS),
    _KC_.CLASSIFY_NUMBER_SETS: (_KC_.SIGNED_NUMBERS,),
    _KC_.COORDINATE_PLANE: (_KC_.RATIONALS_ON_LINE,),
    # U-INT — Integer Arithmetic (rides the rational-number line)
    _KC_.INTEGER_ADD_SUBTRACT: (
        _KC_.RATIONALS_ON_LINE,
        _KC_.ADDITION_UNLIKE,
        _KC_.SUBTRACTION_UNLIKE,
    ),
    _KC_.INTEGER_MULTIPLY_DIVIDE: (_KC_.INTEGER_ADD_SUBTRACT,),
    # U4–U5 — Expressions & Equations
    _KC_.EVALUATE_EXPRESSIONS: (_KC_.EXPONENTS,),
    _KC_.ONE_STEP_EQUATIONS: (_KC_.EVALUATE_EXPRESSIONS,),
    # U6 — Geometry
    _KC_.AREA_POLYGONS: (_KC_.EVALUATE_EXPRESSIONS,),
    _KC_.VOLUME_FRACTIONAL_EDGES: (_KC_.MULTIPLY_FRACTIONS,),
    _KC_.POLYGONS_COORDINATE_PLANE: (_KC_.COORDINATE_PLANE,),
    # U8 — Financial Literacy (TEKS)
    _KC_.CHECK_REGISTER: (_KC_.INTEGER_ADD_SUBTRACT,),
    _KC_.LIFETIME_INCOME: (_KC_.MULTIPLY_FRACTIONS, _KC_.DECIMAL_OPERATIONS),
}


def prerequisites_of(kc: KnowledgeComponentId) -> frozenset[KnowledgeComponentId]:
    """The KCs that must be confirmed before ``kc`` is the right next skill to introduce."""
    return KC_PREREQUISITES[kc]


def remediation_targets(kc: KnowledgeComponentId) -> tuple[KnowledgeComponentId, ...]:
    """The direct prerequisite(s) ``kc`` reactively drops to when its help gate trips (§11.1).

    Empty for a KC with no routed drop — including the five foundation fraction KCs, which are
    TERMINAL (§11.1: no auto-drop below the foundation). The §11.3 selector chooses ONE of the
    returned targets; the order here is the §11.1 listing order (the natural primary first).
    """
    return REMEDIATION_ROUTING.get(kc, ())


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


__all__ = [
    "KC_PREREQUISITES",
    "REMEDIATION_ROUTING",
    "SPINE_ORDER",
    "prerequisites_of",
    "remediation_targets",
    "unlocked",
]
