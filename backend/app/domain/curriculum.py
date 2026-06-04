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
    # True ONLY for lessons we deliberately decided NOT to build as interactive
    # tutor lessons — pure-concept TEKS items with no SymPy/tutor mechanism
    # (DEC.FINLIT: the four non-arithmetic Unit-8 financial-literacy lessons).
    # These are honestly "concept lessons" the surface labels as such, NOT
    # "coming soon" (which would imply a tutor lesson is on the way). It is the
    # SETTLED counterpart to ``playable``: ``playable=False`` says the tutor
    # can't serve this lesson today; ``concept_only=True`` says it never will,
    # by owner decision — so the surface must not promise a build. Defaults
    # False; a genuinely-unbuilt-but-planned lesson (e.g. an interleave gate, a
    # forward-declared Wave-3 KC) leaves it False and keeps "coming soon".
    concept_only: bool = False


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
    description="Write ratios, find unit rates, and use percents to compare amounts.",
    lessons=(
        CatalogLesson(
            slug="u1_l1",
            unit_slug="u1",
            # Aligned to the enum/model label-space id ``KC_ratio_language`` (was the stray
            # ``KC_ratio_meaning``, which matched no KnowledgeComponentId member and so could
            # never resolve or be built — Grade-6 build, 2026-05-30).
            order=1,
            title="What is a ratio?",
            kc_id="KC_ratio_language",
            ccss_code="6.RP.1",
            teks_code="6.4A",
            description="Describe how two amounts compare, and tell a ratio from a count.",
        ),
        CatalogLesson(
            slug="u1_l2",
            unit_slug="u1",
            order=2,
            title="Equivalent ratios",
            kc_id="KC_equivalent_ratios",
            ccss_code="6.RP.3a",
            teks_code="6.5A",
            description="Fill in ratio tables and find ratios equal to a given one.",
        ),
        CatalogLesson(
            slug="u1_l3",
            unit_slug="u1",
            order=3,
            title="Unit rates",
            kc_id="KC_unit_rate",
            ccss_code="6.RP.2",
            teks_code="6.4D",
            description="Find the rate for one — like the better buy at the store.",
        ),
        CatalogLesson(
            slug="u1_l4",
            unit_slug="u1",
            order=4,
            title="Rate problems",
            kc_id="KC_unit_rate",  # reuses KC_unit_rate (CURRICULUM_STANDARD.md §3)
            ccss_code="6.RP.3b",
            teks_code="6.4B",
            description="Use rates to solve speed, price, and other real-world problems.",
        ),
        CatalogLesson(
            slug="u1_l5",
            unit_slug="u1",
            order=5,
            title="Percents",
            kc_id="KC_percent",
            ccss_code="6.RP.3c",
            teks_code="6.4E",
            description="Find a percent of an amount, and the whole from a part.",
        ),
        # TEKS-only: unit conversion via proportions (6.4H). CCSS has only a
        # partial 6.RP.3d analogue, so this is encoded CCSS-None.
        CatalogLesson(
            slug="u1_l6",
            unit_slug="u1",
            order=6,
            title="Converting units",
            kc_id="KC_unit_conversion",
            ccss_code=None,
            teks_code="6.4H",
            description="Change between units like feet and inches using proportions.",
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
    description="Add, subtract, multiply, and divide fractions and decimals fluently.",
    lessons=(
        # Foundations warm-up — folds the existing KC_equivalence (built).
        CatalogLesson(
            slug="u2_l0",
            unit_slug="u2",
            order=1,
            title="Equivalent fractions",
            kc_id="KC_equivalence",
            ccss_code="3.NF",  # below-grade prereq the spec tags 3.NF/4.NF
            teks_code="6.2E",
            description="Warm up by finding fractions that name the same amount.",
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
            description="Add and subtract fractions with different denominators.",
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
            description="Find the greatest common factor and least common multiple.",
        ),
        CatalogLesson(
            slug="u2_l3",
            unit_slug="u2",
            order=4,
            title="Divide fractions",
            # Aligned to the enum/model label-space id ``KC_divide_fractions`` (was the stray
            # ``KC_fraction_division``, which matched no KnowledgeComponentId member and so could
            # never resolve or be built — Grade-6 build, 2026-05-30).
            kc_id="KC_divide_fractions",
            ccss_code="6.NS.1",
            teks_code="6.3A",
            description="Divide one fraction by another and see what it means.",
        ),
        CatalogLesson(
            slug="u2_l4",
            unit_slug="u2",
            order=5,
            title="Multiply fractions",
            kc_id="KC_multiply_fractions",  # built KC id (knowledge_components.py LIVE_KCS)
            # Fraction multiplication is CCSS 5.NF.4 (Grade 5), NOT 6.NS.1 — that
            # code is fraction DIVISION (u2_l3 above). Texas places it in Grade 6
            # (TEKS 6.3B), so this lesson is TEKS-only with no Grade-6 CCSS code,
            # exactly like the integer unit's CCSS gap. (Was "6.NS.1 # spec 6.NS.1-adj";
            # corrected per the panel standards audit, 2026-06-04.)
            ccss_code=None,
            teks_code="6.3B",
            description="Multiply fractions and decide if the answer grows or shrinks.",
        ),
        CatalogLesson(
            slug="u2_l5",
            unit_slug="u2",
            order=6,
            title="Long division",
            # Aligned to the enum/model id ``KC_multi_digit_division`` (was the stray
            # ``KC_long_division``, which matched no KnowledgeComponentId member and so could
            # never resolve or be built — Grade-6 build, 2026-05-30).
            kc_id="KC_multi_digit_division",
            ccss_code="6.NS.2",
            teks_code=None,  # spec tags TEKS side "(computation)" — no own code
            description="Divide large whole numbers using long division.",
        ),
        CatalogLesson(
            slug="u2_l6",
            unit_slug="u2",
            # Aligned to the enum/model label-space id ``KC_decimal_operations`` (was the stray
            # ``KC_decimal_ops``, which matched no KnowledgeComponentId member and so could never
            # resolve or be built — Grade-6 build, 2026-05-30).
            order=7,
            title="Decimal operations",
            kc_id="KC_decimal_operations",
            ccss_code="6.NS.3",
            teks_code="6.3E",
            description="Add, subtract, multiply, and divide decimals.",
        ),
        CatalogLesson(
            slug="u2_l7",
            unit_slug="u2",
            order=8,
            title="Mixed practice",
            kc_id=None,  # interleave gate — no single KC
            ccss_code="6.NS.1",  # spec: "6.NS.1-4"
            teks_code="6.3",
            description="Mix every skill from this unit and finish with a challenge.",
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
    description="Place positive and negative numbers on the number line and order them.",
    lessons=(
        CatalogLesson(
            slug="u3_l1",
            unit_slug="u3",
            order=1,
            title="Positive & negative numbers",
            kc_id="KC_signed_numbers",
            ccss_code="6.NS.5",
            teks_code="6.2B",
            description="Use signed numbers for opposites like up and down or hot and cold.",
        ),
        CatalogLesson(
            slug="u3_l2",
            unit_slug="u3",
            order=2,
            title="Numbers on the number line",
            kc_id="KC_number_line_placement",  # reuses the existing built KC
            ccss_code="6.NS.6",
            teks_code="6.2C",
            description="Place positive and negative numbers and their opposites on a line.",
        ),
        CatalogLesson(
            slug="u3_l3",
            unit_slug="u3",
            order=3,
            title="Ordering numbers",
            kc_id="KC_number_line_placement",  # reuses number-line compare
            ccss_code="6.NS.7a",
            teks_code="6.2C",
            description="Compare and order positive and negative numbers.",
        ),
        CatalogLesson(
            slug="u3_l4",
            unit_slug="u3",
            order=4,
            title="Absolute value",
            kc_id="KC_absolute_value",
            ccss_code="6.NS.7c",
            teks_code="6.2B",
            description="Measure how far a number is from zero.",
        ),
        # TEKS-only: classify number sets / Venn (6.2A). CCSS is only implicit.
        CatalogLesson(
            slug="u3_l5",
            unit_slug="u3",
            order=5,
            title="Sorting number types",
            kc_id="KC_classify_number_sets",
            ccss_code=None,
            teks_code="6.2A",
            description="Sort numbers into whole numbers, integers, and rationals.",
        ),
        CatalogLesson(
            slug="u3_l6",
            unit_slug="u3",
            order=6,
            title="The coordinate plane",
            kc_id="KC_coordinate_plane",
            ccss_code="6.NS.8",
            teks_code="6.11A",
            description="Plot points in all four quadrants and reflect them across the axes.",
        ),
        CatalogLesson(
            slug="u3_l7",
            unit_slug="u3",
            order=7,
            title="Mixed practice",
            kc_id=None,  # interleave gate
            ccss_code="6.NS.5",  # spec: "6.NS.5-8"
            teks_code="6.2",
            description="Mix every skill from this unit and finish with a challenge.",
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
    description="Work all four operations with positive and negative numbers.",
    lessons=(
        CatalogLesson(
            slug="uint_l1",
            unit_slug="uint",
            order=1,
            title="Adding & subtracting integers",
            # Aligned to the enum/model label-space id ``KC_integer_add_subtract`` (was the stray
            # ``KC_integer_add_sub``, which matched no KnowledgeComponentId member and so could
            # never resolve or be built — Grade-6 build, 2026-05-30).
            kc_id="KC_integer_add_subtract",
            ccss_code=None,
            teks_code="6.3C",
            description="Add and subtract positive and negative numbers using models.",
        ),
        CatalogLesson(
            slug="uint_l2",
            unit_slug="uint",
            order=2,
            title="Integer fluency",
            kc_id="KC_integer_add_subtract",  # reuses the models lesson's KC (uint_l1)
            ccss_code=None,
            teks_code="6.3D",
            description="Add and subtract integers quickly, without the models.",
        ),
        CatalogLesson(
            slug="uint_l3",
            unit_slug="uint",
            order=3,
            title="Multiplying & dividing integers",
            # Aligned to the enum/model label-space id ``KC_integer_multiply_divide`` (was the
            # stray ``KC_integer_mul_div``, which matched no KnowledgeComponentId member and so
            # could never resolve or be built — Grade-6 build, 2026-05-30, mirrors the uint_l1 fix).
            kc_id="KC_integer_multiply_divide",
            ccss_code=None,
            teks_code="6.3C",  # spec: 6.3C/6.3D
            description="Use the sign rules to multiply and divide integers.",
        ),
        CatalogLesson(
            slug="uint_l4",
            unit_slug="uint",
            order=4,
            title="Mixed practice",
            kc_id=None,  # interleave gate
            ccss_code=None,
            teks_code="6.3D",  # spec: 6.3C/6.3D
            description="Mix every skill from this unit and finish with a challenge.",
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
    description="Use exponents and variables to write and build expressions.",
    lessons=(
        CatalogLesson(
            slug="u4_l1",
            unit_slug="u4",
            order=1,
            title="Exponents & order of operations",
            kc_id="KC_exponents",
            ccss_code="6.EE.1",
            teks_code="6.7A",
            description="Use exponents and follow the order of operations.",
        ),
        CatalogLesson(
            slug="u4_l2",
            unit_slug="u4",
            order=2,
            title="Variables & expressions",
            kc_id="KC_write_expressions",
            ccss_code="6.EE.2a",
            teks_code="6.7B",
            description="Use letters for unknown numbers and write expressions from words.",
        ),
        CatalogLesson(
            slug="u4_l3",
            unit_slug="u4",
            order=3,
            title="Parts of an expression",
            kc_id="KC_expression_parts",
            ccss_code="6.EE.2b",
            teks_code="6.7B",
            description="Name the terms, coefficients, and factors in an expression.",
        ),
        CatalogLesson(
            slug="u4_l4",
            unit_slug="u4",
            order=4,
            title="Evaluate expressions",
            kc_id="KC_evaluate_expressions",
            ccss_code="6.EE.2c",
            teks_code="6.7A",
            description="Plug in values to find what an expression equals.",
        ),
        CatalogLesson(
            slug="u4_l5",
            unit_slug="u4",
            order=5,
            title="Equivalent expressions",
            kc_id="KC_equivalent_expressions",
            ccss_code="6.EE.3",
            teks_code="6.7C",
            description="Use properties to write expressions that mean the same thing.",
        ),
        CatalogLesson(
            slug="u4_l6",
            unit_slug="u4",
            order=6,
            title="Independent & dependent variables",
            kc_id="KC_dependent_vars",
            ccss_code="6.EE.9",
            teks_code="6.6A",
            description="See how one quantity changes as another one changes.",
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
    description="Solve one-step equations and graph inequalities on a number line.",
    lessons=(
        CatalogLesson(
            slug="u5_l1",
            unit_slug="u5",
            order=1,
            title="What is a solution?",
            # Repointed 2026-05-31: the stale forward-declared id KC_test_solution is now the BUILT
            # KC_equation_solutions (6.EE.5 — test a value by substitution; the YES/NO solution
            # test + the scalar solve, masterable). This lesson goes live with that KC.
            kc_id="KC_equation_solutions",
            ccss_code="6.EE.5",
            teks_code="6.10B",
            description="Test which value makes an equation or inequality true.",
        ),
        CatalogLesson(
            slug="u5_l2",
            unit_slug="u5",
            order=2,
            title="One-step equations: + and −",
            # Reconciled 2026-05-30: the stale split ids KC_one_step_add / KC_one_step_mul are now
            # ONE built KC (KC_one_step_equations) covering BOTH additive (x + b = c) and
            # multiplicative (a*x = c) equations behind an operand-mode flag (6.EE.7). Both U5
            # lessons point at it; the generator's mode flag distinguishes the two equation types.
            kc_id="KC_one_step_equations",
            ccss_code="6.EE.7",
            teks_code="6.9A",
            description="Solve equations like x + 7 = 12.",
        ),
        CatalogLesson(
            slug="u5_l3",
            unit_slug="u5",
            order=3,
            title="One-step equations: × and ÷",
            kc_id="KC_one_step_equations",  # reconciled: same KC as u5_l2 (see u5_l2 note)
            ccss_code="6.EE.7",
            teks_code="6.9A",
            description="Solve equations like 4x = 20.",
        ),
        CatalogLesson(
            slug="u5_l4",
            unit_slug="u5",
            order=4,
            title="Inequalities",
            kc_id="KC_inequalities",
            ccss_code="6.EE.8",
            teks_code="6.9A",
            description="Write, solve, and graph inequalities on a number line.",
        ),
        CatalogLesson(
            slug="u5_l5",
            unit_slug="u5",
            order=5,
            title="Two-variable relationships",
            kc_id="KC_dependent_vars",  # reuses from U4 L6
            ccss_code="6.EE.9",
            teks_code="6.6B",
            description="Connect an equation, a table, and a graph.",
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
    description="Find the area, surface area, and volume of triangles, polygons, and solids.",
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
            description="Explore the angles and side lengths of triangles.",
        ),
        CatalogLesson(
            slug="u6_l2",
            unit_slug="u6",
            order=2,
            title="Area of triangles",
            kc_id="KC_area_polygons",
            ccss_code="6.G.1",
            teks_code="6.8B",
            description="Find a triangle's area with A = 1/2 x base x height.",
        ),
        CatalogLesson(
            slug="u6_l3",
            unit_slug="u6",
            order=3,
            title="Area of polygons",
            kc_id="KC_area_polygons",
            ccss_code="6.G.1",
            teks_code="6.8B",
            description="Find the area of parallelograms, trapezoids, and combined shapes.",
        ),
        CatalogLesson(
            slug="u6_l4",
            unit_slug="u6",
            order=4,
            title="Volume",
            kc_id="KC_volume_fractional_edges",
            ccss_code="6.G.2",
            teks_code="6.8C",
            description="Find volume with whole and fractional edge lengths.",
        ),
        # CCSS-only: polygons on the coordinate plane (6.G.3). TEKS not explicit.
        CatalogLesson(
            slug="u6_l5",
            unit_slug="u6",
            order=5,
            title="Polygons on the grid",
            kc_id="KC_polygons_coordinate_plane",
            ccss_code="6.G.3",
            teks_code=None,
            description="Find side lengths of shapes drawn on the coordinate plane.",
        ),
        # CCSS-only: surface area from nets (6.G.4). Not in TEKS 6.8.
        CatalogLesson(
            slug="u6_l6",
            unit_slug="u6",
            order=6,
            title="Surface area from nets",
            kc_id="KC_surface_area_nets",
            ccss_code="6.G.4",
            teks_code=None,
            description="Unfold solids into nets to find total surface area.",
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
    description="Collect data, make graphs, and describe its center, spread, and shape.",
    lessons=(
        CatalogLesson(
            slug="u7_l1",
            unit_slug="u7",
            order=1,
            title="Statistical questions",
            kc_id="KC_statistical_questions",
            ccss_code="6.SP.1",
            teks_code="6.13B",
            description="Spot questions whose answers vary from person to person.",
        ),
        CatalogLesson(
            slug="u7_l2",
            unit_slug="u7",
            order=2,
            title="Data displays",
            kc_id="KC_data_displays",
            ccss_code="6.SP.4",
            teks_code="6.12A",
            description="Read and make dot plots, histograms, and box plots.",
        ),
        CatalogLesson(
            slug="u7_l3",
            unit_slug="u7",
            order=3,
            title="Center, spread & shape",
            kc_id="KC_center_spread_shape",
            ccss_code="6.SP.2",
            teks_code="6.12B",
            description="Describe the overall shape of a data set from its graph.",
        ),
        CatalogLesson(
            slug="u7_l4",
            unit_slug="u7",
            order=4,
            title="Mean, median & range",
            kc_id="KC_summary_statistics",
            ccss_code="6.SP.3",
            teks_code="6.12C",
            description="Find the center and spread of a data set.",
        ),
        # CCSS-only: mean absolute deviation (6.SP.5c). Not emphasized in TEKS.
        CatalogLesson(
            slug="u7_l5",
            unit_slug="u7",
            order=5,
            title="Mean absolute deviation",
            kc_id="KC_mean_absolute_deviation",
            ccss_code="6.SP.5c",
            teks_code=None,
            description="Measure how far data spreads from the mean.",
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
            description="Summarize categories with tables and percent bar graphs.",
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
    description="Build real money skills, from check registers to planning lifetime income.",
    lessons=(
        CatalogLesson(
            slug="u8_l1",
            unit_slug="u8",
            order=1,
            title="Checking accounts",
            kc_id="KC_banking",
            ccss_code=None,
            teks_code="6.14A",
            description="Learn how checking accounts and debit cards work.",
            # Pure-concept TEKS item, no SymPy/tutor mechanism — DEC.FINLIT
            # decision to stub (not build) this as a concept lesson.
            concept_only=True,
        ),
        CatalogLesson(
            slug="u8_l2",
            unit_slug="u8",
            order=2,
            title="Debit vs. credit",
            kc_id="KC_banking",  # reuses
            ccss_code=None,
            teks_code="6.14B",
            description="Compare paying with a debit card and a credit card.",
            concept_only=True,  # DEC.FINLIT concept lesson (no tutor mechanism)
        ),
        CatalogLesson(
            slug="u8_l3",
            unit_slug="u8",
            order=3,
            title="Balancing a check register",
            kc_id="KC_check_register",
            ccss_code=None,
            teks_code="6.14C",
            description="Keep a running balance as money comes in and goes out.",
        ),
        CatalogLesson(
            slug="u8_l4",
            unit_slug="u8",
            order=4,
            title="Credit history",
            kc_id="KC_credit",
            ccss_code=None,
            teks_code="6.14D",
            description="See why credit history matters and what a credit report shows.",
            concept_only=True,  # DEC.FINLIT concept lesson (no tutor mechanism)
        ),
        CatalogLesson(
            slug="u8_l5",
            unit_slug="u8",
            order=5,
            title="Paying for college",
            kc_id="KC_college_pay",
            ccss_code=None,
            teks_code="6.14G",
            description="Explore grants, scholarships, loans, and work-study.",
            concept_only=True,  # DEC.FINLIT concept lesson (no tutor mechanism)
        ),
        CatalogLesson(
            slug="u8_l6",
            unit_slug="u8",
            order=6,
            title="Salary & lifetime income",
            kc_id="KC_lifetime_income",
            ccss_code=None,
            teks_code="6.14H",
            description="Compare how your education level affects pay over a lifetime.",
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
