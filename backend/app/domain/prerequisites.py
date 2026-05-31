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
    # Grade-6 Unit 2 (T2): dividing fractions IS multiplying once you invert the divisor, so it
    # forward-unlocks on fraction multiplication.
    _KC.DIVIDE_FRACTIONS: frozenset({_KC.MULTIPLY_FRACTIONS}),
    # Grade-6 Unit 1: a unit conversion via proportions IS unit-rate reasoning applied to a
    # known factor, so it forward-unlocks on the unit rate.
    _KC.UNIT_CONVERSION: frozenset({_KC.UNIT_RATE}),
    # Grade-6 Unit 2: GCF/LCM generalizes finding a shared denominator (the LCM IS the least
    # common denominator), so it forward-unlocks on common-denominator — matching its
    # REMEDIATION_ROUTING drop target.
    _KC.GCF_LCM: frozenset({_KC.COMMON_DENOMINATOR}),
    # Grade-6 Unit 2: multi-digit division is whole-number arithmetic; the modeled error is a
    # place-value (magnitude) slip, so it forward-unlocks on number-line placement — judging a
    # number's magnitude on the line is the readiness that catches an off-by-ten quotient.
    _KC.MULTI_DIGIT_DIVISION: frozenset({_KC.NUMBER_LINE_PLACEMENT}),
    # Grade-6 Unit 2: a decimal is a fraction in per-ten/per-hundred clothing, so multiplying
    # decimals rests on naming the same number in an equivalent form — it forward-unlocks on
    # equivalence (its REMEDIATION_ROUTING drop is to multi-digit division, not yet live, so the
    # forward edge uses the live foundation KC the skill conceptually rests on).
    _KC.DECIMAL_OPERATIONS: frozenset({_KC.EQUIVALENCE}),
    # Grade-6 Unit 3: absolute value is distance from 0 on the line, so it forward-unlocks on
    # number-line placement — reading where a number sits relative to 0 is the readiness for "how
    # far from 0", and underpins the signed-vs-magnitude distinction the lesson targets.
    _KC.ABSOLUTE_VALUE: frozenset({_KC.NUMBER_LINE_PLACEMENT}),
    # Grade-6 Unit-INT: adding/subtracting integers is combining directed moves on the number
    # line, so it forward-unlocks on number-line placement (judging where a number sits and which
    # way its sign points is the readiness for the signed combination).
    _KC.INTEGER_ADD_SUBTRACT: frozenset({_KC.NUMBER_LINE_PLACEMENT}),
    # Grade-6 Unit 3: a signed number is a point on the number line and its opposite is the
    # reflection across zero, so opposites build on placing a number on the line.
    _KC.SIGNED_NUMBERS: frozenset({_KC.NUMBER_LINE_PLACEMENT}),
    # Grade-6 Unit 4: writing an expression rests on the idea that a variable STANDS FOR a number,
    # so it forward-unlocks on number-line placement (a number is a point) — the live foundation
    # KC the algebra skill conceptually rests on (its own §11 prereqs are not yet live).
    _KC.WRITE_EXPRESSIONS: frozenset({_KC.NUMBER_LINE_PLACEMENT}),
    # Grade-6 Unit 4: evaluating an expression substitutes a value into one you can already read,
    # so it forward-unlocks on writing expressions (the live Unit-4 skill it directly builds on).
    # Its REMEDIATION_ROUTING drop is to KC_exponents (not yet live), so the forward edge uses the
    # live Unit-4 KC the skill conceptually rests on — mirroring the WRITE_EXPRESSIONS pattern.
    _KC.EVALUATE_EXPRESSIONS: frozenset({_KC.WRITE_EXPRESSIONS}),
    # Grade-6 Unit 5: solving x + b = c / a*x = c rests on the variable STANDING FOR a number (a
    # point on the line) and on judging the size of that number, so it forward-unlocks on
    # number-line placement — the live foundation KC the algebra skill conceptually rests on,
    # matching how KC_write_expressions is wired. (Edge could later tighten to EVALUATE_EXPRESSIONS,
    # now live and its §11 reactive-drop prereq — left as a follow-up to avoid a mid-merge rewire.)
    _KC.ONE_STEP_EQUATIONS: frozenset({_KC.NUMBER_LINE_PLACEMENT}),
    # Grade-6 Unit 4: rewriting an expression as an equivalent one (distribute, combine like terms)
    # rests on being able to read/write an algebraic expression in the first place, so it unlocks
    # on KC_write_expressions — the live prerequisite directly upstream of it.
    _KC.EQUIVALENT_EXPRESSIONS: frozenset({_KC.WRITE_EXPRESSIONS}),
    # Grade-6 Unit 5: writing an inequality from a constraint rests on first being able to write an
    # algebraic relation with a variable, so it unlocks on KC_write_expressions — the live
    # prerequisite directly upstream (its own §11 prereqs, e.g. KC_ordering_inequalities, are not
    # yet live).
    _KC.INEQUALITIES: frozenset({_KC.WRITE_EXPRESSIONS}),
    # Grade-6 Unit 3: a point in the coordinate plane is two signed numbers, each a position on an
    # axis — the number line generalized to two dimensions — so plotting points forward-unlocks on
    # number-line placement (judging where a signed number sits on a line is the readiness for
    # locating it along each axis). The live foundation KC the skill conceptually rests on.
    _KC.COORDINATE_PLANE: frozenset({_KC.NUMBER_LINE_PLACEMENT}),
    # Grade-6 Unit 3 (TEKS 6.2A): classifying a value into the number sets (whole/integer/rational)
    # rests on understanding signed numbers — knowing 5 vs -3 is what distinguishes whole from
    # integer — so it forward-unlocks on KC_signed_numbers, the live Unit-3 KC directly upstream.
    # (Matches its REMEDIATION_ROUTING drop, which is also SIGNED_NUMBERS — both point at the same
    # live prerequisite.)
    _KC.CLASSIFY_NUMBER_SETS: frozenset({_KC.SIGNED_NUMBERS}),
    # Grade-6 Unit 4: naming the parts of an expression (coefficient/constant/terms) rests on being
    # able to read/write an algebraic expression in the first place, so it forward-unlocks on
    # KC_write_expressions — the live Unit-4 prerequisite directly upstream (matching how the other
    # Unit-4 KCs, EVALUATE_EXPRESSIONS and EQUIVALENT_EXPRESSIONS, are wired).
    _KC.EXPRESSION_PARTS: frozenset({_KC.WRITE_EXPRESSIONS}),
    # Grade-6 Unit 4: evaluating a whole-number power produces a NUMBER whose magnitude you read
    # (powers grow fast), so it forward-unlocks on number-line placement — the live foundation KC
    # the skill conceptually rests on (matching how the other Unit-4 KCs are wired; its own §11
    # reactive-drop is the EVALUATE_EXPRESSIONS pairing, kept separate from this forward edge).
    _KC.EXPONENTS: frozenset({_KC.NUMBER_LINE_PLACEMENT}),
    # Grade-6 Unit-INT (TEKS 6.3C/D): multiplying/dividing integers extends signed addition (a
    # product is repeated signed addition; division undoes it), so it forward-unlocks on
    # KC_integer_add_subtract — the live Unit-INT KC directly upstream (matching its
    # REMEDIATION_ROUTING drop, also INTEGER_ADD_SUBTRACT).
    _KC.INTEGER_MULTIPLY_DIVIDE: frozenset({_KC.INTEGER_ADD_SUBTRACT}),
    # Grade-6 Unit 6 (TEKS 6.8A): a missing angle or a triangle's area is a NUMBER (a measure) you
    # compute and read the size of, so triangle properties forward-unlocks on number-line
    # placement — the live foundation KC the geometry skill rests on (its own §11 geometry prereqs
    # are not yet live, matching how the other late-unit KCs are wired to the foundation).
    _KC.TRIANGLE_PROPERTIES: frozenset({_KC.NUMBER_LINE_PLACEMENT}),
    # Grade-6 Unit 6: finding a polygon's area is EVALUATING a formula (1/2·b·h or b·h) at the given
    # side lengths, so it forward-unlocks on KC_evaluate_expressions — the live KC directly upstream
    # (matching its REMEDIATION_ROUTING drop, also EVALUATE_EXPRESSIONS).
    _KC.AREA_POLYGONS: frozenset({_KC.EVALUATE_EXPRESSIONS}),
    # Grade-6 Unit 6 (6.G.2): the volume of a prism with fractional edges IS a product of fractions
    # (V = l*w*h), so it forward-unlocks on KC_multiply_fractions — the live Unit-2 skill the
    # geometry directly builds on (matching its REMEDIATION_ROUTING drop, also MULTIPLY_FRACTIONS).
    _KC.VOLUME_FRACTIONAL_EDGES: frozenset({_KC.MULTIPLY_FRACTIONS}),
    # Grade-6 Unit 6 (6.G.3): drawing polygons in the plane and finding a missing rectangle corner
    # IS plotting/reading integer points — it directly extends plotting single points — so it
    # forward-unlocks on KC_coordinate_plane (6.NS.8), the live coordinate KC it builds on (matching
    # its REMEDIATION_ROUTING drop, also COORDINATE_PLANE).
    _KC.POLYGONS_COORDINATE_PLANE: frozenset({_KC.COORDINATE_PLANE}),
    # Grade-6 Unit 6 (6.G.4): a prism's surface area is the SUM of its six faces' areas, and each
    # face is a polygon (a rectangle) whose area is found exactly as in KC_area_polygons, so surface
    # area from a net forward-unlocks on polygon area — the live geometry skill directly upstream.
    _KC.SURFACE_AREA_NETS: frozenset({_KC.AREA_POLYGONS}),
    # Grade-6 Unit 7 (6.SP.5c): the mean absolute deviation averages the DISTANCES of the data
    # values from the mean — each deviation is an absolute value (a distance from a point), exactly
    # the idea KC_absolute_value teaches — so MAD forward-unlocks on KC_absolute_value, the live
    # Unit-3 KC it conceptually rests on (its own §11 statistics prereqs are not yet live).
    _KC.MEAN_ABSOLUTE_DEVIATION: frozenset({_KC.ABSOLUTE_VALUE}),
    # Grade-6 Unit 7 (6.SP.2): describing a distribution by center/spread rests on ordering the data
    # by size and reading positions and distances along a number line — the median is the middle
    # position, the range and IQR are distances between positions — so it forward-unlocks on
    # number-line placement, the live foundation KC the statistics skill conceptually rests on (its
    # own §11 statistics prereqs are not yet live, matching how the other late-unit KCs are wired).
    _KC.CENTER_SPREAD_SHAPE: frozenset({_KC.NUMBER_LINE_PLACEMENT}),
    # Grade-6 Unit 7 (6.SP.3): a data set's mean is total ÷ count — whole-number division — so
    # summary statistics forward-unlocks on KC_multi_digit_division, the live arithmetic skill it
    # directly builds on (the other statistics — median/mode/range — need only ordering/comparison,
    # already in hand).
    _KC.SUMMARY_STATISTICS: frozenset({_KC.MULTI_DIGIT_DIVISION}),
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
    _KC.DIVIDE_FRACTIONS,  # Grade-6 Unit 2: divide fractions (invert & multiply), on multiplication
    _KC.UNIT_CONVERSION,  # Grade-6 Unit 1: convert via proportions, built on the unit rate
    _KC.GCF_LCM,  # Grade-6 Unit 2: GCF/LCM, generalizes the common denominator (LCM = LCD)
    _KC.MULTI_DIGIT_DIVISION,  # Grade-6 Unit 2: whole-number division, on number-line placement
    _KC.DECIMAL_OPERATIONS,  # Grade-6 Unit 2: multiply decimals, built on equivalence
    _KC.ABSOLUTE_VALUE,  # Grade-6 Unit 3: distance from 0, on number-line placement
    _KC.INTEGER_ADD_SUBTRACT,  # Grade-6 Unit-INT: signed add/subtract, on number-line placement
    _KC.SIGNED_NUMBERS,  # Grade-6 Unit 3: opposites, the reflection across zero on the number line
    _KC.WRITE_EXPRESSIONS,  # Grade-6 Unit 4: write expressions, on number-line placement
    _KC.EVALUATE_EXPRESSIONS,  # Grade-6 Unit 4: evaluate at a value, builds on writing expressions
    _KC.ONE_STEP_EQUATIONS,  # Grade-6 Unit 5: solve one-step equations, on number-line placement
    _KC.EQUIVALENT_EXPRESSIONS,  # Grade-6 Unit 4: rewrite as equivalent, on write expressions
    _KC.INEQUALITIES,  # Grade-6 Unit 5: write inequalities, on write expressions
    _KC.COORDINATE_PLANE,  # Grade-6 Unit 3: plot points in the plane, on number-line placement
    _KC.CLASSIFY_NUMBER_SETS,  # Grade-6 Unit 3 (TEKS 6.2A): classify number sets, on signed numbers
    _KC.EXPRESSION_PARTS,  # Grade-6 Unit 4: name parts of an expression, on write expressions
    _KC.EXPONENTS,  # Grade-6 Unit 4: evaluate whole-number powers, on number-line placement
    _KC.INTEGER_MULTIPLY_DIVIDE,  # Grade-6 Unit-INT: multiply/divide integers, on signed add/sub
    _KC.TRIANGLE_PROPERTIES,  # Grade-6 Unit 6 (TEKS 6.8A): triangle properties, on number-line
    _KC.AREA_POLYGONS,  # Grade-6 Unit 6: area of polygons, evaluating a formula (on evaluate-expr)
    _KC.VOLUME_FRACTIONAL_EDGES,  # Grade-6 Unit 6 (6.G.2): prism volume V=l*w*h, on multiply frac
    _KC.POLYGONS_COORDINATE_PLANE,  # Grade-6 Unit 6 (6.G.3): polygons in the plane, on coord-plane
    _KC.SURFACE_AREA_NETS,  # Grade-6 Unit 6 (6.G.4): surface area from a net, on polygon area
    _KC.MEAN_ABSOLUTE_DEVIATION,  # Grade-6 Unit 7 (6.SP.5c): MAD, on absolute value (distances)
    _KC.CENTER_SPREAD_SHAPE,  # Grade-6 Unit 7 (6.SP.2): center & spread, on number-line placement
    _KC.SUMMARY_STATISTICS,  # Grade-6 Unit 7 (6.SP.3): a data set's summary statistic, on division
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
