"""The Grade-6 curriculum catalog — the frozen, dual-tagged unit/lesson enumeration.

WHY this exists. The recurring blocker was "we had five skills but no
curriculum" (CURRICULUM_STANDARD.md §0). This module is the in-code source of
truth for the **dual-coverage Grade-6 scope and sequence**: 9 units → ~52
lessons, each tagged to BOTH a CCSS and a TEKS standard (or honestly marked
single-framework where only one applies). It is the data DAT.4 seeds into the
DB and DAT.6 bridges onto the course map; keeping the enumeration here — pure,
frozen, deterministic — means the DB, the API, and the teacher/learner views can
never disagree about *what the curriculum is* (mirrors why the KC registry lives
in one place, ARCHITECTURE.md §4).

SOURCE / AUTHORITY. The content is transcribed faithfully from the authoritative
spec: ``CURRICULUM_STANDARD.md`` §2–§7b (the narrative scope-and-sequence) and
the tracker's §FULL CONTENT list (its per-lesson mirror), with framework codes
cross-checked against ``TEKS_CCSS_COMPARISON.md`` §2–§3. Where the two agree,
this catalog follows them; the divergence notes are in this file's header
comments and the DAT.3 hand-off report. This module is NOT a claim that any
lesson is built (CURRICULUM_STANDARD.md §"What this document is NOT") — it is the
catalog of *what exists in the curriculum*, independent of engine readiness.

DUAL-COVERAGE INVARIANT. Every lesson carries at least one framework code. Most
carry both (the superset, so neither a national/CCSS nor a Texas/TEKS reviewer
sees a gap — DEC.SCOPE resolved, CURRICULUM_STANDARD.md §2.5). The honest
exceptions are encoded with the other field ``None``:
  * **TEKS-only** lessons (CCSS parks the topic in another grade or has no
    equivalent): the whole of **U-INT** (integer arithmetic, CCSS=7.NS) and
    **U8** (personal financial literacy, no CCSS strand), plus U1.L6 (unit
    conversion 6.4H), U3.L5 (classify sets 6.2A), U6.L1 (triangle properties
    6.8A), U7.L6 (categorical data 6.12D).
  * **CCSS-only** lessons kept for national coverage: U6.L5 (polygons on the
    plane 6.G.3), U6.L6 (surface area from nets 6.G.4), U7.L5 (MAD 6.SP.5c).
  * **U2.L1** (add/subtract fractions) is a below-grade *foundations review*
    lesson the spec lists as "prereq / prereq" on BOTH frameworks (it has no
    own Grade-6 code on either side — CURRICULUM_STANDARD.md §4, §1 table).
    Encoding it with both codes ``None`` would violate the dual-coverage
    invariant, so it is anchored to the 5.NF.A CCSS prereq it folds (TEKS-None)
    to keep it honestly single-tagged rather than code-less. See the comment at
    its definition.

HOW KC IDS ARE HANDLED (forward declaration). The catalog references many KC ids
that are NOT yet members of ``KnowledgeComponentId`` — only the five fraction KCs
exist today; the rest (KC_ratio_meaning, KC_unit_rate, KC_exponents, …) land
*per lesson* in Wave 3 when their generators/verifiers/misconceptions are built
(tracker §FULL CONTENT per-lesson checklist, step (a)+(j)). We deliberately do
NOT add those members to the enum here — that would be out of scope and break
other build lanes. So ``kc_id`` is stored as a plain ``str | None``: the catalog
string for a forward-declared KC, or ``None`` where a lesson reuses an existing
KC's slot or has no single KC yet (interleave gates). Only the five existing ids
resolve through ``get_kc``; the forward-declared ones are asserted well-formed
(``KC_`` prefix) by the tests until their enum members exist.

PURITY. Pure data + pure functions: no DB, no SymPy, no LLM (CLAUDE.md §7,
§8.1). All dataclasses are frozen (hashable, immutable) so nothing downstream can
rewrite what the curriculum *is* at runtime, the same discipline the KC registry
uses. The module-level index is built once at import and fails fast on a
duplicate slug.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogLesson:
    """One lesson in the Grade-6 catalog (the unit a learner runs end-to-end).

    Frozen because the catalog is a source of truth, not mutable state — and so
    the whole object is hashable. Every lesson must carry at least one of
    ``ccss_code`` / ``teks_code`` (the dual-coverage invariant); most carry both.
    ``kc_id`` is the catalog KC string (forward-declared for Wave-3 KCs) or
    ``None``; see the module docstring for why it is a plain ``str`` and not the
    ``KnowledgeComponentId`` enum.
    """

    slug: str
    unit_slug: str
    order: int
    title: str
    kc_id: str | None
    ccss_code: str | None
    teks_code: str | None
    description: str


@dataclass(frozen=True)
class CatalogUnit:
    """One unit: an ordered, named group of lessons with framework clusters.

    ``lessons`` is a tuple (not a list) so the unit is hashable and genuinely
    immutable. ``ccss_cluster`` / ``teks_cluster`` are the unit-level framework
    labels (e.g. "6.RP.A", "6.4 / 6.5"); a TEKS-only unit carries ``None`` for
    its CCSS cluster and vice versa.
    """

    slug: str
    title: str
    order: int
    ccss_cluster: str | None
    teks_cluster: str | None
    description: str
    lessons: tuple[CatalogLesson, ...]


# ===========================================================================
# THE CATALOG — transcribed from CURRICULUM_STANDARD.md §3–§7b + tracker §FULL
# CONTENT. Lesson descriptions paraphrase the "What the learner does" column.
# ===========================================================================


# --- U1 — Ratios & Rates (CCSS 6.RP.A · TEKS 6.4/6.5) ----------------------
_U1 = CatalogUnit(
    slug="u1",
    title="Ratios & Rates",
    order=1,
    ccss_cluster="6.RP.A",
    teks_cluster="6.4 / 6.5",
    description=(
        "Ratio language, equivalent ratios and tables, unit rate, rate problems, "
        "percent as a rate per 100, and (TEKS) unit conversion by proportion."
    ),
    lessons=(
        CatalogLesson(
            slug="u1_l1",
            unit_slug="u1",
            order=1,
            title="Ratio language",
            kc_id="KC_ratio_meaning",
            ccss_code="6.RP.1",
            teks_code="6.4A",
            description=(
                "Describe a relationship two ways and distinguish a ratio from a "
                "single count (part-to-part vs part-to-whole)."
            ),
        ),
        CatalogLesson(
            slug="u1_l2",
            unit_slug="u1",
            order=2,
            title="Equivalent ratios & tables",
            kc_id="KC_equivalent_ratios",
            ccss_code="6.RP.3a",
            teks_code="6.5A",
            description=(
                "Fill a ratio table and find missing equivalent ratios; "
                "multiplicative (not additive) thinking."
            ),
        ),
        CatalogLesson(
            slug="u1_l3",
            unit_slug="u1",
            order=3,
            title="Unit rate",
            kc_id="KC_unit_rate",
            ccss_code="6.RP.2",
            teks_code="6.4D",
            description="Find the unit rate for a ratio; 'which is the better buy?'.",
        ),
        CatalogLesson(
            slug="u1_l4",
            unit_slug="u1",
            order=4,
            title="Rate & ratio problems",
            kc_id="KC_unit_rate",  # reuses KC_unit_rate (CURRICULUM_STANDARD.md §3)
            ccss_code="6.RP.3b",
            teks_code="6.4B",
            description="Constant speed, unit pricing, rate reasoning (double number line).",
        ),
        CatalogLesson(
            slug="u1_l5",
            unit_slug="u1",
            order=5,
            title="Percent as rate per 100",
            kc_id="KC_percent",
            ccss_code="6.RP.3c",
            teks_code="6.4E",
            description=(
                "Find a percent of a quantity and the whole given a part and "
                "percent (all three unknowns); 10x10 grid."
            ),
        ),
        # TEKS-only: unit conversion via proportions (6.4H). CCSS has only a
        # partial 6.RP.3d analogue, so this is encoded CCSS-None.
        CatalogLesson(
            slug="u1_l6",
            unit_slug="u1",
            order=6,
            title="Unit conversion via proportions",
            kc_id="KC_unit_conversion",
            ccss_code=None,
            teks_code="6.4H",
            description=(
                "Convert customary and metric units by setting up a proportion / "
                "unit rate (TEKS-only)."
            ),
        ),
    ),
)


# --- U2 — Fractions & Decimals (CCSS 6.NS.1-4 · TEKS 6.2E/6.3) -------------
_U2 = CatalogUnit(
    slug="u2",
    title="Fractions & Decimals",
    order=2,
    ccss_cluster="6.NS.1-4",
    teks_cluster="6.2E / 6.3",
    description=(
        "The Number System pt.1: the folded foundations skills (equivalence, "
        "add/subtract, LCM upgraded from common-denominator), fraction "
        "division/multiplication, long division, decimals, and an interleave gate."
    ),
    lessons=(
        # Foundations warm-up — folds the existing KC_equivalence (built).
        CatalogLesson(
            slug="u2_l0",
            unit_slug="u2",
            order=1,
            title="Fraction foundations (warm-up)",
            kc_id="KC_equivalence",
            ccss_code="3.NF",  # below-grade prereq the spec tags 3.NF/4.NF
            teks_code="6.2E",
            description=(
                "Equivalent fractions, fast — folds the existing KC_equivalence "
                "skill; conceptual basis for 6.NS.1 division and 6.NS.4 LCM."
            ),
        ),
        # Add/subtract fractions — below-grade foundations review the spec tags
        # "5.NF.A (prereq) / (prereq)" with no Grade-6 code on EITHER framework.
        # The dual-coverage invariant forbids a code-less lesson, so it is
        # anchored to the 5.NF.A CCSS prereq it folds; TEKS-None (TEKS lists no
        # own code for this review beat). Single-framework by design.
        CatalogLesson(
            slug="u2_l1",
            unit_slug="u2",
            order=2,
            title="Add & subtract fractions",
            kc_id="KC_addition_unlike",
            ccss_code="5.NF.A",
            teks_code=None,
            description=(
                "Unlike-denominator add/subtract — folds the existing "
                "KC_addition_unlike + KC_subtraction_unlike review lesson; "
                "prerequisite for fraction division (below-grade foundations)."
            ),
        ),
        # GCF & LCM — upgrades the existing KC_common_denominator to its true
        # Grade-6 home (6.NS.4); TEKS folds factors into 6.7A.
        CatalogLesson(
            slug="u2_l2",
            unit_slug="u2",
            order=3,
            title="GCF & LCM",
            kc_id="KC_gcf_lcm",
            ccss_code="6.NS.4",
            teks_code="6.7A",
            description=(
                "Greatest common factor and least common multiple; distributive "
                "with GCF. Upgrades KC_common_denominator to 'find the LCM'."
            ),
        ),
        CatalogLesson(
            slug="u2_l3",
            unit_slug="u2",
            order=4,
            title="Divide a fraction by a fraction",
            kc_id="KC_fraction_division",
            ccss_code="6.NS.1",
            teks_code="6.3A",
            description=(
                "Interpret and compute a/b div c/d; the headline Grade-6 fraction "
                "standard (invert-wrong / multiply-across misconception)."
            ),
        ),
        CatalogLesson(
            slug="u2_l4",
            unit_slug="u2",
            order=5,
            title="Multiply fractions",
            kc_id="KC_fraction_multiplication",
            ccss_code="6.NS.1",  # spec: "6.NS.1-adj"
            teks_code="6.3B",
            description=(
                "Multiply fraction x fraction / x whole; reason whether the "
                "product grows or shrinks ('x always bigger' misconception)."
            ),
        ),
        CatalogLesson(
            slug="u2_l5",
            unit_slug="u2",
            order=6,
            title="Divide multi-digit numbers",
            kc_id="KC_long_division",
            ccss_code="6.NS.2",
            teks_code=None,  # spec tags TEKS side "(computation)" — no own code
            description="Fluent standard-algorithm long division (CCSS 6.NS.2).",
        ),
        CatalogLesson(
            slug="u2_l6",
            unit_slug="u2",
            order=7,
            title="Decimal operations",
            kc_id="KC_decimal_ops",
            ccss_code="6.NS.3",
            teks_code="6.3E",
            description="Add/subtract/multiply/divide multi-digit decimals fluently.",
        ),
        CatalogLesson(
            slug="u2_l7",
            unit_slug="u2",
            order=8,
            title="Mixed fraction/decimal fluency gate",
            kc_id=None,  # interleave gate — no single KC
            ccss_code="6.NS.1",  # spec: "6.NS.1-4"
            teks_code="6.3",
            description="Interleaved set across the unit ending in a transfer probe.",
        ),
    ),
)


# --- U3 — Rational Numbers (CCSS 6.NS.5-8 · TEKS 6.2/6.11) -----------------
_U3 = CatalogUnit(
    slug="u3",
    title="Rational Numbers",
    order=3,
    ccss_cluster="6.NS.5-8",
    teks_cluster="6.2 / 6.11",
    description=(
        "Home of the kept/expanded number-line skill: signed numbers, rationals "
        "on the line, ordering, absolute value, (TEKS) classify sets, the "
        "coordinate plane, and an interleave gate."
    ),
    lessons=(
        CatalogLesson(
            slug="u3_l1",
            unit_slug="u3",
            order=1,
            title="Positive & negative numbers",
            kc_id="KC_signed_numbers",
            ccss_code="6.NS.5",
            teks_code="6.2B",
            description="Signed numbers as opposite quantities (temperature, elevation, debt).",
        ),
        CatalogLesson(
            slug="u3_l2",
            unit_slug="u3",
            order=2,
            title="Rationals on the number line",
            kc_id="KC_number_line_placement",  # reuses the existing built KC
            ccss_code="6.NS.6",
            teks_code="6.2C",
            description=(
                "Place positives/negatives and opposites on a line; direct "
                "expansion of the existing KC_number_line_placement."
            ),
        ),
        CatalogLesson(
            slug="u3_l3",
            unit_slug="u3",
            order=3,
            title="Ordering & comparing rationals",
            kc_id="KC_number_line_placement",  # reuses number-line compare
            ccss_code="6.NS.7a",
            teks_code="6.2C",
            description=(
                "Order rationals; write/interpret -3 > -7 (negative-magnitude-bias misconception)."
            ),
        ),
        CatalogLesson(
            slug="u3_l4",
            unit_slug="u3",
            order=4,
            title="Absolute value",
            kc_id="KC_absolute_value",
            ccss_code="6.NS.7c",
            teks_code="6.2B",
            description=("Absolute value as distance from 0; distinguish |x| from order."),
        ),
        # TEKS-only: classify number sets / Venn (6.2A). CCSS is only implicit.
        CatalogLesson(
            slug="u3_l5",
            unit_slug="u3",
            order=5,
            title="Classify number sets (Venn)",
            kc_id="KC_classify_numbers",
            ccss_code=None,
            teks_code="6.2A",
            description=(
                "Sort numbers into whole subset integer subset rational; place a "
                "value in the right region (TEKS-only)."
            ),
        ),
        CatalogLesson(
            slug="u3_l6",
            unit_slug="u3",
            order=6,
            title="The coordinate plane",
            kc_id="KC_coordinate_plane",
            ccss_code="6.NS.8",
            teks_code="6.11A",
            description=(
                "Plot/identify points in four quadrants; reflections across axes; "
                "distance with a shared coordinate."
            ),
        ),
        CatalogLesson(
            slug="u3_l7",
            unit_slug="u3",
            order=7,
            title="Rational numbers gate",
            kc_id=None,  # interleave gate
            ccss_code="6.NS.5",  # spec: "6.NS.5-8"
            teks_code="6.2",
            description="Interleaved set across the unit ending in a transfer probe.",
        ),
    ),
)


# --- U-INT — Integer Arithmetic (TEKS 6.3C/6.3D ONLY; CCSS = 7.NS) ---------
# Whole TEKS-only unit: CCSS parks integer arithmetic in Grade 7 (7.NS), so
# every lesson is CCSS-None (CURRICULUM_STANDARD.md §5b).
_UINT = CatalogUnit(
    slug="uint",
    title="Integer Arithmetic",
    order=4,
    ccss_cluster=None,  # CCSS = 7.NS (Grade 7) — TEKS-only at Grade 6
    teks_cluster="6.3C / 6.3D",
    description=(
        "TEKS-only (CCSS holds to Grade 7/7.NS): add, subtract, multiply, divide "
        "integers with models then fluently; rides the built signed number line."
    ),
    lessons=(
        CatalogLesson(
            slug="uint_l1",
            unit_slug="uint",
            order=1,
            title="Integer add & subtract (models)",
            kc_id="KC_integer_add_sub",
            ccss_code=None,
            teks_code="6.3C",
            description=(
                "Add/subtract integers with two-color counters and number-line "
                "jumps; build the rule from the model (sign-handling misconception)."
            ),
        ),
        CatalogLesson(
            slug="uint_l2",
            unit_slug="uint",
            order=2,
            title="Integer add/subtract fluency",
            kc_id="KC_integer_add_sub",  # reuses
            ccss_code=None,
            teks_code="6.3D",
            description="Fluent signed add/subtract without the manipulative.",
        ),
        CatalogLesson(
            slug="uint_l3",
            unit_slug="uint",
            order=3,
            title="Integer multiply & divide",
            kc_id="KC_integer_mul_div",
            ccss_code=None,
            teks_code="6.3C",  # spec: 6.3C/6.3D
            description="Sign rules for x and div; products/quotients of integers.",
        ),
        CatalogLesson(
            slug="uint_l4",
            unit_slug="uint",
            order=4,
            title="Integer operations gate",
            kc_id=None,  # interleave gate
            ccss_code=None,
            teks_code="6.3D",  # spec: 6.3C/6.3D
            description="Interleaved set across the unit ending in a transfer probe.",
        ),
    ),
)


# --- U4 — Expressions (CCSS 6.EE.1-4 · TEKS 6.6/6.7) ----------------------
_U4 = CatalogUnit(
    slug="u4",
    title="Expressions",
    order=5,
    ccss_cluster="6.EE.1-4",
    teks_cluster="6.6 / 6.7",
    description=(
        "Best SymPy fit: exponents/order of ops, variables, parts of an "
        "expression, evaluation, equivalent expressions, and dependent variables."
    ),
    lessons=(
        CatalogLesson(
            slug="u4_l1",
            unit_slug="u4",
            order=1,
            title="Exponents & order of operations",
            kc_id="KC_exponents",
            ccss_code="6.EE.1",
            teks_code="6.7A",
            description="Write/evaluate numerical expressions with whole-number exponents.",
        ),
        CatalogLesson(
            slug="u4_l2",
            unit_slug="u4",
            order=2,
            title="Variables & expressions",
            kc_id="KC_write_expressions",
            ccss_code="6.EE.2a",
            teks_code="6.7B",
            description=(
                "Write expressions with variables from words; use a variable for an unknown."
            ),
        ),
        CatalogLesson(
            slug="u4_l3",
            unit_slug="u4",
            order=3,
            title="Parts of an expression",
            kc_id="KC_expression_parts",
            ccss_code="6.EE.2b",
            teks_code="6.7B",
            description="Identify term, coefficient, factor, sum/product (vocabulary).",
        ),
        CatalogLesson(
            slug="u4_l4",
            unit_slug="u4",
            order=4,
            title="Evaluate expressions",
            kc_id="KC_evaluate_expressions",
            ccss_code="6.EE.2c",
            teks_code="6.7A",
            description="Evaluate at given values (order of operations, formulas like V=s^3).",
        ),
        CatalogLesson(
            slug="u4_l5",
            unit_slug="u4",
            order=5,
            title="Equivalent expressions",
            kc_id="KC_equivalent_expressions",
            ccss_code="6.EE.3",
            teks_code="6.7C",
            description=(
                "Apply distributive/commutative properties; identify equivalent "
                "expressions (distributive-error misconception)."
            ),
        ),
        CatalogLesson(
            slug="u4_l6",
            unit_slug="u4",
            order=6,
            title="Independent & dependent variables",
            kc_id="KC_dependent_vars",
            ccss_code="6.EE.9",
            teks_code="6.6A",
            description=(
                "Relate two quantities as y=kx or y=x+b across verbal/table/graph/equation."
            ),
        ),
    ),
)


# --- U5 — Equations & Inequalities (CCSS 6.EE.5-9 · TEKS 6.9/6.10) ---------
_U5 = CatalogUnit(
    slug="u5",
    title="Equations & Inequalities",
    order=6,
    ccss_cluster="6.EE.5-9",
    teks_cluster="6.9 / 6.10",
    description=(
        "SymPy-native one-step solving: test a solution, one-step +/- and x/div "
        "equations, inequalities on a line, and two-variable relationships."
    ),
    lessons=(
        CatalogLesson(
            slug="u5_l1",
            unit_slug="u5",
            order=1,
            title="What is a solution?",
            kc_id="KC_test_solution",
            ccss_code="6.EE.5",
            teks_code="6.10B",
            description="Test which value makes an equation/inequality true.",
        ),
        CatalogLesson(
            slug="u5_l2",
            unit_slug="u5",
            order=2,
            title="One-step equations (+/-)",
            kc_id="KC_one_step_add",
            ccss_code="6.EE.7",
            teks_code="6.9A",
            description="Solve x + p = q over nonnegative rationals.",
        ),
        CatalogLesson(
            slug="u5_l3",
            unit_slug="u5",
            order=3,
            title="One-step equations (x/div)",
            kc_id="KC_one_step_mul",
            ccss_code="6.EE.7",
            teks_code="6.9A",
            description="Solve px = q.",
        ),
        CatalogLesson(
            slug="u5_l4",
            unit_slug="u5",
            order=4,
            title="Inequalities (write/solve/graph)",
            kc_id="KC_inequalities",
            ccss_code="6.EE.8",
            teks_code="6.9A",
            description="Write x > c / x < c and graph on a number line (reuses signed line).",
        ),
        CatalogLesson(
            slug="u5_l5",
            unit_slug="u5",
            order=5,
            title="Two-variable relationships",
            kc_id="KC_dependent_vars",  # reuses from U4 L6
            ccss_code="6.EE.9",
            teks_code="6.6B",
            description="Relate equation, table, and graph.",
        ),
    ),
)


# --- U6 — Geometry (CCSS 6.G.1-4 · TEKS 6.8) ------------------------------
_U6 = CatalogUnit(
    slug="u6",
    title="Geometry: Area, Surface Area, Volume",
    order=7,
    ccss_cluster="6.G.1-4",
    teks_cluster="6.8",
    description=(
        "Largest new build: (TEKS) triangle properties, area of triangles and "
        "quadrilaterals, volume with fractional edges, (CCSS) polygons on the "
        "plane and surface area from nets."
    ),
    lessons=(
        # TEKS-only: triangle properties (6.8A — angle sum / inequality, NOT
        # area; verified verbatim, Cornell LII §111.26). Not in CCSS Grade 6.
        CatalogLesson(
            slug="u6_l1",
            unit_slug="u6",
            order=1,
            title="Triangle properties",
            kc_id="KC_triangle_properties",
            ccss_code=None,
            teks_code="6.8A",
            description=(
                "Angle sum = 180; side-length to angle relationship; the triangle "
                "inequality (TEKS-only)."
            ),
        ),
        CatalogLesson(
            slug="u6_l2",
            unit_slug="u6",
            order=2,
            title="Area of triangles",
            kc_id="KC_area_triangle",
            ccss_code="6.G.1",
            teks_code="6.8B",
            description="Area via decomposing/composing; A = 1/2 b h.",
        ),
        CatalogLesson(
            slug="u6_l3",
            unit_slug="u6",
            order=3,
            title="Area of quadrilaterals & polygons",
            kc_id="KC_area_quad",
            ccss_code="6.G.1",
            teks_code="6.8B",
            description="Parallelograms, trapezoids, composite figures.",
        ),
        CatalogLesson(
            slug="u6_l4",
            unit_slug="u6",
            order=4,
            title="Volume with fractional edges",
            kc_id="KC_volume",
            ccss_code="6.G.2",
            teks_code="6.8C",
            description="V = lwh and V = Bh with fractional edge lengths.",
        ),
        # CCSS-only: polygons on the coordinate plane (6.G.3). TEKS not explicit.
        CatalogLesson(
            slug="u6_l5",
            unit_slug="u6",
            order=5,
            title="Polygons on the coordinate plane",
            kc_id="KC_polygons_plane",
            ccss_code="6.G.3",
            teks_code=None,
            description="Vertices and side lengths from coordinates (CCSS-only).",
        ),
        # CCSS-only: surface area from nets (6.G.4). Not in TEKS 6.8.
        CatalogLesson(
            slug="u6_l6",
            unit_slug="u6",
            order=6,
            title="Surface area from nets",
            kc_id="KC_surface_area",
            ccss_code="6.G.4",
            teks_code=None,
            description="Nets of prisms/pyramids; total surface area (CCSS-only).",
        ),
    ),
)


# --- U7 — Statistics (CCSS 6.SP.1-5 · TEKS 6.12/6.13) ---------------------
_U7 = CatalogUnit(
    slug="u7",
    title="Statistics",
    order=8,
    ccss_cluster="6.SP.1-5",
    teks_cluster="6.12 / 6.13",
    description=(
        "Statistical questions, data displays, center/spread/shape, numeric "
        "summaries, (CCSS) MAD, and (TEKS) categorical data / percent bar graph."
    ),
    lessons=(
        CatalogLesson(
            slug="u7_l1",
            unit_slug="u7",
            order=1,
            title="Statistical questions & variability",
            kc_id="KC_stat_questions",
            ccss_code="6.SP.1",
            teks_code="6.13B",
            description="Recognize questions that have variability; data with vs without it.",
        ),
        CatalogLesson(
            slug="u7_l2",
            unit_slug="u7",
            order=2,
            title="Data displays",
            kc_id="KC_data_displays",
            ccss_code="6.SP.4",
            teks_code="6.12A",
            description="Dot plots, histograms, box plots, stem-and-leaf.",
        ),
        CatalogLesson(
            slug="u7_l3",
            unit_slug="u7",
            order=3,
            title="Center, spread, shape",
            kc_id="KC_center_spread_shape",
            ccss_code="6.SP.2",
            teks_code="6.12B",
            description="Describe a distribution's overall shape from the graph.",
        ),
        CatalogLesson(
            slug="u7_l4",
            unit_slug="u7",
            order=4,
            title="Mean, median, range, IQR",
            kc_id="KC_center_measures",
            ccss_code="6.SP.3",
            teks_code="6.12C",
            description="Compute and choose center (mean/median) and spread (range/IQR).",
        ),
        # CCSS-only: mean absolute deviation (6.SP.5c). Not emphasized in TEKS.
        CatalogLesson(
            slug="u7_l5",
            unit_slug="u7",
            order=5,
            title="Mean absolute deviation (MAD)",
            kc_id="KC_mad",
            ccss_code="6.SP.5c",
            teks_code=None,
            description="Compute MAD; relate spread to center (CCSS-only).",
        ),
        # TEKS-only: categorical data / percent bar graph (6.12D). Not in 6.SP.
        CatalogLesson(
            slug="u7_l6",
            unit_slug="u7",
            order=6,
            title="Categorical data",
            kc_id="KC_categorical_data",
            ccss_code=None,
            teks_code="6.12D",
            description="Mode, relative-frequency table, percent bar graph (TEKS-only).",
        ),
    ),
)


# --- U8 — Personal Financial Literacy (TEKS 6.14A-H ONLY; no CCSS) ---------
# Whole TEKS-only strand CCSS has no equivalent of; every lesson CCSS-None
# (CURRICULUM_STANDARD.md §7b; DEC.FINLIT scope caveat).
_U8 = CatalogUnit(
    slug="u8",
    title="Personal Financial Literacy",
    order=9,
    ccss_cluster=None,  # no CCSS equivalent strand
    teks_cluster="6.14A-H",
    description=(
        "TEKS-only (DEC.FINLIT caveat): mostly curated-bank concept items; SymPy "
        "grades the two arithmetic lessons (check register, lifetime income)."
    ),
    lessons=(
        CatalogLesson(
            slug="u8_l1",
            unit_slug="u8",
            order=1,
            title="Checking accounts & debit cards",
            kc_id="KC_banking",
            ccss_code=None,
            teks_code="6.14A",
            description="Features/costs of a checking account vs a debit card.",
        ),
        CatalogLesson(
            slug="u8_l2",
            unit_slug="u8",
            order=2,
            title="Debit vs credit cards",
            kc_id="KC_banking",  # reuses
            ccss_code=None,
            teks_code="6.14B",
            description="Compare debit and credit card use.",
        ),
        CatalogLesson(
            slug="u8_l3",
            unit_slug="u8",
            order=3,
            title="Balance a check register",
            kc_id="KC_check_register",
            ccss_code=None,
            teks_code="6.14C",
            description="Keep a running balance across deposits/withdrawals (SymPy-graded).",
        ),
        CatalogLesson(
            slug="u8_l4",
            unit_slug="u8",
            order=4,
            title="Credit history & reports",
            kc_id="KC_credit",
            ccss_code=None,
            teks_code="6.14D",
            description="Why credit history matters; what is in a credit report.",
        ),
        CatalogLesson(
            slug="u8_l5",
            unit_slug="u8",
            order=5,
            title="Paying for college",
            kc_id="KC_college_pay",
            ccss_code=None,
            teks_code="6.14G",
            description="Grants/scholarships/loans/work-study.",
        ),
        CatalogLesson(
            slug="u8_l6",
            unit_slug="u8",
            order=6,
            title="Salary & lifetime income",
            kc_id="KC_income",
            ccss_code=None,
            teks_code="6.14H",
            description=(
                "Compare salaries by education level; lifetime-income effect (SymPy-graded)."
            ),
        ),
    ),
)


# The full curriculum, in the conventional Grade-6 teaching order (ratios, the
# number system, integers, algebra, geometry, statistics, financial literacy).
# Order here is the single source of truth for unit `order`.
CURRICULUM: tuple[CatalogUnit, ...] = (_U1, _U2, _U3, _UINT, _U4, _U5, _U6, _U7, _U8)


# ===========================================================================
# Registry / index — built once at import, fails fast on a duplicate slug
# (mirrors KnowledgeComponentRegistry's duplicate-id guard).
# ===========================================================================


def build_index(
    units: tuple[CatalogUnit, ...],
) -> tuple[dict[str, CatalogUnit], dict[str, CatalogLesson]]:
    """Build the by-slug indexes, raising on a duplicate unit or lesson slug.

    Exposed (not just inlined) so the duplicate-detection invariant can be
    tested directly with a synthetic duplicate, the way the KC registry's guard
    is. Raises ``ValueError`` naming the offending slug so a duplicate fails at
    import time rather than silently shadowing an earlier entry.
    """
    by_unit: dict[str, CatalogUnit] = {}
    by_lesson: dict[str, CatalogLesson] = {}
    for unit in units:
        if unit.slug in by_unit:
            raise ValueError(f"Duplicate unit slug: {unit.slug}")
        by_unit[unit.slug] = unit
        for lesson in unit.lessons:
            if lesson.slug in by_lesson:
                raise ValueError(f"Duplicate lesson slug: {lesson.slug}")
            by_lesson[lesson.slug] = lesson
    return by_unit, by_lesson


_BY_UNIT, _BY_LESSON = build_index(CURRICULUM)

# Public alias for the unit index (DAT.6 will bridge units onto the course map).
CURRICULUM_BY_UNIT: dict[str, CatalogUnit] = _BY_UNIT


def all_units() -> tuple[CatalogUnit, ...]:
    """Every unit, in the curriculum's declared (teaching) order."""
    return CURRICULUM


def get_unit(slug: str) -> CatalogUnit:
    """Resolve a unit by slug; raise ``KeyError`` naming the slug if unknown."""
    try:
        return _BY_UNIT[slug]
    except KeyError as exc:
        raise KeyError(f"Unknown curriculum unit slug: {slug!r}") from exc


def get_lesson(slug: str) -> CatalogLesson:
    """Resolve a lesson by slug; raise ``KeyError`` naming the slug if unknown."""
    try:
        return _BY_LESSON[slug]
    except KeyError as exc:
        raise KeyError(f"Unknown curriculum lesson slug: {slug!r}") from exc


def lessons_for_unit(slug: str) -> tuple[CatalogLesson, ...]:
    """The lessons of a unit, in order; raise ``KeyError`` if the unit is unknown."""
    return get_unit(slug).lessons


__all__ = [
    "CURRICULUM",
    "CURRICULUM_BY_UNIT",
    "CatalogLesson",
    "CatalogUnit",
    "all_units",
    "build_index",
    "get_lesson",
    "get_unit",
    "lessons_for_unit",
]
