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
    BETTER_BUY = "KC_better_buy"
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
    # An algebraic expression the learner types (Unit 4–5: write/equivalent expressions). The
    # answer is a SymPy-parseable string graded by equivalence, rendered by the ExpressionInput
    # widget (widget_id "expression").
    EXPRESSION = "expression"
    # A one-variable inequality the learner types (Unit 5: write inequalities, 6.EE.8). The answer
    # is a SymPy-parseable relational STRING ("x>=5", "x<13") graded by relational equivalence
    # (same variable, direction, and bound — i.e. same solution set), rendered by the inequality
    # input widget (widget_id "inequality").
    INEQUALITY = "inequality"
    # The four-quadrant coordinate plane (Unit 3, 6.NS.8). The learner plots/identifies one or more
    # integer-coordinate points; the answer is a set of points ("(2,-1)" or "(0,0),(3,0),(3,2)")
    # graded ORDER-INSENSITIVELY by the domain verifier, rendered by the coordinate-plane widget
    # (widget_id "coordinate_plane").
    COORDINATE_PLANE = "coordinate_plane"
    # A classification of a number into the number SETS it belongs to (Unit 3, TEKS 6.2A:
    # natural ⊂ whole ⊂ integer ⊂ rational). The answer is a comma-separated set of labels graded
    # by order-insensitive set membership, rendered by the ClassifySets widget (widget_id
    # "classify_sets").
    NUMBER_SETS = "number_sets"


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
    # Better buy (6.RP.3b / 6.RP.2): compare TWO unit rates to decide which store is the better
    # buy — the multi-step rate-reasoning lesson U1.L4 ("Rate problems") was promised but reused
    # the unit-rate generator (panel audit, 2026-06-04). Two stores sell the same item, each with
    # a (quantity, price) pair; the better buy is the LOWER price PER UNIT (price/quantity). The
    # answer is YES_NO ("is Store A the better buy?"), REUSING the existing yes/no answer kind (NO
    # widget): the truth rides in ``operands`` ((qA,pA,qB,pB)) so the SAME ``_verify_yes_no``
    # SymPy-comparison path grades it (SymPy decides, never an LLM — CLAUDE.md §8.2). Advertises
    # SYMBOLIC + WORD_PROBLEM (the comparison text IS a word problem — the ≥2-rep contract), LIVE
    # only on SYMBOLIC (scheduler._LIVE_REPRESENTATIONS) — PRACTICE-ONLY (one live answer surface;
    # WORD_PROBLEM is the same judgment with no separate surface state), exactly like UNIT_RATE and
    # STATISTICAL_QUESTIONS. Error routes never target WORD_PROBLEM — they stay on SYMBOLIC.
    KnowledgeComponent(
        id=KnowledgeComponentId.BETTER_BUY,
        skill_name="Compare two rates (better buy)",
        description=(
            "Compare two stores' prices by finding each unit price (price per item) and deciding "
            "which is the better buy — the lower price per item (6 apples for $3 is $0.50 each, "
            "10 apples for $4 is $0.40 each, so the 10-apple store is the better buy), not the "
            "lower total price."
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
    # ─── Grade-6 content build (2026-05-30) — Unit 7: Statistics ───
    # Summary statistics (CCSS 6.SP.3): summarize a small data set with a single number — its
    # MEAN, MEDIAN, MODE, or RANGE. The answer is one numeric value (a fraction for some means)
    # entered in the symbolic editor (reuses the editor, NO new widget). Advertises SYMBOLIC +
    # NUMBER_LINE (the data set is a set of points on the number line, and center/spread are read
    # off that line — the canonical picture), but LIVE only on SYMBOLIC for now
    # (scheduler._LIVE_REPRESENTATIONS) — PRACTICE-ONLY like the other Grade-6 KCs. The NUMBER_LINE
    # widget already exists, so it is the natural candidate to promote to a masterable second rep
    # later; kept SYMBOLIC-only here to not over-scope this build.
    KnowledgeComponent(
        id=KnowledgeComponentId.SUMMARY_STATISTICS,
        skill_name="Summarize a data set with one number",
        description=(
            "Compute a summary statistic of a small data set — its mean, median, mode, or range "
            "(e.g. the mean of 4, 8, 6, 10 is 7; the range of 2, 7, 4 is 5)."
        ),
        representations=(Representation.SYMBOLIC, Representation.NUMBER_LINE),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 7: Statistics ───
    # Data displays (CCSS 6.SP.4): read and interpret a data display — a dot plot / frequency
    # table / histogram described textually in the prompt. The answer is one numeric value (a
    # count or a value) entered in the symbolic editor (reuses the editor, NO new widget today; a
    # future stats-display renderer will visualize what the prompt describes). Advertises SYMBOLIC
    # + NUMBER_LINE (a dot plot sits on a number line — each dot a data point above its value, the
    # canonical picture of this display), but LIVE only on SYMBOLIC for now
    # (scheduler._LIVE_REPRESENTATIONS) — PRACTICE-ONLY like the other Grade-6 KCs. The NUMBER_LINE
    # widget already exists, so it is the natural candidate to promote to a masterable second rep
    # later; kept SYMBOLIC-only here to not over-scope this build.
    KnowledgeComponent(
        id=KnowledgeComponentId.DATA_DISPLAYS,
        skill_name="Read a data display",
        description=(
            "Read and interpret a data display (a dot plot, frequency table, or histogram) — "
            "e.g. how many data points are greater than 5, the most frequent value, or how many "
            "fall in a given bin."
        ),
        representations=(Representation.SYMBOLIC, Representation.NUMBER_LINE),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 4: Expressions ───
    # Write an algebraic expression from a word phrase (6.EE.2a / 6.EE.B.6): the answer is a typed
    # expression STRING ("p + 7", "3*n"), graded by SymPy equivalence — the FIRST expression-answer
    # KC, establishing the wire contract the ExpressionInput widget consumes (answer_kind
    # "expression", widget_id "expression"). Advertises EXPRESSION + WORD_PROBLEM (the phrase IS a
    # word problem; the ≥2-rep contract), LIVE only on EXPRESSION (scheduler._LIVE_REPRESENTATIONS)
    # — PRACTICE-ONLY; EXPRESSION is the default surface, so widget_id resolves to "expression".
    KnowledgeComponent(
        id=KnowledgeComponentId.WRITE_EXPRESSIONS,
        skill_name="Write an expression",
        description=(
            "Write an algebraic expression with a variable from a word phrase, choosing the right "
            "operation and order (e.g. '7 more than p' is p + 7; '7 less than p' is p - 7)."
        ),
        representations=(Representation.EXPRESSION, Representation.WORD_PROBLEM),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 4: Expressions ───
    # Evaluate an expression at a given value (6.EE.2c): substitute a value for the variable and
    # evaluate a*x + b honoring order of operations ("evaluate 3x + 2 when x = 4" -> 14). The answer
    # is a single NUMERIC value entered in the editor (reuses the editor, NO new widget). Offers TWO
    # REAL surfaces — SYMBOLIC (the symbolic "evaluate … when x = …") and AREA_MODEL (an array/area
    # picture: a rows of x squares, plus b extra) — answered with the SAME numeric value, and BOTH
    # are live (scheduler._LIVE_REPRESENTATIONS), so this KC is MASTERABLE: the §3.4 rule-2
    # representation-diversity gate is reachable live, unlike the practice-only Grade-6 KCs.
    KnowledgeComponent(
        id=KnowledgeComponentId.EVALUATE_EXPRESSIONS,
        skill_name="Evaluate an expression",
        description=(
            "Substitute a given value for the variable and evaluate the expression, honoring order "
            "of operations — multiply before you add (evaluate 3x + 2 when x = 4 gives 14, not 18)."
        ),
        representations=(Representation.SYMBOLIC, Representation.AREA_MODEL),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 4: Expressions ───
    # Evaluate a whole-number exponent (6.EE.1): read a power as repeated multiplication and
    # compute its value ("3^4 = ?" -> 81; "evaluate 2^5" -> 32). The answer is a single NUMERIC
    # value entered in the editor (reuses the editor, NO new widget). Offers TWO REAL surfaces —
    # SYMBOLIC (the symbolic power "base^exp") and AREA_MODEL (the geometric picture: base^2 is the
    # area of a square of side base, base^3 the volume of a cube) — answered with the SAME numeric
    # value, and BOTH are live (scheduler._LIVE_REPRESENTATIONS), so this KC is MASTERABLE: the
    # §3.4 rule-2 representation-diversity gate is reachable live, unlike the practice-only KCs.
    KnowledgeComponent(
        id=KnowledgeComponentId.EXPONENTS,
        skill_name="Evaluate an exponent",
        description=(
            "Evaluate a whole-number exponent as repeated multiplication — the base multiplied by "
            "itself exponent-many times (3^4 = 3x3x3x3 = 81; 2^5 = 32), not the base times the "
            "exponent."
        ),
        representations=(Representation.SYMBOLIC, Representation.AREA_MODEL),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 5: Equations & Inequalities ───
    # Solve a one-step equation (6.EE.7): ONE KC covering BOTH additive equations (x + b = c) and
    # multiplicative equations (a*x = c) behind an operand-mode flag in the generator. The answer is
    # the NUMERIC value of x entered in the editor (reuses the editor, NO new widget). Advertises
    # SYMBOLIC + WORD_PROBLEM — and unlike the earlier Grade-6 KCs this one is built
    # MASTERABLE-LIVE: BOTH reps are live (scheduler._LIVE_REPRESENTATIONS), so a learner can be
    # correct in two representations (the SYMBOLIC equation and the same equation in a story),
    # satisfying mastery rule 2. WORD_PROBLEM has no surface state, so error routes target SYMBOLIC.
    KnowledgeComponent(
        id=KnowledgeComponentId.ONE_STEP_EQUATIONS,
        skill_name="Solve a one-step equation",
        description=(
            "Solve a one-step equation for x by applying the inverse operation — subtract to undo "
            "addition (x + 5 = 12 gives x = 7), divide to undo multiplying (3x = 12 gives x = 4)."
        ),
        representations=(Representation.SYMBOLIC, Representation.WORD_PROBLEM),
    ),
    # Produce an expression EQUIVALENT to a given one (6.EE.3 / 6.EE.4): expand a product like
    # "3(x + 2)" into "3x + 6" (or combine like terms), the answer a typed expression STRING graded
    # by SymPy equivalence — REUSING the expression-answer contract KC_write_expressions
    # established (answer_kind "expression", widget_id "expression"). Advertises EXPRESSION (the
    # typed answer surface) + WORD_PROBLEM (the ≥2-rep ontology), LIVE only on EXPRESSION
    # (scheduler._LIVE_REPRESENTATIONS) — PRACTICE-ONLY: the only widget that accepts a typed
    # algebra answer is the ExpressionInput, so a second masterable surface awaits its own widget.
    KnowledgeComponent(
        id=KnowledgeComponentId.EQUIVALENT_EXPRESSIONS,
        skill_name="Write an equivalent expression",
        description=(
            "Rewrite an expression as an equivalent one — distribute a product like 3(x + 2) into "
            "3x + 6, or combine like terms like 2x + 5x into 7x — keeping the same value."
        ),
        representations=(Representation.EXPRESSION, Representation.WORD_PROBLEM),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 5: Inequalities ───
    # Write a one-variable inequality from a real-world constraint (6.EE.8): "a number is at least
    # 5" -> x>=5; "you must be under 13" -> x<13. The answer is a typed RELATIONAL string graded by
    # SymPy relational equivalence (same variable, direction, bound = same solution set) — a NEW
    # answer kind + a NEW Representation (INEQUALITY), modeled on the EXPRESSION precedent
    # KC_write_expressions established. Advertises INEQUALITY (the typed answer surface) +
    # WORD_PROBLEM (the constraint IS a word problem; the ≥2-rep contract), LIVE only on INEQUALITY
    # (scheduler._LIVE_REPRESENTATIONS) — PRACTICE-ONLY; INEQUALITY is the default surface, so
    # widget_id resolves to "inequality".
    KnowledgeComponent(
        id=KnowledgeComponentId.INEQUALITIES,
        skill_name="Write an inequality",
        description=(
            "Write a one-variable inequality (>, >=, <, <=) for a real-world constraint, choosing "
            "the right direction and whether the boundary is included (e.g. 'at least 5' is "
            "x >= 5; 'under 13' is x < 13)."
        ),
        representations=(Representation.INEQUALITY, Representation.WORD_PROBLEM),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 3: The coordinate plane ───
    # Identify/plot points in the four-quadrant coordinate plane (6.NS.8 / TEKS 6.11A): the answer
    # is a SET of integer-coordinate POINTS — a single point "(2,-1)" or a polygon vertex list
    # "(0,0),(3,0),(3,2)" — graded ORDER-INSENSITIVELY by the domain verifier (a polygon's vertices
    # match in any order; a single point is a one-element set). The FIRST point-set answer KC,
    # establishing the wire contract the coordinate-plane widget consumes (answer_kind
    # "coordinate", widget_id "coordinate_plane"). Advertises COORDINATE_PLANE + WORD_PROBLEM (the
    # phrase IS a word problem; the ≥2-rep contract), LIVE only on COORDINATE_PLANE
    # (scheduler._LIVE_REPRESENTATIONS) — PRACTICE-ONLY; COORDINATE_PLANE is the default surface, so
    # widget_id resolves to "coordinate_plane".
    KnowledgeComponent(
        id=KnowledgeComponentId.COORDINATE_PLANE,
        skill_name="Plot points in the coordinate plane",
        description=(
            "Plot and identify points in the four-quadrant coordinate plane, including reflecting "
            "a point across an axis and reading distance along a shared row or column."
        ),
        representations=(Representation.COORDINATE_PLANE, Representation.WORD_PROBLEM),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 3: Rational Numbers (TEKS 6.2A) ───
    # Classify a number into the number SETS it belongs to: natural ⊂ whole ⊂ integer ⊂ rational
    # (the nested-subset structure). The answer is a SET of labels (comma-separated), graded by
    # order-insensitive set membership — the FIRST set-answer KC, establishing the wire contract
    # the ClassifySets widget consumes (answer_kind "number_sets", widget_id "classify_sets").
    # Advertises NUMBER_SETS + WORD_PROBLEM (the ≥2-rep contract; the phrase IS a word problem),
    # LIVE only on NUMBER_SETS (scheduler._LIVE_REPRESENTATIONS) — PRACTICE-ONLY (one live answer
    # surface, like write_expressions; WORD_PROBLEM is framing with no surface state). NUMBER_SETS
    # is the default surface, so widget_id resolves to "classify_sets".
    KnowledgeComponent(
        id=KnowledgeComponentId.CLASSIFY_NUMBER_SETS,
        skill_name="Classify number sets",
        description=(
            "Decide which number sets a value belongs to — natural, whole, integer, rational — "
            "knowing they nest (every whole number is an integer; every integer is rational)."
        ),
        representations=(Representation.NUMBER_SETS, Representation.WORD_PROBLEM),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 4: Expressions ───
    # Parts of an expression (6.EE.2b): name the COEFFICIENT, the CONSTANT, or the number of TERMS
    # of an algebraic expression (e.g. "the coefficient of x in 7x + 4" is 7). An item-mode flag
    # varies which part is asked. The answer is a single whole number entered in the existing
    # NUMERIC editor (reuses the editor, NO new widget), so the live answer surface is SYMBOLIC.
    # Advertises SYMBOLIC + WORD_PROBLEM (the ≥2-rep contract; WORD_PROBLEM is just the phrase
    # framing with no surface state), LIVE only on SYMBOLIC (scheduler._LIVE_REPRESENTATIONS) —
    # PRACTICE-ONLY, like the other numeric Grade-6 KCs (unit_rate, unit_conversion). There is no
    # second CONCRETE answer widget for naming a part, so SYMBOLIC stays the only live surface
    # (kept honest per the build brief — error routes never target WORD_PROBLEM).
    KnowledgeComponent(
        id=KnowledgeComponentId.EXPRESSION_PARTS,
        skill_name="Identify parts of an expression",
        description=(
            "Name a part of an algebraic expression — the coefficient of a variable, the constant "
            "term, or how many terms it has (in 7x + 4, the coefficient of x is 7, the constant "
            "is 4, and there are 2 terms)."
        ),
        representations=(Representation.SYMBOLIC, Representation.WORD_PROBLEM),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit-INT: Integer Arithmetic (TEKS 6.3C/D) ───
    # Multiply & divide integers (TEKS-primary; adjacent-grade CCSS 7.NS.A.2): the answer is a
    # single signed integer entered in the symbolic editor (reuses the editor, NO new widget). A
    # divide item always divides evenly, so the quotient is an integer. Advertises SYMBOLIC +
    # NUMBER_LINE (a product is repeated directed jumps from zero — the number-line picture of
    # integer multiplication; division undoes it), but LIVE only on SYMBOLIC for now
    # (scheduler._LIVE_REPRESENTATIONS) — PRACTICE-ONLY like the other Grade-6 KCs; the NUMBER_LINE
    # widget exists, so this is a natural candidate to promote to a masterable second rep later.
    KnowledgeComponent(
        id=KnowledgeComponentId.INTEGER_MULTIPLY_DIVIDE,
        skill_name="Multiply and divide integers",
        description=(
            "Multiply and divide positive and negative integers using the sign rules "
            "(e.g. -3 × 4 = -12; -12 ÷ -4 = 3; 6 × -5 = -30): like signs give a positive "
            "result, unlike signs a negative one."
        ),
        representations=(Representation.SYMBOLIC, Representation.NUMBER_LINE),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 6: Geometry (TEKS 6.8A) ───
    # Triangle properties (TEKS-primary, not in CCSS Grade 6): apply the angle sum (a triangle's
    # three angles total 180°, so a missing angle is 180 − the other two) and the base/height–area
    # relationship (A = ½ · base · height). An item-mode flag picks one or the other; either way the
    # answer is a single NUMERIC value entered in the existing editor (NO new widget). Advertises
    # SYMBOLIC + AREA_MODEL — the triangle figure is a geometric/area picture (its angles and its
    # base×height region are the natural second surface), but LIVE only on SYMBOLIC for now
    # (scheduler._LIVE_REPRESENTATIONS) — PRACTICE-ONLY like the other Grade-6 KCs. Promoting
    # AREA_MODEL to live (when a triangle-figure input widget lands) makes it masterable with no
    # other change.
    KnowledgeComponent(
        id=KnowledgeComponentId.TRIANGLE_PROPERTIES,
        skill_name="Apply triangle properties",
        description=(
            "Use the properties of a triangle: the three angles add to 180° (so a missing angle "
            "is 180 minus the other two), and the area is half the base times the height "
            "(A = ½ · b · h)."
        ),
        representations=(Representation.SYMBOLIC, Representation.AREA_MODEL),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 6: Geometry ───
    # Area of polygons (6.G.1): find the area of a triangle (1/2 · b · h) or a parallelogram /
    # rectangle (b · h) by composing/decomposing into rectangles and triangles. An item-mode flag
    # varies the shape. The answer is a single numeric area entered in the existing NUMERIC editor
    # (reuses the editor, NO new widget); the prompt can show the existing display-only
    # FigureStimulus (a labeled figure). MASTERABLE-LIVE: SYMBOLIC + AREA_MODEL are BOTH live
    # (scheduler._LIVE_REPRESENTATIONS) and answered with the SAME numeric area — area IS literally
    # an area-model quantity (read the area off a unit-square grid vs. compute it from the formula),
    # so the two reps meet the §3.4 rule-2 representation-diversity gate, like
    # KC_evaluate_expressions and KC_exponents (not the practice-only Grade-6 KCs).
    KnowledgeComponent(
        id=KnowledgeComponentId.AREA_POLYGONS,
        skill_name="Find the area of polygons",
        description=(
            "Find the area of a triangle (one half base times height) or a parallelogram / "
            "rectangle (base times height) by composing and decomposing into rectangles and "
            "triangles — a triangle is half its bounding parallelogram."
        ),
        representations=(Representation.SYMBOLIC, Representation.AREA_MODEL),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 6: Geometry ───
    # Volume of a right rectangular prism with FRACTIONAL edge lengths (6.G.2): V = l*w*h with
    # fraction edges (l=3/2, w=2, h=5/2 -> 15/2). The answer is a single NUMERIC value (a Rational
    # fraction) entered in the existing editor (reuses the editor, NO new widget); all arithmetic
    # is exact SymPy Rational (no float). Advertises SYMBOLIC + AREA_MODEL — a prism's volume IS an
    # area-model in 3D (a stack of unit-cube layers), the canonical concrete picture of V = l*w*h —
    # but LIVE only on SYMBOLIC for now (scheduler._LIVE_REPRESENTATIONS) — PRACTICE-ONLY like the
    # other numeric Grade-6 KCs. The AREA_MODEL prism widget would be the natural masterable second
    # surface later; kept SYMBOLIC-only here to not over-scope this build (error routes never target
    # AREA_MODEL while it has no surface state — they stay on SYMBOLIC).
    KnowledgeComponent(
        id=KnowledgeComponentId.VOLUME_FRACTIONAL_EDGES,
        skill_name="Find the volume of a prism with fractional edges",
        description=(
            "Find the volume of a right rectangular prism with fractional edge lengths by "
            "MULTIPLYING the three edges — V = l x w x h (a prism 3/2 by 2 by 5/2 has volume "
            "15/2), not by adding them."
        ),
        representations=(Representation.SYMBOLIC, Representation.AREA_MODEL),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 6: Geometry (CCSS 6.G.3) ───
    # Draw polygons in the coordinate plane given vertices, and use coordinates to solve problems:
    # give the missing vertex of an axis-aligned rectangle from its other three corners, or name the
    # four corners of a rectangle described by its x- and y-extents (6.G.3). The answer is a SET of
    # integer-coordinate POINTS — REUSES the coordinate point-set contract KC_coordinate_plane
    # (6.NS.8) established (answer_kind "coordinate", widget_id "coordinate_plane"), graded
    # ORDER-INSENSITIVELY by the SAME domain verifier path (_verify_coordinate / parse_points) — NO
    # new answer kind, widget, or grading path. Advertises COORDINATE_PLANE + WORD_PROBLEM (the
    # phrase IS a word problem; the >=2-rep contract), LIVE only on COORDINATE_PLANE
    # (scheduler._LIVE_REPRESENTATIONS) — PRACTICE-ONLY; COORDINATE_PLANE is the default surface, so
    # widget_id resolves to "coordinate_plane".
    KnowledgeComponent(
        id=KnowledgeComponentId.POLYGONS_COORDINATE_PLANE,
        skill_name="Draw polygons in the coordinate plane",
        description=(
            "Draw polygons in the coordinate plane from their vertices and use coordinates to "
            "solve problems — find the missing corner of a rectangle from its other three corners, "
            "or name the four corners of a rectangle from its width and height."
        ),
        representations=(Representation.COORDINATE_PLANE, Representation.WORD_PROBLEM),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 6: Geometry ───
    # Surface area of a right rectangular prism (or cube) from its net (6.G.4): unfold the solid
    # into its six rectangular faces and SUM their areas — SA = 2(l*w + l*h + w*h) (a 2x3x4 prism
    # has SA = 2(6 + 8 + 12) = 52). The answer is a single NUMERIC value entered in the existing
    # editor (reuses the editor, NO new widget); the prompt can show the existing display-only
    # FigureStimulus (a labeled net/figure). Advertises SYMBOLIC + AREA_MODEL — a net IS literally
    # an area model of the faces (each face is a rectangle whose area you read/compute and add) —
    # but LIVE only on SYMBOLIC for now (scheduler._LIVE_REPRESENTATIONS) — PRACTICE-ONLY like the
    # other numeric Grade-6 KCs. The AREA_MODEL net widget would be the natural masterable second
    # surface later; kept SYMBOLIC-only here to not over-scope this build (error routes never target
    # AREA_MODEL while it has no surface state — they stay on SYMBOLIC).
    KnowledgeComponent(
        id=KnowledgeComponentId.SURFACE_AREA_NETS,
        skill_name="Find the surface area of a prism from its net",
        description=(
            "Find the surface area of a right rectangular prism (or cube) by unfolding it into a "
            "net of six rectangular faces and adding the face areas — SA = 2(l x w + l x h + "
            "w x h) (a 2 by 3 by 4 prism has surface area 52), not by counting only three faces."
        ),
        representations=(Representation.SYMBOLIC, Representation.AREA_MODEL),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 7: Statistics ───
    # Mean absolute deviation (CCSS 6.SP.5c): the mean of the absolute deviations of a small data
    # set from the data's mean ({2,4,6,8} -> mean 5, |deviations| {3,1,1,3}, MAD 2). The answer is
    # a single Rational entered in the symbolic editor (reuses the editor, NO new widget); the data
    # set is given in the prompt text. Advertises SYMBOLIC + NUMBER_LINE — each deviation is a
    # DISTANCE from the mean on the number line, and the MAD is the average of those distances, so
    # the number line is the canonical picture of the spread — but LIVE only on SYMBOLIC for now
    # (scheduler._LIVE_REPRESENTATIONS) — PRACTICE-ONLY like the other numeric Grade-6 KCs. The
    # NUMBER_LINE widget already exists, so it is the natural masterable second surface later; kept
    # SYMBOLIC-only here to match the template and not over-scope (errors never route to NUMBER_LINE
    # while it has no surface state — they stay on SYMBOLIC).
    KnowledgeComponent(
        id=KnowledgeComponentId.MEAN_ABSOLUTE_DEVIATION,
        skill_name="Find the mean absolute deviation of a data set",
        description=(
            "Find the mean absolute deviation (MAD) of a small data set — the mean of the "
            "distances of the values from the data's mean. For {2, 4, 6, 8} the mean is 5, the "
            "absolute deviations are {3, 1, 1, 3}, and the MAD is 2."
        ),
        representations=(Representation.SYMBOLIC, Representation.NUMBER_LINE),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 7: Statistics (6.SP) ───
    # Center & spread (6.SP.2): describe a distribution by a measure of CENTER (the median) or
    # SPREAD (the range, or the interquartile range Q3 − Q1), computed exactly from a small data
    # set given in the prompt. The answer is a single numeric value entered in the symbolic editor
    # (reuses the editor, NO new widget). Advertises SYMBOLIC + NUMBER_LINE — center and spread are
    # canonically read on a number line (a box plot lays Q1/median/Q3 and the min/max along one) —
    # but LIVE only on SYMBOLIC for now (scheduler._LIVE_REPRESENTATIONS) — PRACTICE-ONLY like the
    # other numeric Grade-6 KCs; the NUMBER_LINE widget exists, so it is the natural masterable
    # second surface to promote later. Error routes never target NUMBER_LINE while it has no surface
    # state for this KC — they stay on SYMBOLIC.
    KnowledgeComponent(
        id=KnowledgeComponentId.CENTER_SPREAD_SHAPE,
        skill_name="Describe a distribution by center and spread",
        description=(
            "Describe a data distribution with a measure of center (the median) or spread (the "
            "range = max - min, or the interquartile range IQR = Q3 - Q1), computed from a small "
            "data set — e.g. the IQR of 2, 4, 6, 8, 10, 12 is 10 - 4 = 6."
        ),
        representations=(Representation.SYMBOLIC, Representation.NUMBER_LINE),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 7: Statistics (TEKS 6.12D) ───
    # Categorical data (TEKS 6.12D): read counts/frequencies from a category breakdown given in the
    # prompt ("12 like red, 8 blue, 5 green") and compute a summary — how many MORE chose one
    # category than another (a count difference), the TOTAL surveyed, or the RELATIVE FREQUENCY of a
    # category (a fraction of the total). The answer is one numeric value — an integer for the
    # difference/total, an exact Rational for relative frequency — entered in the symbolic editor
    # (reuses the editor, NO new widget). Advertises SYMBOLIC + AREA_MODEL: a category breakdown is
    # canonically pictured as a bar/area graph (one bar per category, length = count), which is the
    # ≥2-rep second surface. LIVE only on SYMBOLIC for now (scheduler._LIVE_REPRESENTATIONS) —
    # PRACTICE-ONLY like the other numeric Grade-6 KCs; the AREA_MODEL bar-graph surface is the
    # natural masterable second rep to promote later. Error routes never target AREA_MODEL while it
    # has no surface state for this KC — they stay on SYMBOLIC.
    KnowledgeComponent(
        id=KnowledgeComponentId.CATEGORICAL_DATA,
        skill_name="Summarize categorical data",
        description=(
            "Read counts from a category breakdown and summarize them — how many more chose one "
            "category than another, the total surveyed, or the relative frequency (fraction) of a "
            "category (e.g. 12 like red and 8 blue: 4 more like red; 25 surveyed if green is 5)."
        ),
        representations=(Representation.SYMBOLIC, Representation.AREA_MODEL),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 7: Statistics (CCSS 6.SP.1) ───
    # Statistical questions: decide whether a question is a STATISTICAL question — one that
    # anticipates VARIABILITY in the data (its answers vary across a population), e.g. "How tall
    # are the students in my class?" (YES — heights vary) vs. "How tall is the teacher?" (NO — a
    # single value). The answer is YES_NO, REUSING the existing yes/no answer kind (NO new widget):
    # the generator draws from curated statistical (→ YES) and non-statistical (→ NO) question
    # templates, and the truth rides in ``operands`` so the SAME ``_verify_yes_no`` SymPy-equality
    # path grades it (SymPy decides, never an LLM — CLAUDE.md §8.2). Advertises SYMBOLIC +
    # WORD_PROBLEM (the question text IS a word problem; the ≥2-rep contract), LIVE only on SYMBOLIC
    # (scheduler._LIVE_REPRESENTATIONS) — PRACTICE-ONLY (one live answer surface; WORD_PROBLEM is
    # the same judgment with no separate surface state). Error routes never target WORD_PROBLEM —
    # they stay on SYMBOLIC, the only live surface.
    KnowledgeComponent(
        id=KnowledgeComponentId.STATISTICAL_QUESTIONS,
        skill_name="Recognize statistical questions",
        description=(
            "Decide whether a question is a statistical question — one that anticipates "
            "variability in the data, so its answers vary (How tall are the students in my "
            "class?), versus one with a single fixed answer (How tall is the teacher?)."
        ),
        representations=(Representation.SYMBOLIC, Representation.WORD_PROBLEM),
    ),
    # ─── Grade-6 content build (2026-05-31) — Unit 4/5: Dependent variables (CCSS 6.EE.9) ───
    # Use variables for two quantities that change in relationship and analyze how the DEPENDENT
    # variable depends on the INDEPENDENT one. The gradeable form anchors on a relationship equation
    # y = a*x: given the independent value x, find the dependent value y. Offers TWO REAL live
    # surfaces answered from the SAME relationship, so this KC is MASTERABLE (the §3.4 rule-2
    # representation-diversity gate is reachable live, like KC_evaluate_expressions):
    #   - SYMBOLIC (default) — the scalar dependent value y entered in the NUMBER_ENTRY editor
    #     ("y = 3x, what is y when x = 4?" -> 12), graded NUMERIC by SymPy substitute-and-evaluate;
    #   - COORDINATE_PLANE — plot the point (x, y) that satisfies the relationship for the given x
    #     ("plot (x, y) when x = 4" -> (4,12)), REUSING the live coordinate-plane widget and the
    #     existing order-insensitive coordinate verifier (per the project handoff: dependent_vars
    #     can reuse the live coordinate widget).
    # Two answer kinds across one KC's reps (NUMERIC + COORDINATE) — the wire keys the widget on the
    # surface and the verifier on answer_kind PER PROBLEM, so both surfaces grade cleanly. Errors
    # route to the OTHER live surface (each has a real surface state), never to a rep without one.
    KnowledgeComponent(
        id=KnowledgeComponentId.DEPENDENT_VARS,
        skill_name="Relate dependent and independent variables",
        description=(
            "Use variables for two quantities that change together, write the relationship, and "
            "find the dependent value from the independent one — for y = 3x, when x is 4 the "
            "dependent value y is 12 (multiply by the rate, not add)."
        ),
        representations=(Representation.SYMBOLIC, Representation.COORDINATE_PLANE),
    ),
    # ─── Grade-6 content build (2026-05-31) — Unit 5: Equation solutions (CCSS 6.EE.5) ───
    # Understand solving an equation as the process of answering WHICH values make it true, and use
    # SUBSTITUTION to decide whether a given number is a solution. This is TESTING a candidate value
    # — deliberately distinct from KC_one_step_equations (solve from scratch, 6.EE.7), which stays a
    # separate KC. Offers TWO REAL live surfaces over the same equation x + b = c, so this KC is
    # MASTERABLE (the §3.4 rule-2 representation-diversity gate is reachable live, like
    # KC_dependent_vars):
    #   - NUMBER_LINE (default) — a YES/NO judgment "Is x = N a solution to x + b = c?" answered
    #     with the yes/no control (REUSES the YES_NO answer kind, NO new widget). A candidate is a
    #     point on the line; the SymPy SUBSTITUTION truth rides in ``operands`` ((1,1) → YES for a
    #     true candidate, (1,0) → NO for a false one), so the SAME ``_verify_yes_no`` SymPy-equality
    #     path grades it (SymPy decides, never an LLM — CLAUDE.md §8.2). Both true and false
    #     candidates are generated, so "yes" is not always correct.
    #   - SYMBOLIC — the SOLVE framing "Which value of x makes x + b = c true?" answered with the
    #     scalar solution c − b in the NUMBER_ENTRY editor. This is a SYMBOLIC SCALAR KC (NOT a
    #     fraction KC — kept OUT of lesson_spec._FRACTION_ANSWER_KCS), so it routes to NUMBER_ENTRY
    #     via the widget contract; graded NUMERIC by SymPy.
    # Both reps have a real surface state (NUMBER_LINE_PRIMARY / SYMBOLIC_FOCUS), so an error on one
    # routes honestly to the other — never to a rep without a surface state (WORD_PROBLEM is not a
    # rep here).
    KnowledgeComponent(
        id=KnowledgeComponentId.EQUATION_SOLUTIONS,
        skill_name="Test whether a value is a solution",
        description=(
            "Understand solving an equation as finding which values make it true, and use "
            "substitution to decide whether a given number is a solution — x = 5 is a solution to "
            "x + 4 = 9 because 5 + 4 = 9, and the value that makes it true is 5."
        ),
        representations=(Representation.NUMBER_LINE, Representation.SYMBOLIC),
    ),
    # ─── Grade-6 content build (2026-05-31) — Unit 8: Check register (TEKS 6.14C) ───
    # Balance a check register: keep a RUNNING BALANCE across a short sequence of deposits (+) and
    # withdrawals (−). One of the two SymPy-gradeable financial-literacy KCs (owner decision
    # DEC.FINLIT). Offers TWO REAL live surfaces, so this KC is MASTERABLE (the §3.4 rule-2 gate is
    # reachable live, like KC_equation_solutions):
    #   - SYMBOLIC (default) — the ENDING BALANCE: the exact SymPy sum of the starting balance and
    #     the signed transactions, a currency/decimal answer entered in the NUMBER_ENTRY editor (NOT
    #     a fraction KC — the editor cannot express a decimal). The data is VARIABLE-LENGTH (the
    #     operands (start, *signed_transactions)), matched ``operand_count=None`` like the stats.
    #   - NUMBER_LINE — an OVERDRAFT YES/NO check ("is the balance enough to cover a $X
    #     withdrawal?"), whose SymPy truth (balance >= X) rides in ``operands`` exactly as
    #     KC_equation_solutions encodes its yes/no truth, so the SAME ``_verify_yes_no`` path grades
    #     it.
    # Both reps have a real surface state (SYMBOLIC_FOCUS / NUMBER_LINE_PRIMARY), so an error on one
    # routes honestly to the other — never to a rep without a surface state.
    KnowledgeComponent(
        id=KnowledgeComponentId.CHECK_REGISTER,
        skill_name="Balance a check register",
        description=(
            "Keep a running balance in a check register: add each deposit and subtract each "
            "withdrawal from the starting balance to find the ending balance (start 100, deposit "
            "50, withdraw 20 leaves 130), and tell whether the balance covers the next withdrawal."
        ),
        representations=(Representation.SYMBOLIC, Representation.NUMBER_LINE),
    ),
    # ─── Grade-6 content build (2026-05-31) — Unit 8: Lifetime income (TEKS 6.14H) ───
    # Salary & lifetime income: lifetime income = annual salary × working years, and comparing
    # income across education levels. The other SymPy-gradeable financial-literacy KC (DEC.FINLIT).
    # The gradeable form is a NUMERIC scalar in the NUMBER_ENTRY editor (NOT a fraction KC): default
    # item is "$X/year over Y years -> X*Y", and a second item MODE frames the education-level
    # COMPARISON ("how much MORE does job A earn than job B over Y years -> (A−B)*Y"). Advertises
    # SYMBOLIC + WORD_PROBLEM (the ≥2-rep contract; the salary scenario IS a word problem), but LIVE
    # only on SYMBOLIC for now (scheduler._LIVE_REPRESENTATIONS) — PRACTICE-ONLY like KC_unit_rate;
    # errors route to SYMBOLIC (a rep WITH a surface state), never to WORD_PROBLEM.
    KnowledgeComponent(
        id=KnowledgeComponentId.LIFETIME_INCOME,
        skill_name="Find lifetime income from a salary",
        description=(
            "Find lifetime income by MULTIPLYING annual salary by the number of working years "
            "($40,000 a year for 30 years is $1,200,000), and compare income across education "
            "levels by the difference over those years — not by reading the yearly salary alone."
        ),
        representations=(Representation.SYMBOLIC, Representation.WORD_PROBLEM),
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


# The FIVE FOUNDATION fraction KCs — the terminal "basics" set (PROJECT.md §3.1; the same KCs
# prerequisites.py calls terminal, "only the FIVE FOUNDATION fraction KCs are terminal"). This is
# the foundation/remediation floor: a learner struggling in a Grade-6 lesson drops down to one of
# these, and nothing auto-drops below them. The course-map "foundation work" home (CourseMap.tsx)
# renders exactly this set, so it lives here — the single source of truth, next to ``LIVE_KCS`` —
# rather than being re-hardcoded in the frontend. Membership is what drives ``CourseNodeView``'s
# ``is_foundation`` flag on the /course wire.
FOUNDATION_KCS: frozenset[KnowledgeComponentId] = frozenset(
    {
        KnowledgeComponentId.EQUIVALENCE,
        KnowledgeComponentId.COMMON_DENOMINATOR,
        KnowledgeComponentId.ADDITION_UNLIKE,
        KnowledgeComponentId.SUBTRACTION_UNLIKE,
        KnowledgeComponentId.NUMBER_LINE_PLACEMENT,
    }
)


def get_kc(kc_id: KnowledgeComponentId | str) -> KnowledgeComponent:
    """Module-level shortcut for ``KC_REGISTRY.get`` (the common case)."""
    return KC_REGISTRY.get(kc_id)
