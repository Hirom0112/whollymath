"""Layer-1 Knowledge Component registry — the canonical KC source of truth.

This is Slice 1.1 of the domain model (ARCHITECTURE.md §5 Layer 1; PROJECT.md
§4.1). The tightly-scoped goal (PROJECT.md §3.1) decomposes into exactly five
knowledge components — the unit of mastery. "Mastered fractions" is meaningless;
"mastered KC_equivalence" is trackable (ARCHITECTURE.md §4).

This module defines those five KCs deterministically: an identifier (matching
the locked `diagnostic_gems.json` `_meta.kc_catalog` verbatim), a human-readable
skill name and description, and the representations each KC can be exercised in.
Nothing here computes math or calls an LLM — SymPy lives only in the verifier
(Slice 1.4) and LLMs only in `llm/` (CLAUDE.md §7, §8.1/§8.2, ARCHITECTURE.md
§14). The KC objects are designed so that misconceptions (Slice 1.2), problem
generators (1.3) and the SymPy verifier (1.4) can later hang off them, but those
are intentionally NOT implemented here.

The mastery model, the persona harness, and the transfer test all reference
these same KC ids; keeping them in one registry is what makes that reference
unambiguous (PROJECT.md §4.1, ARCHITECTURE.md §4).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class KnowledgeComponentId(StrEnum):
    """Stable KC identifiers — the full Grade-6 ontology AND the HelpNeed model's label space.

    Two tiers (see the member groups below):
      - the five CONTENT-COMPLETE foundation skills, which have a full Layer-1 stack and match
        the `diagnostic_gems.json` `_meta.kc_catalog` verbatim (``LIVE_KCS`` / the registry); and
      - the Grade-6 ontology KCs (one per CURRICULUM_STANDARD.md §3–§7 lesson), added so the
        cross-topic HelpNeed one-hot (`KC_ORDER = tuple(KnowledgeComponentId)`) has a column per
        topic. These are label-space-only until their content is built — not in the registry, the
        gem catalog, or ``LIVE_KCS`` (T1_T2_COORDINATION.md §4).

    ``StrEnum`` makes a member compare equal to and serialize as its id string, so the gem bank,
    the DB (plain-string columns), and the API all speak the same id, with guaranteed-unique
    members and a typed handle. A content-complete KC's VALUE is the contract with the gem catalog
    and must not change without updating the catalog.
    """

    # ── The five CONTENT-COMPLETE foundation skills (PROJECT.md §3.1) ──
    # These have the full Layer-1 stack (registry metadata + generator + lesson spec + hints)
    # and are the set the tutor actually schedules today. ``LIVE_KCS`` (below) tracks them.
    EQUIVALENCE = "KC_equivalence"
    COMMON_DENOMINATOR = "KC_common_denominator"
    ADDITION_UNLIKE = "KC_addition_unlike"
    SUBTRACTION_UNLIKE = "KC_subtraction_unlike"
    NUMBER_LINE_PLACEMENT = "KC_number_line_placement"

    # ── The Grade-6 ontology (CURRICULUM_STANDARD.md §3–§7; one KC per lesson) ──
    # Added for the cross-topic HelpNeed model (T1_T2_COORDINATION.md §4): these are the
    # model's one-hot label space (``KC_ORDER``) and the curriculum ontology, but are NOT yet
    # content-complete — no generator/spec/hints, no registry entry, no gem-catalog entry —
    # so the tutor never schedules them and ``get_kc``/the content registries raise for them
    # until their content is built. Each enters ``LIVE_KCS`` the moment it gets a registry entry.
    # U1 — Ratios & Rates (6.RP)
    RATIO_LANGUAGE = "KC_ratio_language"
    EQUIVALENT_RATIOS = "KC_equivalent_ratios"
    UNIT_RATE = "KC_unit_rate"
    RATE_PROBLEMS = "KC_rate_problems"
    PERCENT = "KC_percent"
    UNIT_CONVERSION = "KC_unit_conversion"
    # U2 — Fractions & Decimals (6.NS.1–4)
    GCF_LCM = "KC_gcf_lcm"
    DIVIDE_FRACTIONS = "KC_divide_fractions"
    MULTIPLY_FRACTIONS = "KC_multiply_fractions"
    MULTI_DIGIT_DIVISION = "KC_multi_digit_division"
    DECIMAL_OPERATIONS = "KC_decimal_operations"
    # U3 — Rational Numbers (6.NS.5–8)
    SIGNED_NUMBERS = "KC_signed_numbers"
    RATIONALS_ON_LINE = "KC_rationals_on_line"
    ORDERING_INEQUALITIES = "KC_ordering_inequalities"
    ABSOLUTE_VALUE = "KC_absolute_value"
    CLASSIFY_NUMBER_SETS = "KC_classify_number_sets"
    COORDINATE_PLANE = "KC_coordinate_plane"
    # U-INT — Integer Arithmetic (TEKS 6.3C/D)
    INTEGER_ADD_SUBTRACT = "KC_integer_add_subtract"
    INTEGER_MULTIPLY_DIVIDE = "KC_integer_multiply_divide"
    # U4 — Expressions (6.EE.1–4, 6)
    EXPONENTS = "KC_exponents"
    WRITE_EXPRESSIONS = "KC_write_expressions"
    EXPRESSION_PARTS = "KC_expression_parts"
    EVALUATE_EXPRESSIONS = "KC_evaluate_expressions"
    EQUIVALENT_EXPRESSIONS = "KC_equivalent_expressions"
    DEPENDENT_VARS = "KC_dependent_vars"
    # U5 — Equations & Inequalities (6.EE.5–9)
    EQUATION_SOLUTIONS = "KC_equation_solutions"
    ONE_STEP_EQUATIONS = "KC_one_step_equations"
    INEQUALITIES = "KC_inequalities"
    # U6 — Geometry (6.G)
    TRIANGLE_PROPERTIES = "KC_triangle_properties"
    AREA_POLYGONS = "KC_area_polygons"
    VOLUME_FRACTIONAL_EDGES = "KC_volume_fractional_edges"
    POLYGONS_COORDINATE_PLANE = "KC_polygons_coordinate_plane"
    SURFACE_AREA_NETS = "KC_surface_area_nets"
    # U7 — Statistics (6.SP)
    STATISTICAL_QUESTIONS = "KC_statistical_questions"
    DATA_DISPLAYS = "KC_data_displays"
    CENTER_SPREAD_SHAPE = "KC_center_spread_shape"
    SUMMARY_STATISTICS = "KC_summary_statistics"
    MEAN_ABSOLUTE_DEVIATION = "KC_mean_absolute_deviation"
    CATEGORICAL_DATA = "KC_categorical_data"
    # U8 — Personal Financial Literacy (TEKS 6.14)
    CHECK_REGISTER = "KC_check_register"
    LIFETIME_INCOME = "KC_lifetime_income"


class Representation(StrEnum):
    """The surfaces a KC can be exercised and assessed in.

    These mirror the representations the diagnostic-gem items already use
    (`problem_statement.representations_available`) and the multi-representation
    surfaces in the UI (PROJECT.md §3.3, §3.5). The mastery model's "correctness
    across >=2 representations" rule (PROJECT.md §3.4 rule 2) is defined over this
    set; the KC advertises which representations apply to it so the rule has a
    domain to range over. Slice 1.1 only declares the slot — the rule itself is
    the mastery model's job (a later slice).
    """

    SYMBOLIC = "symbolic"
    AREA_MODEL = "area_model"
    NUMBER_LINE = "number_line"
    WORD_PROBLEM = "word_problem"


@dataclass(frozen=True)
class KnowledgeComponent:
    """One knowledge component: the unit of mastery (ARCHITECTURE.md §4).

    Frozen because Layer 1 is a source of truth, not mutable state — nothing
    downstream should be able to rewrite what a KC *is* at runtime
    (ARCHITECTURE.md §14, CLAUDE.md §8.4). ``representations`` is a tuple (not a
    list) so the whole object is hashable and genuinely immutable.

    The fields are deliberately the minimal Slice-1.1 surface. Misconceptions
    (1.2), generators (1.3) and the SymPy verifier (1.4) will reference a KC by
    its ``id``; they are not stored on the KC here.
    """

    id: KnowledgeComponentId
    skill_name: str
    description: str
    representations: tuple[Representation, ...]


# The five KCs, in the goal's natural learning order (PROJECT.md §3.1):
# identify equivalence -> find a common denominator -> add -> subtract -> place
# on a number line. The skill names mirror ARCHITECTURE.md §4's table; the
# descriptions restate each KC's job in one plain sentence. Representations are
# taken from how each KC is actually exercised in diagnostic_gems.json and the UI
# surface states (PROJECT.md §3.3, §3.5).
_KNOWLEDGE_COMPONENTS: tuple[KnowledgeComponent, ...] = (
    KnowledgeComponent(
        id=KnowledgeComponentId.EQUIVALENCE,
        skill_name="Identify equivalent fractions",
        description=(
            "Decide whether two fractions name the same amount, and rename a "
            "fraction to an equivalent form."
        ),
        representations=(
            Representation.SYMBOLIC,
            Representation.AREA_MODEL,
            Representation.WORD_PROBLEM,
        ),
    ),
    KnowledgeComponent(
        id=KnowledgeComponentId.COMMON_DENOMINATOR,
        skill_name="Find a common denominator",
        description=(
            "Find a shared piece size (denominator) that lets two fractions be "
            "written with same-size pieces."
        ),
        representations=(
            Representation.SYMBOLIC,
            Representation.AREA_MODEL,
            Representation.NUMBER_LINE,
            Representation.WORD_PROBLEM,
        ),
    ),
    KnowledgeComponent(
        id=KnowledgeComponentId.ADDITION_UNLIKE,
        skill_name="Add fractions with unlike denominators",
        description=(
            "Add two fractions whose denominators differ, by first writing them "
            "with a common denominator."
        ),
        representations=(
            Representation.SYMBOLIC,
            Representation.AREA_MODEL,
            Representation.NUMBER_LINE,
            Representation.WORD_PROBLEM,
        ),
    ),
    KnowledgeComponent(
        id=KnowledgeComponentId.SUBTRACTION_UNLIKE,
        skill_name="Subtract fractions with unlike denominators",
        description=(
            "Subtract one fraction from another when the denominators differ, by "
            "first writing them with a common denominator."
        ),
        representations=(
            Representation.SYMBOLIC,
            Representation.AREA_MODEL,
            Representation.NUMBER_LINE,
            Representation.WORD_PROBLEM,
        ),
    ),
    KnowledgeComponent(
        id=KnowledgeComponentId.NUMBER_LINE_PLACEMENT,
        skill_name="Place a fraction correctly on a number line",
        description=(
            "Locate a fraction at the correct position on a number line, "
            "reasoning about its magnitude rather than its digits."
        ),
        representations=(
            Representation.NUMBER_LINE,
            Representation.SYMBOLIC,
        ),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 1: Ratios & Rates ───
    # Ratio language (6.RP.1): tell a part-TO-part ratio from a part-TO-whole ratio. Numeric
    # answer (a single fraction entered in the symbolic editor — reuses the editor, no new
    # widget), practice-only like UNIT_RATE; the WORD_PROBLEM rep is the story framing that
    # satisfies the ≥2-rep contract and becomes the masterable surface once a widget lands (T3).
    KnowledgeComponent(
        id=KnowledgeComponentId.RATIO_LANGUAGE,
        skill_name="Read ratio language",
        description=(
            "Describe a relationship as a ratio and tell a part-to-part ratio from a "
            "part-to-whole ratio (3 red to 5 blue is 3:5; red of all counters is 3/8)."
        ),
        representations=(Representation.SYMBOLIC, Representation.WORD_PROBLEM),
    ),
    # The first Grade-6 lesson built on the existing numeric infrastructure: a unit-rate
    # word problem with a numeric answer. It advertises SYMBOLIC + WORD_PROBLEM (the lesson-spec
    # contract requires ≥2 representations), but is LIVE only on SYMBOLIC for now (see
    # scheduler._LIVE_REPRESENTATIONS) — i.e. PRACTICE-ONLY, exactly like COMMON_DENOMINATOR;
    # masterability waits on a numeric-answer word-problem widget (T3). The answer is a single
    # magnitude entered in the symbolic editor; the statement carries the rate context.
    KnowledgeComponent(
        id=KnowledgeComponentId.UNIT_RATE,
        skill_name="Find a unit rate",
        description=(
            "Find how much for ONE — the rate per single unit — from a quantity given for "
            "several units (e.g. $6 for 3 lbs is $2 per lb)."
        ),
        representations=(Representation.SYMBOLIC, Representation.WORD_PROBLEM),
    ),
    # Equivalent ratios: scale a ratio MULTIPLICATIVELY to a target term (6.RP.3a). Numeric
    # answer (the missing term), practice-only like UNIT_RATE.
    KnowledgeComponent(
        id=KnowledgeComponentId.EQUIVALENT_RATIOS,
        skill_name="Find an equivalent ratio",
        description=(
            "Find the missing term of an equivalent ratio by multiplying both terms by the "
            "same number (e.g. 3:4 = 9:12), reasoning multiplicatively rather than additively."
        ),
        representations=(Representation.SYMBOLIC, Representation.WORD_PROBLEM),
    ),
    # Percent as a rate per 100: find a percent OF a quantity (6.RP.3c). Numeric answer,
    # practice-only.
    KnowledgeComponent(
        id=KnowledgeComponentId.PERCENT,
        skill_name="Find a percent of a number",
        description=(
            "Find a given percent of a quantity, reading a percent as a rate per 100 "
            "(e.g. 30% of 50 is 15)."
        ),
        representations=(Representation.SYMBOLIC, Representation.WORD_PROBLEM),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 2: Fractions & Decimals (T2) ───
    # Multiply two proper fractions: the product is a single fraction entered in the symbolic
    # editor. Advertises SYMBOLIC + AREA_MODEL (the area model is the canonical picture of
    # fraction multiplication), but LIVE only on SYMBOLIC for now (scheduler._LIVE_REPRESENTATIONS)
    # — PRACTICE-ONLY like UNIT_RATE; masterability waits on the AREA_MODEL multiply widget (T3).
    KnowledgeComponent(
        id=KnowledgeComponentId.MULTIPLY_FRACTIONS,
        skill_name="Multiply two fractions",
        description=(
            "Multiply two proper fractions by multiplying the numerators and the "
            "denominators (e.g. 2/3 x 3/4 = 6/12 = 1/2), not by adding them."
        ),
        representations=(Representation.SYMBOLIC, Representation.AREA_MODEL),
    ),
    # Divide a fraction by a fraction (6.NS.1) — the headline Grade-6 fraction standard. Invert
    # the divisor and multiply; the quotient is a single fraction entered in the symbolic editor
    # (reuses the editor, NO new widget, like MULTIPLY_FRACTIONS). Advertises SYMBOLIC + AREA_MODEL
    # (the area/measurement picture of "how many c/d fit in a/b"), but LIVE only on SYMBOLIC for
    # now (scheduler._LIVE_REPRESENTATIONS) — PRACTICE-ONLY like MULTIPLY_FRACTIONS; masterability
    # waits on the AREA_MODEL division widget (T3).
    KnowledgeComponent(
        id=KnowledgeComponentId.DIVIDE_FRACTIONS,
        skill_name="Divide two fractions",
        description=(
            "Divide a fraction by a fraction by inverting the divisor and multiplying "
            "(e.g. 1/2 div 3/4 = 1/2 x 4/3 = 2/3), not by multiplying straight across."
        ),
        representations=(Representation.SYMBOLIC, Representation.AREA_MODEL),
    ),
    # Convert units via ratio reasoning / proportions (TEKS 6.4H; partial CCSS 6.RP.3d). Given a
    # conversion factor ("12 inches = 1 foot") and a quantity in the larger unit, find the
    # quantity in the smaller unit — a single numeric answer entered in the symbolic editor.
    # Advertises SYMBOLIC + WORD_PROBLEM (the ≥2-rep contract; the statement is a conversion
    # story), but LIVE only on SYMBOLIC for now (scheduler._LIVE_REPRESENTATIONS) — PRACTICE-ONLY
    # like UNIT_RATE; masterability waits on a numeric word-problem widget (T3).
    KnowledgeComponent(
        id=KnowledgeComponentId.UNIT_CONVERSION,
        skill_name="Convert units via proportions",
        description=(
            "Convert a quantity from a larger unit to a smaller one using a conversion factor "
            "(e.g. 12 inches per foot, so 4 feet is 48 inches), by MULTIPLYING by the factor."
        ),
        representations=(Representation.SYMBOLIC, Representation.WORD_PROBLEM),
    ),
    # GCF & LCM of two whole numbers (6.NS.4 / TEKS 6.7A): the answer is a single integer entered
    # in the symbolic editor. Advertises SYMBOLIC + NUMBER_LINE (the number line is the canonical
    # whole-number picture — factors as marks that divide the span evenly, multiples as the
    # skip-count jumps where two counts first coincide for the LCM), but LIVE only on SYMBOLIC for
    # now (scheduler._LIVE_REPRESENTATIONS) — PRACTICE-ONLY like MULTIPLY_FRACTIONS; masterability
    # waits on a whole-number NUMBER_LINE factor/multiple widget (T3).
    KnowledgeComponent(
        id=KnowledgeComponentId.GCF_LCM,
        skill_name="Find the GCF or LCM",
        description=(
            "Find the greatest common factor (the largest number that divides both) or the "
            "least common multiple (the smallest number both divide into) of two whole numbers "
            "(e.g. GCF of 12 and 18 is 6; LCM of 4 and 6 is 12)."
        ),
        representations=(Representation.SYMBOLIC, Representation.NUMBER_LINE),
    ),
    # Multi-digit whole-number division by the standard algorithm (6.NS.2): the answer is a single
    # integer quotient entered in the symbolic editor. Generated as CLEAN exact division (the
    # divisor divides the dividend evenly). Advertises SYMBOLIC + AREA_MODEL (the equal-groups
    # array is the canonical picture of division — the dividend split into ``divisor`` equal rows),
    # but LIVE only on SYMBOLIC for now (scheduler._LIVE_REPRESENTATIONS) — PRACTICE-ONLY like
    # MULTIPLY_FRACTIONS; masterability waits on an AREA_MODEL equal-groups widget (T3).
    KnowledgeComponent(
        id=KnowledgeComponentId.MULTI_DIGIT_DIVISION,
        skill_name="Divide multi-digit whole numbers",
        description=(
            "Fluently divide multi-digit whole numbers with the standard algorithm, finding the "
            "whole-number quotient of an exact division (e.g. 416 divided by 8 is 52)."
        ),
        representations=(Representation.SYMBOLIC, Representation.AREA_MODEL),
    ),
    # Multiply decimals and place the point by its place value (CCSS 6.NS.3 / TEKS 6.3E). A single
    # decimal product entered in the symbolic editor (the decimal-string answer the verifier now
    # parses exactly). Advertises SYMBOLIC + AREA_MODEL (an area model is the canonical picture of
    # a decimal product), but LIVE only on SYMBOLIC for now (scheduler._LIVE_REPRESENTATIONS) —
    # PRACTICE-ONLY like MULTIPLY_FRACTIONS; masterability waits on the area-model widget (T3).
    KnowledgeComponent(
        id=KnowledgeComponentId.DECIMAL_OPERATIONS,
        skill_name="Operate on decimals",
        description=(
            "Multiply decimals and place the decimal point in the product by counting place "
            "values (e.g. 0.5 x 0.4 = 0.20), rather than misplacing the point by a power of ten."
        ),
        representations=(Representation.SYMBOLIC, Representation.AREA_MODEL),
    ),
    # Absolute value as distance from 0 (6.NS.7c/d): the answer is a single non-negative integer
    # entered in the symbolic editor. Advertises SYMBOLIC + NUMBER_LINE (the number line is the
    # canonical picture — |x| is how many units x sits from 0, regardless of side), but LIVE only
    # on SYMBOLIC for now (scheduler._LIVE_REPRESENTATIONS) — PRACTICE-ONLY like
    # MULTI_DIGIT_DIVISION; masterability waits on a signed NUMBER_LINE distance widget (T3).
    KnowledgeComponent(
        id=KnowledgeComponentId.ABSOLUTE_VALUE,
        skill_name="Find an absolute value",
        description=(
            "Find the absolute value of an integer as its distance from 0 on the number line, "
            "so the result is never negative (e.g. the absolute value of -7 is 7)."
        ),
        representations=(Representation.SYMBOLIC, Representation.NUMBER_LINE),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit-INT: Integer Arithmetic (TEKS 6.3C/D) ───
    # Add & subtract integers (TEKS-primary; adjacent-grade CCSS 7.NS.A.1): the answer is a single
    # signed integer entered in the symbolic editor (reuses the editor, NO new widget). Advertises
    # SYMBOLIC + NUMBER_LINE (the number line is the canonical picture of integer combination —
    # directed jumps from a starting point), but LIVE only on SYMBOLIC for now
    # (scheduler._LIVE_REPRESENTATIONS) — PRACTICE-ONLY like the other Grade-6 KCs; the NUMBER_LINE
    # widget exists, so this is a natural candidate to promote to a masterable second rep later.
    KnowledgeComponent(
        id=KnowledgeComponentId.INTEGER_ADD_SUBTRACT,
        skill_name="Add and subtract integers",
        description=(
            "Add and subtract positive and negative integers, accounting for the signs "
            "(e.g. -5 + 3 = -2; 4 - 7 = -3), not by combining the magnitudes as whole numbers."
        ),
        representations=(Representation.SYMBOLIC, Representation.NUMBER_LINE),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 3: Rational Numbers ───
    # Signed numbers / opposites (6.NS.5): find the opposite of a signed integer. The answer is a
    # single signed integer entered in the symbolic editor (reuses the editor, NO new widget).
    # Advertises SYMBOLIC + NUMBER_LINE (the number line is the canonical picture of an opposite —
    # the reflection of a point across zero), but LIVE only on SYMBOLIC for now
    # (scheduler._LIVE_REPRESENTATIONS) — PRACTICE-ONLY like the other Grade-6 KCs. The NUMBER_LINE
    # widget already exists, so this is the natural first candidate to promote to a masterable
    # second rep later; kept SYMBOLIC-only here to match the template and not over-scope.
    KnowledgeComponent(
        id=KnowledgeComponentId.SIGNED_NUMBERS,
        skill_name="Find the opposite of a number",
        description=(
            "Find the opposite of a signed number — the number the same distance from zero on "
            "the other side (the opposite of -7 is 7; the opposite of 5 is -5)."
        ),
        representations=(Representation.SYMBOLIC, Representation.NUMBER_LINE),
    ),
)


class KnowledgeComponentRegistry:
    """The single, ordered, deduplicated home for the five KCs.

    Construction enforces id uniqueness (the "guaranteed-unique ids" requirement)
    so a duplicate would fail fast at import time rather than silently shadowing
    an earlier entry. Lookups accept either a ``KnowledgeComponentId`` or its raw
    catalog string, because both the DB/API (strings) and typed code (enum) need
    to resolve a KC.
    """

    def __init__(self, components: tuple[KnowledgeComponent, ...]) -> None:
        by_id: dict[KnowledgeComponentId, KnowledgeComponent] = {}
        for component in components:
            if component.id in by_id:
                raise ValueError(f"Duplicate knowledge component id: {component.id.value}")
            by_id[component.id] = component
        # Preserve declared order for deterministic iteration (PROJECT.md §4.1
        # reproducibility); dict in 3.11 keeps insertion order.
        self._by_id = by_id

    def all(self) -> tuple[KnowledgeComponent, ...]:
        """Every KC, in the registry's declared (learning) order."""
        return tuple(self._by_id.values())

    def get(self, kc_id: KnowledgeComponentId | str) -> KnowledgeComponent:
        """Resolve a KC by enum member or raw catalog string.

        Raises ``KeyError`` naming the offending id on an unknown KC, so callers
        get a clear failure instead of a silent ``None`` (CLAUDE.md §8.5: write
        for the reader).
        """
        if isinstance(kc_id, KnowledgeComponentId):
            return self._by_id[kc_id]
        try:
            resolved = KnowledgeComponentId(kc_id)
        except ValueError as exc:
            raise KeyError(f"Unknown knowledge component id: {kc_id!r}") from exc
        return self._by_id[resolved]


# The module-level registry is the single source of truth referenced across the
# system (ARCHITECTURE.md §4). Built once at import; immutable contents.
KC_REGISTRY = KnowledgeComponentRegistry(_KNOWLEDGE_COMPONENTS)


# The CONTENT-COMPLETE KCs — those with a full Layer-1 stack (registry metadata above +
# a problem generator + a lesson spec + a hint bank). Derived from the registry so it
# cannot drift: a KC becomes "live" exactly when it gets a registry entry here, and the
# generator/spec/hint coverage tests then require the rest of its stack. The other
# ``KnowledgeComponentId`` members are the Grade-6 ontology + the HelpNeed label space
# (``KC_ORDER``) but are not built — the tutor never schedules them, and ``get_kc`` /
# the content registries raise for them until their content lands (T1_T2_COORDINATION.md §4).
LIVE_KCS: frozenset[KnowledgeComponentId] = frozenset(kc.id for kc in _KNOWLEDGE_COMPONENTS)


def get_kc(kc_id: KnowledgeComponentId | str) -> KnowledgeComponent:
    """Module-level shortcut for ``KC_REGISTRY.get`` (the common case)."""
    return KC_REGISTRY.get(kc_id)
