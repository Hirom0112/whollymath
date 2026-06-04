"""Layer-1 misconception catalog + deterministic wrong-answer generators.

This is Slice 1.2 of the domain model (ARCHITECTURE.md §5 Layer 1; PROJECT.md
§4.1, §4.2). It hangs off the KC registry (`knowledge_components.py`, Slice 1.1)
and is the single source of truth for *the named ways a learner gets a fraction
problem wrong*. The mastery model, the persona behavioral simulator (Layer 3),
and the transfer test all reference these same misconception ids, exactly as they
all reference the same KC ids — keeping them in one registry is what makes that
reference unambiguous.

Two things live here, and nothing else:

  (a) the five named misconceptions as typed, immutable domain objects, with ids
      matching `diagnostic_gems.json` `_meta.misconception_catalog` verbatim; and
  (b) deterministic functions that, given a fraction problem, produce the SPECIFIC
      wrong answer that misconception yields.

Each generator is grounded in RESEARCH.md §1.2 (the fraction-misconception
catalog) and is verified against the gem bank's SymPy-computed
`wrong_answer_produced` oracle values (RESEARCH.md §6) in the test suite.

SymPy IS used here for fraction arithmetic — this is `domain/`, the one place
math correctness lives (CLAUDE.md §7, ARCHITECTURE.md §14 invariant 5), and we use
`sympy.Rational` to stay consistent with the verifier (Slice 1.4). There is NO LLM
and NO DB anywhere in this module (CLAUDE.md §8.1/§8.2): the generators are pure
and deterministic — same input, same output, every time, which is what makes the
persona harness reproducible (ARCHITECTURE.md §5 Layer 3).

A note on what these generators are NOT: they are not problem generators (Slice
1.3) and not the answer verifier (Slice 1.4). They take a problem's operands as
input and return the wrong answer a misconception produces; building the problems
and judging correctness are separate, later slices.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from sympy import Add, Mul, Pow, Rational, gcd, lcm, sstr, sympify
from sympy.core.relational import (
    GreaterThan,
    LessThan,
    Relational,
    StrictGreaterThan,
    StrictLessThan,
)
from sympy.core.sympify import SympifyError

from app.domain.knowledge_components import KnowledgeComponentId

# A yes/no judgment is the answer type for the relational "are these the same
# amount?" items (the gem bank's `type: yes_no`). Aliased for readability.
YesNo = Literal["yes", "no"]

# The FIXED number-set label vocabulary for KC_classify_number_sets (TEKS 6.2A), ordered SMALL set
# → LARGE set: natural ⊂ whole ⊂ integer ⊂ rational. The single source of truth for which labels
# exist and their canonical order; the generator, verifier, and worked example all read it so a
# typed/parsed answer is compared against the same vocabulary. No LLM ever decides membership — it
# is computed from the value with SymPy (``classify_sets_for_value``). Grade-6 scope: every value
# in this lesson is rational, so "rational" is the outermost set every number belongs to.
NUMBER_SET_LABELS: tuple[str, ...] = ("natural", "whole", "integer", "rational")


class MisconceptionId(StrEnum):
    """Stable misconception identifiers, matching the gem bank verbatim.

    The string VALUES match `diagnostic_gems.json` `_meta.misconception_catalog`
    exactly; they are the join key between this module, the bank, and the persona
    configs (Layer 2). As with ``KnowledgeComponentId``, ``StrEnum`` lets a member
    serialize as its catalog string while still giving typed code a real handle.
    Changing a VALUE is a breaking change to that contract.
    """

    NATURAL_NUMBER_BIAS = "natural-number-bias"
    ADD_ACROSS_ERROR = "add-across-error"
    REDUCE_MEANS_SMALLER = "reduce-means-smaller"
    EQUAL_SIGN_AS_PROCEDURAL = "equal-sign-as-procedural"
    PROCEDURE_WITHOUT_CONCEPT = "procedure-without-concept"
    # Grade-6 content build (2026-05-30): misconceptions for the new KCs are NOT in the
    # fraction-only diagnostic_gems bank — they enter with their lesson (the bank's verbatim
    # match holds only for the five fraction misconceptions above).
    RATE_INVERSION = "rate-inversion"
    ADDITIVE_RATIO = "additive-ratio"
    PERCENT_AS_AMOUNT = "percent-as-amount"
    # Unit 2 (T2): treating fraction multiplication like addition (x as +).
    MULTIPLY_AS_ADD = "multiply-as-add"
    # Unit 1: applying the conversion factor upside-down — dividing (or flipping the factor)
    # when converting to the SMALLER unit, where you should multiply.
    CONVERSION_INVERSION = "conversion-inversion"
    # Unit 1 (6.RP.1): confusing a part-part ratio with a part-whole ratio (and vice versa).
    PART_PART_WHOLE_CONFUSION = "part-part-whole-confusion"
    # Unit 2: swapping the two whole-number aggregates — answering the LCM when the GCF was
    # asked, or the GCF when the LCM was asked.
    GCF_LCM_CONFUSION = "gcf-lcm-confusion"
    # Unit 2 (6.NS.1): dividing fractions by multiplying straight across without inverting.
    MULTIPLY_WITHOUT_INVERTING = "multiply-without-inverting"
    # Unit 2: a long-division place-value slip — the quotient digits are right but misplaced
    # (a dropped/extra zero), so the answer is off by a factor of 10.
    PLACE_VALUE_SLIP = "place-value-slip"
    # Unit 2 (6.NS.3): misplacing the decimal point in a product — the digits are right but the
    # value is off by a power of ten.
    DECIMAL_POINT_MISPLACEMENT = "decimal-point-misplacement"
    # Unit 3 (6.NS.7c): "absolute value of a negative stays negative" — reports the signed value
    # itself instead of its distance from 0 (conflates magnitude with signed order).
    SIGNED_NOT_MAGNITUDE = "signed-not-magnitude"
    # Unit-INT (TEKS 6.3C/D): a sign-handling error on integer addition — combining two
    # opposite-sign numbers by ADDING their magnitudes instead of accounting for the signs.
    SIGN_HANDLING_ERROR = "sign-handling-error"
    # Unit 3 (6.NS.5): a sign error on opposites — leaving the number's sign unchanged instead
    # of flipping it ("the opposite of -7 is -7").
    SIGN_ERROR = "sign-error"
    # Unit 4 (6.EE.2a): writing an expression with the operands reversed on a non-commutative op —
    # "7 less than p" written as 7 - p instead of p - 7 (or n / 3 as 3 / n).
    REVERSED_OPERANDS = "reversed-operands"
    # Unit 4 (6.EE.2c): an order-of-operations slip on evaluating a*x + b — combining left-to-right
    # (multiply after adding) so a*x + b is computed as a*(x + b) instead of honoring precedence.
    ORDER_OF_OPERATIONS_SLIP = "order-of-operations-slip"
    # Unit 5 (6.EE.7): solving a one-step equation with the WRONG inverse — adding instead of
    # subtracting for x + b = c, or subtracting a instead of dividing for a*x = c.
    INVERSE_OPERATION_ERROR = "inverse-operation-error"
    # Unit 4 (6.EE.3): a distributive error — distributing a multiplier onto only the FIRST term of
    # a sum, "3(x + 2)" written as 3x + 2 instead of 3x + 6 (the +2 is left un-multiplied).
    DISTRIBUTIVE_ERROR = "distributive-error"
    # Unit 5 (6.EE.8): a flipped inequality direction — writing the wrong relational direction for a
    # constraint, e.g. "x < 5" for "at least 5" (which is x >= 5), keeping the bound but reversing
    # the comparison.
    FLIPPED_INEQUALITY = "flipped-inequality"
    # Unit 3 (6.NS.8): a coordinate-swap error — plotting/reading a point with its coordinates
    # transposed, putting (x, y) at (y, x) (moving up first, then across, or reflecting across
    # y = x by accident).
    COORDINATE_SWAP = "coordinate-swap"
    # Unit 3 (TEKS 6.2A): classifying an integer WITHOUT marking it rational — not realizing every
    # integer is also a rational number (it can be written as a fraction over 1), so the learner
    # drops "rational" from an integer's set (-3 marked {integer} instead of {integer, rational}).
    INTEGER_NOT_RATIONAL = "integer-not-rational"
    # Unit 4 (6.EE.2b): confusing the parts of an expression — naming the CONSTANT when the
    # COEFFICIENT was asked (4 instead of 7 for "coefficient of x in 7x + 4"), or the coefficient
    # when the constant was asked. The two prominent numbers are swapped.
    PART_CONFUSION = "part-confusion"
    # Unit 4 (6.EE.1): treating a power as one multiplication — multiplying the base BY the
    # exponent (3^4 -> 3*4 = 12) instead of by itself exponent-many times (3*3*3*3 = 81).
    MULTIPLY_BASE_BY_EXPONENT = "multiply-base-by-exponent"
    # Unit-INT (TEKS 6.3C/D): a sign-rule error on integer multiplication/division — computing the
    # right MAGNITUDE but applying the wrong sign rule (e.g. -3 × 4 -> 12 instead of -12, treating
    # the product of an unlike-sign pair as positive). The arithmetic is right; only the sign is.
    SIGN_RULE_ERROR = "sign-rule-error"
    # Unit 6 (TEKS 6.8A): a triangle-formula error — using the WRONG fixed relationship. For a
    # missing angle, subtracting from 90 instead of 180 (treating it like a right-angle complement);
    # for an area, dropping the ½ and answering base × height (the rectangle's area, not the
    # triangle's). The operands are read right; the formula relationship applied is wrong.
    TRIANGLE_FORMULA_ERROR = "triangle-formula-error"
    # Unit 6 (6.G.1): forgot the 1/2 on a triangle — applied the rectangle formula b·h to a
    # triangle instead of 1/2·b·h, so the area comes out twice too big.
    FORGOT_TRIANGLE_HALF = "forgot-triangle-half"
    # Unit 6 (6.G.1): forgot the 1/2 on a trapezoid — answered (base1 + base2)·height instead of
    # AVERAGING the two parallel sides first (1/2·(base1 + base2)·height), so the area is twice too
    # big. The trapezoid analogue of forgot-triangle-half (Slice 4c, U6.L3 trapezoid coverage).
    FORGOT_TRAPEZOID_HALF = "forgot-trapezoid-half"
    # Unit 6 (6.G.2): finding a prism's volume by ADDING the edge lengths (l + w + h) instead of
    # MULTIPLYING them (V = l*w*h) — the wrong operation, so the answer comes out far too small.
    ADD_EDGES_ERROR = "add-edges-error"
    # Unit 6 (6.G.4): counting only three of a prism's six faces — summing l*w + l*h + w*h and
    # forgetting that each face has a matching opposite, so the surface area comes out half-size.
    COUNT_THREE_FACES = "count-three-faces"
    # Unit 7 (6.SP.5c): computing the mean absolute deviation WITHOUT taking absolute values —
    # averaging the SIGNED deviations from the mean instead of their distances. The signed
    # deviations always sum to zero, so this wrong "MAD" is always 0.
    FORGOT_ABSOLUTE_VALUE = "forgot-absolute-value"
    # Unit 7 (6.SP.2): computing a distribution's RANGE by ADDING the extremes (max + min) instead
    # of subtracting them (max - min) — the wrong operation, so the spread comes out far too large.
    RANGE_AS_SUM = "range-as-sum"
    # Unit 7 (6.SP.3): finding the median WITHOUT sorting first — reading the middle value of the
    # data set as it was GIVEN, rather than ordering the values and then taking the center. The
    # learner knows "median = middle" but skips the sort step, so an unordered list gives the
    # wrong center.
    MEDIAN_WITHOUT_SORTING = "median-without-sorting"
    # Unit 7 (6.SP.4): reading a data display by counting how many DIFFERENT values lie above a
    # threshold instead of how many DATA POINTS do — collapsing the duplicate dots stacked over a
    # value into a single count. The learner reads the x-axis (distinct values) rather than the
    # dots (the data points), so an undercount results whenever a value above the threshold repeats.
    DISTINCT_VALUE_COUNT = "distinct-value-count"
    # Unit 7 (TEKS 6.12D): computing a category's RELATIVE FREQUENCY over the WRONG DENOMINATOR —
    # dividing its count by another category's count instead of by the total surveyed (e.g. 8 blue
    # of 25 surveyed reported as 8/12 against the next category, not 8/25). The learner forms a
    # part-to-part ratio where a part-to-whole fraction was asked.
    WRONG_DENOMINATOR = "wrong-denominator"
    # Unit 7 (6.SP.1): treating ANY question that mentions people or numbers as a statistical
    # question — answering "yes" to a single-value question ("How tall is the teacher?") because it
    # is about a person/quantity, missing that a statistical question must anticipate VARIABILITY.
    # NOTE: the YES_NO answer kind does not use the operand-based ``_WRONG_ANSWER_MODELS`` path, so
    # the verifier does NOT classify this id (a wrong yes/no is scored MAGNITUDE / no misconception,
    # like every YES_NO item). It lives here for catalog completeness and hint framing only.
    TREATS_ANY_AS_STATISTICAL = "treats-any-as-statistical"
    # Unit 4/5 (6.EE.9): confusing the dependent/independent relationship — treating the
    # MULTIPLICATIVE rule y = a·x as ADDITIVE, computing a + x instead of a·x ("y = 3x, x = 4"
    # answered 7 instead of 12). The learner reads the rate as something to ADD to the input rather
    # than to multiply it by, so the relationship between the two variables is applied with the
    # wrong operation.
    DEPENDENT_INDEPENDENT_SWAP = "dependent-independent-swap"
    # Unit 5 (6.EE.5): a substitution / isolate-x sign error when solving x + b = c — moving the
    # constant to the other side WITHOUT flipping its sign, so the learner answers c + b instead of
    # c - b ("x + 4 = 9" -> x = 9 + 4 = 13 instead of 9 - 4 = 5). The candidate is tested with the
    # wrong inverse, so the value claimed to make the equation true does not.
    SOLUTION_SUBSTITUTION_ERROR = "solution-substitution-error"
    # Unit 8 (TEKS 6.14C): a sign slip in a check register — ADDING a withdrawal to the running
    # balance instead of subtracting it. The learner treats every transaction as a deposit, so the
    # ending balance comes out too high by twice the withdrawal (a withdrawal of W flips from −W to
    # +W, a 2W swing). The running balance no longer reflects the money actually spent.
    ADD_WITHDRAWAL_INSTEAD_OF_SUBTRACTING = "add-withdrawal-instead-of-subtracting"
    # Unit 8 (TEKS 6.14H): forgetting to multiply by the YEARS when finding lifetime income —
    # answering the annual salary (or the annual income difference) itself instead of the salary
    # times the working years ("$40,000/yr over 30 years" answered 40,000 instead of 1,200,000). The
    # learner reads the per-year figure as the lifetime total, missing that income accumulates over
    # the working years.
    FORGOT_MULTIPLY_BY_YEARS = "forgot-multiply-by-years"


@dataclass(frozen=True)
class Misconception:
    """One named misconception: a documented way learners get fractions wrong.

    Frozen because Layer 1 is a source of truth, not mutable state — nothing
    downstream may rewrite what a misconception *is* at runtime (ARCHITECTURE.md
    §14, CLAUDE.md §8.4). ``applicable_kcs`` is a tuple (not a list) so the object
    is hashable and genuinely immutable; it references ``KnowledgeComponentId`` so
    the misconception and the KC registry speak the same ids.

    The fields are the minimal Slice-1.2 surface: a stable id, human-readable name
    and description (each traceable to RESEARCH.md §1.2), and which KCs the
    misconception can show up on. The wrong-answer *behavior* is the generator
    functions below, not data stored on the object — a misconception's effect
    depends on the specific problem, so it cannot be a fixed field.
    """

    id: MisconceptionId
    name: str
    description: str
    applicable_kcs: tuple[KnowledgeComponentId, ...]


# The five misconceptions, in the gem-bank catalog order (PROJECT.md §4.2,
# RESEARCH.md §1.2). The ``applicable_kcs`` for each reflect how the bank actually
# probes them (RESEARCH.md §6.1 "Items per misconception" table), which in turn
# traces to the persona designs (PROJECT.md §4.2):
#
#   - natural-number-bias is the headline misconception and the umbrella mechanism
#     behind operate-on-parts-separately errors, so it spans comparison/equivalence,
#     common-denominator finding, subtraction, and number-line placement.
#   - add-across-error is reserved strictly for the literal tops+tops / bottoms+
#     bottoms ADDITION error (RESEARCH.md §6.4) — KC_addition_unlike only.
#   - reduce-means-smaller and equal-sign-as-procedural are equivalence-judgment
#     errors (KC_equivalence).
#   - procedure-without-concept can occur on any KC where a procedure can be run
#     rotely; the bank probes it on equivalence, common-denominator, subtraction,
#     and number-line items.
_MISCONCEPTIONS: tuple[Misconception, ...] = (
    Misconception(
        id=MisconceptionId.NATURAL_NUMBER_BIAS,
        name="Natural-number bias",
        description=(
            "Treats a fraction's numerator and denominator as two independent "
            "whole numbers, so a bigger denominator is read as a bigger amount "
            "(believing 1/6 > 1/2 because 6 > 2). Drives magnitude/comparison "
            "errors, number-line misplacement, and the operate-on-the-parts-"
            "separately errors in common-denominator finding and subtraction."
        ),
        applicable_kcs=(
            KnowledgeComponentId.EQUIVALENCE,
            KnowledgeComponentId.COMMON_DENOMINATOR,
            KnowledgeComponentId.SUBTRACTION_UNLIKE,
            KnowledgeComponentId.NUMBER_LINE_PLACEMENT,
        ),
    ),
    Misconception(
        id=MisconceptionId.ADD_ACROSS_ERROR,
        name="Add-across error",
        description=(
            "Adds the numerators and the denominators separately, so "
            "a/b + c/d becomes (a+c)/(b+d) — e.g. 1/4 + 1/4 = 2/8. A special case "
            "of treating the parts as independent whole numbers, reserved here for "
            "the literal addition form."
        ),
        applicable_kcs=(KnowledgeComponentId.ADDITION_UNLIKE,),
    ),
    Misconception(
        id=MisconceptionId.REDUCE_MEANS_SMALLER,
        name="Reduce-means-smaller",
        description=(
            "Believes that naming a fraction with smaller numbers (e.g. simplifying "
            "6/8 to 3/4) makes it a smaller amount, so two equal fractions written "
            "differently are judged unequal."
        ),
        applicable_kcs=(KnowledgeComponentId.EQUIVALENCE,),
    ),
    Misconception(
        id=MisconceptionId.EQUAL_SIGN_AS_PROCEDURAL,
        name="Equal-sign-as-procedural",
        description=(
            "Reads '=' as 'compute and write the answer' rather than as a relational "
            "'these name the same amount'. On an 'are these the same?' item there is "
            "nothing to compute, so the learner has no procedure to run and defaults "
            "to 'no'."
        ),
        applicable_kcs=(KnowledgeComponentId.EQUIVALENCE,),
    ),
    Misconception(
        id=MisconceptionId.PROCEDURE_WITHOUT_CONCEPT,
        name="Procedure-without-concept",
        description=(
            "Runs a memorized algorithm correctly but cannot say why it works, "
            "cannot judge whether an answer is reasonable, and fails error-finding "
            "items. Produces the CORRECT numeric answer on routine items — the "
            "tell is the missing justification, not a wrong number."
        ),
        applicable_kcs=(
            KnowledgeComponentId.EQUIVALENCE,
            KnowledgeComponentId.COMMON_DENOMINATOR,
            KnowledgeComponentId.ADDITION_UNLIKE,
            KnowledgeComponentId.SUBTRACTION_UNLIKE,
            KnowledgeComponentId.NUMBER_LINE_PLACEMENT,
        ),
    ),
    Misconception(
        id=MisconceptionId.RATE_INVERSION,
        name="Rate inversion",
        description=(
            "Forms the rate with the quantities upside-down — divides the per-unit "
            "count by the total instead of the total by the count, so '$6 for 3 lbs' "
            "becomes 3/6 = $0.50 per lb instead of 6/3 = $2 per lb. The learner sets up "
            "the ratio but loses track of which quantity is 'per 1'."
        ),
        applicable_kcs=(KnowledgeComponentId.UNIT_RATE,),
    ),
    Misconception(
        id=MisconceptionId.ADDITIVE_RATIO,
        name="Additive ratio reasoning",
        description=(
            "Scales a ratio by ADDING the same amount to both terms instead of "
            "MULTIPLYING — so 3:4 = ?:12 becomes 11 (add 8 to each) rather than 9 "
            "(multiply by 3). The classic additive-vs-multiplicative error: the learner "
            "preserves the difference instead of the multiplicative relationship."
        ),
        applicable_kcs=(KnowledgeComponentId.EQUIVALENT_RATIOS,),
    ),
    Misconception(
        id=MisconceptionId.PERCENT_AS_AMOUNT,
        name="Percent as amount",
        description=(
            "Reports the percent NUMBER itself as the answer instead of computing that "
            "percent OF the whole — '30% of 50' becomes 30, not 15. The learner does not "
            "engage the base; the percent is read as an absolute count."
        ),
        applicable_kcs=(KnowledgeComponentId.PERCENT,),
    ),
    Misconception(
        id=MisconceptionId.MULTIPLY_AS_ADD,
        name="Multiply as add",
        description=(
            "Treats fraction multiplication like addition: instead of multiplying the "
            "numerators and denominators (2/3 x 3/4 = 6/12), the learner adds the fractions "
            "(2/3 + 3/4). The operation is confused, so the result is too big — a product of "
            "two proper fractions is smaller than either factor, never larger."
        ),
        applicable_kcs=(KnowledgeComponentId.MULTIPLY_FRACTIONS,),
    ),
    Misconception(
        id=MisconceptionId.CONVERSION_INVERSION,
        name="Conversion-factor inversion",
        description=(
            "Applies the conversion factor the wrong way round when converting to the smaller "
            "unit: DIVIDES by the factor (or flips it) instead of multiplying, so '4 feet' at "
            "12 inches per foot becomes 4/12 instead of 4 x 12 = 48. The learner has the right "
            "factor but loses track of which way the conversion goes."
        ),
        applicable_kcs=(KnowledgeComponentId.UNIT_CONVERSION,),
    ),
    Misconception(
        id=MisconceptionId.PART_PART_WHOLE_CONFUSION,
        name="Part-part vs part-whole confusion",
        description=(
            "Confuses a part-to-part ratio with a part-to-whole ratio — in either direction. "
            "Asked for the part-OF-the-whole (3 red of 8 total = 3/8), the learner reports the "
            "part-TO-part comparison instead (3 red to 5 blue = 3/5); asked for the part-to-part "
            "ratio, the learner reports the part-of-the-whole fraction. Both quantities are "
            "legitimate ratios, but they answer different questions — the learner loses track of "
            "whether the comparison is against the other part or the whole."
        ),
        applicable_kcs=(KnowledgeComponentId.RATIO_LANGUAGE,),
    ),
    Misconception(
        id=MisconceptionId.GCF_LCM_CONFUSION,
        name="GCF/LCM confusion",
        description=(
            "Swaps the two whole-number aggregates: answers the LEAST COMMON MULTIPLE when "
            "the GREATEST COMMON FACTOR was asked (e.g. gives 36 for 'GCF of 12 and 18' instead "
            "of 6), or the GCF when the LCM was asked. The learner can compute both but loses "
            "track of which one the question wants — factors (what divides into both) versus "
            "multiples (what both divide into)."
        ),
        applicable_kcs=(KnowledgeComponentId.GCF_LCM,),
    ),
    Misconception(
        id=MisconceptionId.MULTIPLY_WITHOUT_INVERTING,
        name="Multiply without inverting",
        description=(
            "Divides fractions by multiplying straight across without inverting the divisor: "
            "a/b ÷ c/d is done as a/b × c/d (so 1/2 ÷ 3/4 becomes 3/8 instead of the correct "
            "1/2 × 4/3 = 2/3). The learner skips the 'flip the second fraction' step — running "
            "the multiplication procedure on the division problem unchanged."
        ),
        applicable_kcs=(KnowledgeComponentId.DIVIDE_FRACTIONS,),
    ),
    Misconception(
        id=MisconceptionId.PLACE_VALUE_SLIP,
        name="Place-value slip",
        description=(
            "Computes the right quotient digits but misplaces them by one place — drops or adds "
            "a zero in the quotient, so the answer is off by a factor of 10 (e.g. gives 4 or 400 "
            "for 240 / 6 instead of 40). The division procedure is sound; the learner loses track "
            "of place value, so the magnitude is wrong while the digits are right."
        ),
        applicable_kcs=(KnowledgeComponentId.MULTI_DIGIT_DIVISION,),
    ),
    Misconception(
        id=MisconceptionId.DECIMAL_POINT_MISPLACEMENT,
        name="Decimal point misplacement",
        description=(
            "Multiplies the digits correctly but places the decimal point in the product by the "
            "wrong count — using only the longer factor's decimal places instead of the SUM of "
            "both — so 0.5 x 0.4 (one place each, two in the product) becomes 2.0 instead of "
            "0.20. The DIGITS are right; the value is off by a power of ten (a magnitude error)."
        ),
        applicable_kcs=(KnowledgeComponentId.DECIMAL_OPERATIONS,),
    ),
    Misconception(
        id=MisconceptionId.SIGNED_NOT_MAGNITUDE,
        name="Signed value, not magnitude",
        description=(
            "Treats absolute value as 'leave the number as it is' rather than its DISTANCE from "
            "0, so the absolute value of a negative stays negative — gives -7 for |-7| instead of "
            "7. The learner conflates the magnitude (how far from 0) with the signed number and "
            "its order on the line; a magnitude can never be negative."
        ),
        applicable_kcs=(KnowledgeComponentId.ABSOLUTE_VALUE,),
    ),
    Misconception(
        id=MisconceptionId.SIGN_HANDLING_ERROR,
        name="Sign-handling error",
        description=(
            "Combines two opposite-sign integers by ADDING their magnitudes and ignoring the "
            "signs — treats -5 + 3 like 5 + 3 = 8 instead of -2. The learner applies whole-number "
            "addition to the magnitudes rather than reasoning about direction on the number line, "
            "so the result is too big (its magnitude is |a| + |b|, never the smaller |a + b|)."
        ),
        applicable_kcs=(KnowledgeComponentId.INTEGER_ADD_SUBTRACT,),
    ),
    Misconception(
        id=MisconceptionId.SIGN_ERROR,
        name="Sign error on opposites",
        description=(
            "Leaves a number's sign unchanged when asked for its opposite — 'the opposite of "
            "-7 is -7', or returns 7 for the opposite of 7. The magnitude is right but the "
            "negation (flipping the sign across zero) was never applied, so the answer is the "
            "original number instead of its opposite."
        ),
        applicable_kcs=(KnowledgeComponentId.SIGNED_NUMBERS,),
    ),
    Misconception(
        id=MisconceptionId.REVERSED_OPERANDS,
        name="Reversed operands",
        description=(
            "Writes the expression with the two operands in the wrong order on a non-commutative "
            "operation — 'p less than 7' phrasing trips the learner into 7 - p when the phrase '7 "
            "less than p' means p - 7, or 'n divided by 3' into 3 / n. The learner translates the "
            "words left-to-right instead of by the operation's meaning, so the OPERATION is set up "
            "backwards. Harmless on commutative ops (p + 7 == 7 + p), with no wrong order."
        ),
        applicable_kcs=(KnowledgeComponentId.WRITE_EXPRESSIONS,),
    ),
    Misconception(
        id=MisconceptionId.ORDER_OF_OPERATIONS_SLIP,
        name="Order-of-operations slip on evaluation",
        description=(
            "Evaluates a*x + b by combining left-to-right instead of by precedence — adds before "
            "multiplying, computing a*(x + b) rather than a*x + b. 'Evaluate 3x + 2 when x = 4' "
            "becomes 3*(4 + 2) = 18 instead of 3*4 + 2 = 14. The substitution is right; the "
            "OPERATION order is wrong (multiplication should happen before the addition)."
        ),
        applicable_kcs=(KnowledgeComponentId.EVALUATE_EXPRESSIONS,),
    ),
    Misconception(
        id=MisconceptionId.INVERSE_OPERATION_ERROR,
        name="Wrong inverse operation",
        description=(
            "Solves a one-step equation by applying the WRONG inverse — for 'x + 5 = 12' the "
            "learner ADDS 5 (getting 17) instead of subtracting it, and for '3x = 12' they "
            "SUBTRACT 3 (getting 9) instead of dividing. The learner reaches for the operation "
            "they SEE in the equation rather than the one that undoes it, so the procedure for "
            "isolating x is run backwards and x is never actually isolated."
        ),
        applicable_kcs=(KnowledgeComponentId.ONE_STEP_EQUATIONS,),
    ),
    Misconception(
        id=MisconceptionId.DISTRIBUTIVE_ERROR,
        name="Distributive error",
        description=(
            "Distributes a multiplier onto only the FIRST term of a sum, leaving the rest "
            "un-multiplied — '3(x + 2)' written as 3x + 2 instead of 3x + 6. The learner applies "
            "the factor to the variable term but forgets it must also reach the constant (and any "
            "further term), so the OPERATION (distribution) is applied incompletely. Harmless on a "
            "single-term product (3 * x has nothing else to reach), where there is no wrong form."
        ),
        applicable_kcs=(KnowledgeComponentId.EQUIVALENT_EXPRESSIONS,),
    ),
    Misconception(
        id=MisconceptionId.FLIPPED_INEQUALITY,
        name="Flipped inequality",
        description=(
            "Writes the inequality pointing the WRONG way — 'x < 5' for 'a number is at least 5' "
            "(which is x >= 5), or 'x > 13' for 'under 13' (x < 13). The learner keeps the "
            "boundary value but reverses the comparison direction, often by translating the words "
            "left-to-right rather than reasoning about which side of the bound the values fall on, "
            "so the OPERATION (the relation) points the wrong way."
        ),
        applicable_kcs=(KnowledgeComponentId.INEQUALITIES,),
    ),
    Misconception(
        id=MisconceptionId.COORDINATE_SWAP,
        name="Coordinate swap",
        description=(
            "Plots or reads a point with its two coordinates transposed — putting (x, y) at "
            "(y, x). The learner moves up the y-axis first and then across, or reflects the point "
            "across the line y = x by accident, so the ordered pair's ORDER is reversed. Harmless "
            "for a point already on y = x (e.g. (3, 3)), where swapping changes nothing."
        ),
        # Applies to BOTH coordinate KCs: KC_coordinate_plane (6.NS.8) and
        # KC_polygons_coordinate_plane (6.G.3, where transposing the missing rectangle corner is the
        # same axis-order confusion).
        applicable_kcs=(
            KnowledgeComponentId.COORDINATE_PLANE,
            KnowledgeComponentId.POLYGONS_COORDINATE_PLANE,
        ),
    ),
    Misconception(
        id=MisconceptionId.INTEGER_NOT_RATIONAL,
        name="Integer is not rational",
        description=(
            "Classifies an integer without marking it rational — not realizing every integer is a "
            "rational number (it can be written as a fraction over 1), so 'rational' is dropped "
            "from the set: -3 marked {integer} instead of {integer, rational}, or 5 marked "
            "{natural, whole, integer} without rational. The CONCEPT of the nested subsets "
            "(integer ⊂ rational) is incomplete. Harmless on a value that is not an integer (a "
            "non-integer rational is already rational-only — there is no integer label to keep)."
        ),
        applicable_kcs=(KnowledgeComponentId.CLASSIFY_NUMBER_SETS,),
    ),
    Misconception(
        id=MisconceptionId.PART_CONFUSION,
        name="Confuses coefficient and constant",
        description=(
            "Confuses the parts of an expression — names the CONSTANT when the COEFFICIENT was "
            "asked, or the coefficient when the constant was asked. 'The coefficient of x in "
            "7x + 4' answered as 4 (the constant) instead of 7, or the constant of 6x + 9 "
            "answered as 6 (the coefficient) instead of 9. The two prominent numbers are swapped: "
            "the learner reads the wrong part of the expression. Does not apply to a term-count "
            "question, which has no coefficient/constant to swap."
        ),
        applicable_kcs=(KnowledgeComponentId.EXPRESSION_PARTS,),
    ),
    Misconception(
        id=MisconceptionId.MULTIPLY_BASE_BY_EXPONENT,
        name="Multiply the base by the exponent",
        description=(
            "Reads a power as a single multiplication of the base BY the exponent — 3^4 computed "
            "as 3 x 4 = 12 instead of 3 x 3 x 3 x 3 = 81. The exponent is treated as a factor to "
            "multiply once, not as the COUNT of how many times the base is multiplied by itself, "
            "so the answer is base x exponent rather than the repeated product."
        ),
        applicable_kcs=(KnowledgeComponentId.EXPONENTS,),
    ),
    Misconception(
        id=MisconceptionId.SIGN_RULE_ERROR,
        name="Sign-rule error on multiply/divide",
        description=(
            "Multiplies or divides the magnitudes correctly but applies the wrong sign rule — "
            "treats an unlike-sign pair as positive (or a like-sign pair as negative), so -3 × 4 "
            "becomes 12 instead of -12, or -12 ÷ -4 becomes -3 instead of 3. The arithmetic is "
            "right; only the sign of the result is wrong (like signs give a positive result, "
            "unlike signs a negative one)."
        ),
        applicable_kcs=(KnowledgeComponentId.INTEGER_MULTIPLY_DIVIDE,),
    ),
    Misconception(
        id=MisconceptionId.TRIANGLE_FORMULA_ERROR,
        name="Triangle-formula error",
        description=(
            "Applies the wrong fixed relationship for a triangle. For a missing angle, subtracts "
            "the two known angles from 90 instead of 180 — as if the angles totaled a right angle "
            "rather than a straight one. For an area, drops the ½ and answers base × height (the "
            "area of a rectangle, twice the triangle's). The numbers are read correctly; the "
            "formula relationship is wrong."
        ),
        applicable_kcs=(KnowledgeComponentId.TRIANGLE_PROPERTIES,),
    ),
    Misconception(
        id=MisconceptionId.FORGOT_TRIANGLE_HALF,
        name="Forgot the one-half on a triangle",
        description=(
            "Computes a triangle's area with the rectangle formula base x height instead of one "
            "half base x height — a triangle of base 8 and height 3 answered as 24 instead of 12. "
            "The base x height is the bounding parallelogram; a triangle is HALF of it, so the "
            "answer comes out exactly twice too big (the 1/2 was dropped). Does not apply to a "
            "parallelogram/rectangle item, where base x height IS the area."
        ),
        applicable_kcs=(KnowledgeComponentId.AREA_POLYGONS,),
    ),
    Misconception(
        id=MisconceptionId.FORGOT_TRAPEZOID_HALF,
        name="Forgot the one-half on a trapezoid",
        description=(
            "Computes a trapezoid's area as (base1 + base2) x height instead of one half "
            "(base1 + base2) x height — it sums the two parallel sides and multiplies by the "
            "height but never AVERAGES the bases. A trapezoid's area uses the average of the two "
            "parallel sides, so dropping the 1/2 makes the answer exactly twice too big. Does not "
            "apply to a triangle or parallelogram item (a different formula)."
        ),
        applicable_kcs=(KnowledgeComponentId.AREA_POLYGONS,),
    ),
    Misconception(
        id=MisconceptionId.ADD_EDGES_ERROR,
        name="Adds the edges instead of multiplying",
        description=(
            "Finds a right rectangular prism's volume by ADDING the edge lengths (l + w + h) "
            "instead of MULTIPLYING them (V = l*w*h) — confuses volume with a perimeter-style sum, "
            "so the answer comes out far too small (3/2 + 2 + 5/2 = 6 rather than 3/2 * 2 * 5/2 = "
            "15/2). The wrong operation, not a magnitude slip; the edges are read correctly."
        ),
        applicable_kcs=(KnowledgeComponentId.VOLUME_FRACTIONAL_EDGES,),
    ),
    Misconception(
        id=MisconceptionId.COUNT_THREE_FACES,
        name="Counts only three of the six faces",
        description=(
            "Finds a prism's surface area by adding only ONE face from each pair — l*w + l*h + "
            "w*h — and forgets that every face has a matching opposite, so the doubling is "
            "dropped (a 2x3x4 prism answered 26 instead of 2*(6 + 8 + 12) = 52). The face areas "
            "are read correctly; the wrong operation (not multiplying the three-face total by 2) "
            "makes the answer come out exactly half the true surface area."
        ),
        applicable_kcs=(KnowledgeComponentId.SURFACE_AREA_NETS,),
    ),
    Misconception(
        id=MisconceptionId.FORGOT_ABSOLUTE_VALUE,
        name="Forgets the absolute value in the MAD",
        description=(
            "Computes the mean absolute deviation WITHOUT taking the absolute value of each "
            "deviation — averaging the SIGNED differences from the mean instead of their "
            "distances. Because the deviations from the mean always sum to zero, this wrong "
            "'MAD' is always 0 (for {2, 4, 6, 8}: the signed deviations -3, -1, 1, 3 average to "
            "0 instead of the true MAD of 2). The deviations are computed correctly; the wrong "
            "operation (skipping the absolute value) collapses the spread to nothing."
        ),
        applicable_kcs=(KnowledgeComponentId.MEAN_ABSOLUTE_DEVIATION,),
    ),
    Misconception(
        id=MisconceptionId.RANGE_AS_SUM,
        name="Computes the range as max + min",
        description=(
            "Finds a distribution's range by ADDING the largest and smallest values (max + min) "
            "instead of subtracting them (max - min) — e.g. answering 14 for the range of 3, 5, 9, "
            "11 instead of 11 - 3 = 8. The extremes are identified correctly; the wrong operation "
            "(addition for subtraction) makes the reported spread far too large."
        ),
        applicable_kcs=(KnowledgeComponentId.CENTER_SPREAD_SHAPE,),
    ),
    Misconception(
        id=MisconceptionId.MEDIAN_WITHOUT_SORTING,
        name="Takes the middle without sorting first",
        description=(
            "Finds the median by reading the middle value of the data set AS GIVEN, skipping the "
            "ordering step (for 3, 9, 5 answers the middle entry 9 instead of sorting to 3, 5, 9 "
            "and reading 5). The learner knows 'median = the middle' but forgets that the middle "
            "is the center of the SORTED list, so an unordered list yields the wrong center."
        ),
        applicable_kcs=(KnowledgeComponentId.SUMMARY_STATISTICS,),
    ),
    Misconception(
        id=MisconceptionId.DISTINCT_VALUE_COUNT,
        name="Counts distinct values, not data points",
        description=(
            "Reads a data display by counting how many DIFFERENT values lie above the threshold "
            "instead of how many DATA POINTS do — for dots stacked over 6, 6, 8 above a cutoff of "
            "5 answers 2 (the distinct values 6 and 8) instead of 3 (the three dots). The learner "
            "reads the x-axis labels rather than the dots, so a repeated value above the threshold "
            "is undercounted."
        ),
        applicable_kcs=(KnowledgeComponentId.DATA_DISPLAYS,),
    ),
    Misconception(
        id=MisconceptionId.WRONG_DENOMINATOR,
        name="Relative frequency over the wrong denominator",
        description=(
            "Computes a category's relative frequency by dividing its count by ANOTHER category's "
            "count rather than by the total surveyed (8 blue out of 25 reported as 8/12 against "
            "the next category, not 8/25). The learner forms a part-to-part ratio where a "
            "part-to-whole fraction — count over the whole survey total — was asked."
        ),
        applicable_kcs=(KnowledgeComponentId.CATEGORICAL_DATA,),
    ),
    Misconception(
        id=MisconceptionId.TREATS_ANY_AS_STATISTICAL,
        name="Treats any question about people or numbers as statistical",
        description=(
            "Answers 'yes, it is a statistical question' for ANY question that mentions people or "
            "quantities, even one with a single fixed answer ('How tall is the teacher?'). The "
            "learner anchors on the topic (people/numbers) instead of the defining feature — a "
            "statistical question anticipates VARIABILITY, so its answers vary across the data."
        ),
        applicable_kcs=(KnowledgeComponentId.STATISTICAL_QUESTIONS,),
    ),
    Misconception(
        id=MisconceptionId.DEPENDENT_INDEPENDENT_SWAP,
        name="Confuses the dependent/independent relationship",
        description=(
            "Applies the rule relating two variables with the WRONG operation — treats a "
            "multiplicative relationship y = a·x as additive, so 'y = 3x, find y when x = 4' "
            "becomes 3 + 4 = 7 instead of 3 × 4 = 12. The learner reads the rate as something to "
            "ADD to the input rather than to multiply it by, mishandling how the dependent "
            "variable depends on the independent one."
        ),
        applicable_kcs=(KnowledgeComponentId.DEPENDENT_VARS,),
    ),
    Misconception(
        id=MisconceptionId.SOLUTION_SUBSTITUTION_ERROR,
        name="Wrong-sign substitution when testing a solution",
        description=(
            "Solves x + b = c by moving the constant to the other side WITHOUT flipping its sign — "
            "answering c + b instead of c - b ('x + 4 = 9' gives x = 9 + 4 = 13 instead of "
            "9 - 4 = 5). The learner substitutes / isolates x with the wrong inverse, so the value "
            "they claim makes the equation true does not actually balance it."
        ),
        applicable_kcs=(KnowledgeComponentId.EQUATION_SOLUTIONS,),
    ),
    Misconception(
        id=MisconceptionId.ADD_WITHDRAWAL_INSTEAD_OF_SUBTRACTING,
        name="Adds a withdrawal instead of subtracting it",
        description=(
            "Treats every check-register entry as money coming IN — adding a withdrawal to the "
            "running balance instead of subtracting it. The ending balance ends up too high (a "
            "withdrawal of 20 raises the balance by 20 rather than lowering it), because the "
            "learner ignores that a withdrawal takes money out of the account."
        ),
        applicable_kcs=(KnowledgeComponentId.CHECK_REGISTER,),
    ),
    Misconception(
        id=MisconceptionId.FORGOT_MULTIPLY_BY_YEARS,
        name="Forgets to multiply income by the years",
        description=(
            "Reads the annual salary as the lifetime total — answering the per-year figure (or the "
            "per-year income difference) instead of multiplying it by the number of working years. "
            "'$40,000 a year over 30 years' is reported as 40,000 rather than 1,200,000, missing "
            "that lifetime income accumulates year after year."
        ),
        applicable_kcs=(KnowledgeComponentId.LIFETIME_INCOME,),
    ),
)


class MisconceptionRegistry:
    """The single, ordered, deduplicated home for the five misconceptions.

    Mirrors ``KnowledgeComponentRegistry`` (Slice 1.1): construction enforces id
    uniqueness so a duplicate fails fast at import time; lookups accept either a
    ``MisconceptionId`` or its raw catalog string, because both the bank/DB
    (strings) and typed code (enum) need to resolve a misconception.
    """

    def __init__(self, misconceptions: tuple[Misconception, ...]) -> None:
        by_id: dict[MisconceptionId, Misconception] = {}
        for misconception in misconceptions:
            if misconception.id in by_id:
                raise ValueError(f"Duplicate misconception id: {misconception.id.value}")
            by_id[misconception.id] = misconception
        # Preserve declared (catalog) order for deterministic iteration.
        self._by_id = by_id

    def all(self) -> tuple[Misconception, ...]:
        """Every misconception, in the registry's declared (catalog) order."""
        return tuple(self._by_id.values())

    def get(self, misconception_id: MisconceptionId | str) -> Misconception:
        """Resolve a misconception by enum member or raw catalog string.

        Raises ``KeyError`` naming the offending id on an unknown misconception,
        so callers get a clear failure instead of a silent ``None`` (CLAUDE.md
        §8.5: write for the reader).
        """
        if isinstance(misconception_id, MisconceptionId):
            return self._by_id[misconception_id]
        try:
            resolved = MisconceptionId(misconception_id)
        except ValueError as exc:
            raise KeyError(f"Unknown misconception id: {misconception_id!r}") from exc
        return self._by_id[resolved]


# The module-level registry is the single source of truth referenced across the
# system. Built once at import; immutable contents.
MISCONCEPTION_REGISTRY = MisconceptionRegistry(_MISCONCEPTIONS)


def get_misconception(misconception_id: MisconceptionId | str) -> Misconception:
    """Module-level shortcut for ``MISCONCEPTION_REGISTRY.get`` (the common case)."""
    return MISCONCEPTION_REGISTRY.get(misconception_id)


# ─── Wrong-answer result types ──────────────────────────────────────────────
#
# These small frozen types are what the generators return. They are deliberately
# richer than a bare value so a downstream caller (the persona simulator, the
# tutor's diagnostic log) can see BOTH the raw, possibly-impossible form the
# learner produced AND its rational value. The bank records both (RESEARCH.md
# §6.5: "records both the raw student-produced form and its reduced value"), so
# we preserve both rather than normalizing the impossibility away.


@dataclass(frozen=True)
class WrongFraction:
    """A fraction a learner produced, kept in its RAW (unreduced, possibly-

    impossible) form. The across errors can yield a zero or negative denominator
    (e.g. 1/-3 from subtracting bottoms); that impossibility is the diagnostic
    signal, so we never silently normalize it. ``as_rational`` gives the SymPy
    value for comparison and verification.
    """

    numerator: int
    denominator: int

    def as_rational(self) -> Rational:
        """The SymPy value of this raw fraction (reduces/normalizes sign).

        Used for VALUE comparison against the bank's oracle (e.g. raw 2/8 == 1/4).
        ``Rational`` happily represents a negative denominator as a negative value
        (1/-3 -> -1/3); a zero denominator is genuinely undefined and SymPy raises,
        which correctly surfaces the impossibility rather than hiding it.
        """
        return Rational(self.numerator, self.denominator)


@dataclass(frozen=True)
class NumberLineMisplacement:
    """Where natural-number-bias drops a fraction's marker vs. where it belongs.

    ``true_value`` is the correct position on the 0–1 line; ``biased_position`` is
    where the bias places it by reading the digits (typically the denominator) as
    a whole-number position. The two differing is the whole point.
    """

    true_value: Rational
    biased_position: Rational


@dataclass(frozen=True)
class EqualSignVerdict:
    """The equal-sign-as-procedural answer on a relational same-amount item.

    ``answer`` is the yes/no the learner gives; ``tried_to_compute`` records
    whether they found an operation to run. On a relational item there is nothing
    to compute, so they default to 'no' with ``tried_to_compute=False`` — that is
    the operational-reading signature (RESEARCH.md §1.2; McNeil et al. 2006).
    """

    answer: YesNo
    tried_to_compute: bool


@dataclass(frozen=True)
class ProcedureWithoutConceptResult:
    """The procedure-without-concept marker (PROJECT.md §4.2 Persona 2 — Priya).

    Crucially this is NOT a fabricated wrong number. The procedural learner gets
    the routine answer RIGHT (``answer`` is the correct value), but cannot justify
    it and fails error-finding — so ``can_justify`` is always ``False``. Modeling
    this as a marker, not a wrong value, is the nuance the brief calls out: the
    mastery model must distinguish procedural fluency from conceptual understanding
    (PROJECT.md §3.4, §3.9), and it can only do that if the persona's *answer* is
    correct while a separate flag reports the missing justification.
    """

    answer: object
    can_justify: bool


# ─── Generators ─────────────────────────────────────────────────────────────


def add_across(num1: int, den1: int, num2: int, den2: int) -> WrongFraction:
    """add-across-error: a/b + c/d -> (a+c)/(b+d).

    The learner adds tops and bottoms separately, treating the parts as
    independent whole numbers (RESEARCH.md §1.2; Aksoy & Yazlik 2017; Braithwaite
    & Siegler 2018). E.g. 1/4 + 1/4 -> 2/8, the canonical Surface-Sam error named
    verbatim in PROJECT.md §4.2. The result is returned raw; for 1/2 + 1/4 that is
    2/6 (which reduces to 1/3, smaller than either addend — an impossibility for a
    sum, and exactly the diagnostic tell).
    """
    return WrongFraction(numerator=num1 + num2, denominator=den1 + den2)


def additive_ratio(known_num: int, known_den: int, target_den: int) -> Rational:
    """additive-ratio: scale a:b -> ?:target_den by ADDING (target_den - b) to a, not multiplying.

    The learner preserves the DIFFERENCE instead of the multiplicative relationship, so
    3:4 -> ?:12 gives 3 + (12 - 4) = 11 rather than 3 * 3 = 9. Returned as a Rational so the
    verifier compares values directly (it equals the correct multiplicative answer only in the
    degenerate target_den == 2*b case, which the generator avoids).
    """
    return Rational(known_num + (target_den - known_den))


def part_part_ratio(part: int, other: int) -> Rational:
    """part-part-whole confusion: report the part-TO-part ratio ``part/other`` when the

    part-TO-whole ratio ``part/(part+other)`` was asked. Given "3 red, 5 blue", asked for the
    fraction of counters that are red (3/8), the learner answers the red-to-blue comparison
    instead (3/5). Returned as a SymPy ``Rational`` so the verifier compares values directly; it
    is always distinct from the correct part-whole value because ``other != part + other`` for
    any ``part >= 1``.
    """
    return Rational(part, other)


def part_whole_ratio(part: int, other: int) -> Rational:
    """part-part-whole confusion (the PART-TO-PART direction): report the part-TO-whole fraction

    ``part/(part+other)`` when the part-TO-part ratio ``part/other`` was asked. The mirror of
    ``part_part_ratio``: given "6 green, 2 yellow", asked for the ratio of green to yellow (6/2),
    the learner answers the green-of-all fraction instead (6/8). Returned as a SymPy ``Rational``
    so the verifier compares values directly; always distinct from the correct part-part value
    because ``part+other != other`` for any ``part >= 1`` — the same property, the other way round.
    """
    return Rational(part, part + other)


def invert_rate(total: int, count: int) -> Rational:
    """rate-inversion: form the unit rate upside-down — ``count/total`` not ``total/count``.

    The correct unit rate for ``total`` per ``count`` units is ``total/count`` ("how much for
    ONE"). The learner who inverts divides the other way, getting ``count/total`` — e.g. $6 for
    3 lbs becomes 3/6 = 1/2 instead of 6/3 = 2. Returned as a SymPy ``Rational`` (a rate is a
    single magnitude, not a fraction pair), so the verifier can compare values directly.
    """
    return Rational(count, total)


def invert_conversion(quantity: int, factor: int) -> Rational:
    """conversion-inversion: convert to the smaller unit by DIVIDING by the factor, not multiplying.

    The correct conversion of ``quantity`` larger units to the smaller unit (``factor`` small units
    per large unit) is ``quantity * factor`` ("how many small units"). The learner who inverts
    divides the other way, getting ``quantity/factor`` — e.g. 4 feet at 12 in/ft becomes 4/12 = 1/3
    instead of 48. Returned as a SymPy ``Rational`` so the verifier can compare values directly.
    """
    return Rational(quantity, factor)


def gcf_lcm_confusion(a: int, b: int, *, lcm_asked: bool) -> Rational:
    """gcf-lcm-confusion: answer the OTHER whole-number aggregate of ``a`` and ``b``.

    The learner swaps factors and multiples: when the GCF was asked (``lcm_asked`` False) they
    return ``lcm(a, b)``; when the LCM was asked (``lcm_asked`` True) they return ``gcd(a, b)``.
    SymPy ``gcd``/``lcm`` compute both (domain/ is the one place math correctness lives,
    CLAUDE.md §7). Returned as a ``Rational`` so the verifier compares values directly; equals the
    correct answer only when gcd == lcm (a == b), which the generator avoids.
    """
    other = gcd(a, b) if lcm_asked else lcm(a, b)
    return Rational(int(other))


def multiply_without_inverting(dividend: Rational, divisor: Rational) -> Rational:
    """multiply-without-inverting: do a/b ÷ c/d as a/b × c/d (skip flipping the divisor).

    The correct quotient is ``dividend * (1/divisor)`` — invert the divisor, then multiply. The
    learner who skips the flip multiplies straight across instead, getting ``dividend * divisor``
    — e.g. 1/2 ÷ 3/4 becomes 1/2 × 3/4 = 3/8 instead of 1/2 × 4/3 = 2/3. Returned as a SymPy
    ``Rational`` so the verifier can compare values directly; it differs from the correct quotient
    whenever the divisor is not its own reciprocal (i.e. divisor != 1), which holds for any proper
    divisor c/d with c < d.
    """
    return dividend * divisor


def place_value_slip(dividend: int, divisor: int) -> Rational:
    """place-value-slip: the right quotient digits, off by one place (a factor of 10).

    The correct quotient of an exact division is ``dividend // divisor`` ("how many times the
    divisor fits"). The learner who slips place value writes the same digits with an extra zero —
    ``quotient * 10`` — e.g. 240 / 6 = 40 becomes 400. Returned as a SymPy ``Rational`` so the
    verifier compares values directly; never equals the correct quotient (which is >= 1), so it is
    always a genuinely wrong, magnitude-only error.
    """
    return Rational((dividend // divisor) * 10)


def _decimal_places(value: Rational) -> int:
    """How many decimal places ``value`` needs as a finite decimal (regardless of reduction).

    A reduced rational p/q is a terminating decimal exactly when q's only prime factors are 2
    and 5; the place count is then ``max(exponent of 2, exponent of 5)`` in q — e.g. 1/5 (=0.2)
    → 1, 3/20 (=0.15) → 2, 1/4 (=0.25) → 2, 3 → 0. (SymPy reduces 2/10 to 1/5, so we must NOT
    assume a power-of-ten denominator — we factor q instead.) Raises if q has any other prime
    factor (a non-terminating decimal), which the decimal-operations generator never produces, so
    that would be a bug not learner input — fail loudly per CLAUDE.md §8.5."""
    den = value.q
    twos = fives = 0
    while den % 2 == 0:
        den //= 2
        twos += 1
    while den % 5 == 0:
        den //= 5
        fives += 1
    if den != 1:
        raise ValueError(f"{value} is not a terminating decimal (denominator has other primes)")
    return max(twos, fives)


def decimal_point_misplacement(operands: tuple[Rational, ...]) -> Rational | None:
    """decimal-point-misplacement: place the PRODUCT's point by the LONGER factor's place count.

    The decimal-operations generator encodes an item as ``(first, second, mode)`` where
    ``mode == 0`` (_DECIMAL_MULTIPLY) is a multiplication and 1/2/3 are add/subtract/divide. This is
    MULTIPLY-SPECIFIC — it models mis-placing the *product's* decimal point — so it only applies to
    multiply items; it returns ``None`` for add/subtract/divide (no product to misplace) and for an
    unexpected operand shape (defensive), exactly as ``forget_triangle_half`` returns ``None`` off
    the triangle mode. The verifier then never mislabels a correct or wrong non-multiply answer.

    On a MULTIPLY item the correct product ``first * second`` has ``places(first) + places(second)``
    decimal places. The learner counts only ``max`` of the two instead of the SUM, so the point
    lands too far right — the value is the correct product scaled UP by ``10 ** min(places)`` (a
    power of ten). e.g. 0.5 x 0.4 (one place each): correct 0.20, misplaced 2.0 (x10). The digits
    are right; the magnitude is wrong — which is why the verifier classifies this as a MAGNITUDE
    error. Returned as a SymPy ``Rational`` so the verifier compares values directly.
    """
    if len(operands) != 3:
        return None  # defensive: the verifier then reports OTHER rather than a false match
    first, second, mode = operands
    if mode != 0:  # add/subtract/divide: no product point to misplace, so the error does not apply
        return None
    p1, p2 = _decimal_places(first), _decimal_places(second)
    return Rational(first * second) * (10 ** min(p1, p2))


def percent_as_amount(operands: tuple[Rational, ...]) -> Rational | None:
    """percent-as-amount: report the percent NUMBER itself instead of that percent OF the whole.

    The percent generator encodes an item as ``(percent, whole, mode)`` where ``mode == 0``
    (_PERCENT_OF) asks "what is p% of whole?" and ``mode == 1`` (_PERCENT_FIND_WHOLE) asks
    "{part} is p% of what number?". This error is PERCENT_OF-specific — it models reading the
    percent ``p`` as an absolute count instead of taking it OF the base (30% of 50 -> 30, not 15).
    On the find-the-whole direction there is no "percent OF the whole" to skip (the answer IS the
    whole), so the error does not apply: this returns ``None`` for mode 1 and for an unexpected
    operand shape (defensive), exactly as ``decimal_point_misplacement`` returns ``None`` off the
    multiply mode. The verifier then never mislabels a correct (or otherwise-wrong) find-the-whole
    answer as percent-as-amount. Returned as a SymPy ``Rational`` so the verifier compares values
    directly; the generator excludes whole == 100, so on a PERCENT_OF item ``p`` always differs from
    the correct ``p*whole/100``.
    """
    if len(operands) != 3:
        return None  # defensive: the verifier then reports OTHER rather than a false match
    percent, _whole, mode = operands
    if mode != 0:  # find-the-whole: no "percent OF the whole" to skip, so the error does not apply
        return None
    return percent


def signed_not_magnitude(value: int) -> Rational:
    """signed-not-magnitude: report the signed value itself instead of its distance from 0.

    The correct absolute value is ``abs(value)`` ("how far from 0"). The learner who thinks the
    absolute value of a negative stays negative just returns ``value`` unchanged — e.g. -7 for
    |-7| instead of 7. Returned as a SymPy ``Rational`` so the verifier compares values directly;
    it differs from ``abs(value)`` for any negative input (which the generator guarantees).
    """
    return Rational(value)


def add_magnitudes_ignoring_sign(a: Rational, b: Rational) -> Rational:
    """sign-handling-error: combine two integers by ADDING their magnitudes, ignoring the signs.

    The correct integer sum is ``a + b`` (direction matters). The learner who makes the sign error
    treats it like whole-number addition of the magnitudes, getting ``|a| + |b|`` — e.g. -5 + 3
    becomes 5 + 3 = 8 instead of -2. Returned as a SymPy ``Rational`` so the verifier compares
    values directly; for OPPOSITE-sign operands ``|a| + |b| > |a + b|`` always, so it is always a
    distinct, wrong value.
    """
    return abs(a) + abs(b)


# KC_summary_statistics (6.SP.3) encodes its variable-length item as ``operands = (mode_code,
# *data)`` — a leading sentinel stat-mode code followed by the data values. This is the canonical
# code map (problem_generators re-exports it as ``_SUMMARY_STAT_MODE_CODE``); the median
# misconception below decodes the mode to know when it applies.
SUMMARY_STAT_MODE_CODE: dict[str, int] = {"mean": 0, "median": 1, "mode": 2, "range": 3}


def unsorted_middle(operands: tuple[Rational, ...]) -> Rational | None:
    """median-without-sorting: read the middle of the UNSORTED data, skipping the sort (6.SP.3).

    The summary-statistics item is encoded as ``operands = (mode_code, *data)`` (a leading stat-mode
    sentinel; see ``SUMMARY_STAT_MODE_CODE``). This error is median-specific: the learner takes the
    center of the list AS GIVEN instead of sorting first — for 3, 9, 5 they read the middle entry 9
    rather than the true median 5 (sorted 3, 5, 9). Returns the middle of the raw (unsorted) data
    for a MEDIAN item with an odd-length data set (the generator only emits odd-length median items,
    so "the middle" is a single, unambiguous element). Returns ``None`` for any non-median mode (no
    median to mis-take) and for an unexpected shape (defensive — the verifier then reports OTHER
    rather than a false match). Returned as a SymPy ``Rational`` so the verifier compares values
    directly; whether it differs from the true median depends on the data, so the generator
    guarantees a diagnostic gap on the median items it exercises (the verifier match is only used
    when the values actually differ).
    """
    if not operands:
        return None
    mode_code, *data = operands
    if mode_code != SUMMARY_STAT_MODE_CODE["median"]:
        return None
    if len(data) % 2 == 0 or not data:
        return None  # the generator emits only odd-length median items; defensive otherwise
    return data[len(data) // 2]


# KC_data_displays (6.SP.4) encodes its variable-length item as ``operands = (question_code, param,
# *data)`` — a leading question-type sentinel, then a single parameter (the threshold for a
# count-above item; the bin's lower bound for a bin-frequency item; unused/0 for a most-frequent
# item), then the data values that the textual display describes. This is the canonical code map
# (problem_generators re-exports it as ``_DATA_DISPLAY_QUESTION_CODE``); the distinct-value-count
# misconception below decodes the question type to know when it applies.
DATA_DISPLAY_QUESTION_CODE: dict[str, int] = {"count_above": 0, "most_frequent": 1, "bin_freq": 2}


def distinct_value_count(operands: tuple[Rational, ...]) -> Rational | None:
    """distinct-value-count: count DIFFERENT values above the threshold, not DATA POINTS (6.SP.4).

    The data-displays item is encoded as ``operands = (question_code, param, *data)`` (a leading
    question-type sentinel; see ``DATA_DISPLAY_QUESTION_CODE``). This error is count-above-specific:
    asked "how many data points are greater than T", the learner counts how many DIFFERENT values
    exceed T (reading the x-axis labels) instead of how many dots do — for dots at 6, 6, 8 above
    T = 5 they answer 2 (the values 6 and 8) instead of 3 (the three dots). Returns the count of
    DISTINCT data values strictly greater than ``param`` for a count-above item; returns ``None``
    for any other question type (no threshold to mis-count) and for an unexpected shape (defensive —
    the verifier then reports OTHER rather than a false match). Returned as a SymPy ``Rational`` so
    the verifier compares values directly; whether it differs from the true count depends on the
    data, so the generator guarantees a repeated value above the threshold on every count-above
    item it emits (the verifier match is only used when the values actually differ).
    """
    if len(operands) < 3:
        return None
    question_code, threshold, *data = operands
    if question_code != DATA_DISPLAY_QUESTION_CODE["count_above"]:
        return None
    distinct_above = {v for v in data if v > threshold}
    return Rational(len(distinct_above))


# KC_categorical_data (TEKS 6.12D) encodes its variable-length item as ``operands = (mode_code,
# *category_counts)`` — a leading sentinel mode code followed by the per-category counts. This is
# the canonical code map (problem_generators re-exports it as ``_CATEGORICAL_MODE_CODE``); the
# wrong-denominator misconception below decodes the mode to know when it applies.
CATEGORICAL_MODE_CODE: dict[str, int] = {
    "count_difference": 0,
    "total": 1,
    "relative_frequency": 2,
}


def wrong_denominator_relative_frequency(
    operands: tuple[Rational, ...],
) -> Rational | None:
    """wrong-denominator: relative frequency over another category's count, not the total (6.12D).

    The categorical item is encoded as ``operands = (mode_code, *category_counts)`` (a leading
    sentinel; see ``CATEGORICAL_MODE_CODE``). This error is relative-frequency-specific: the
    learner divides the first category's count by the SECOND category's count (a part-to-part
    ratio) instead of by the total surveyed (the part-to-whole fraction) — 8 blue out of 25
    reported as 8/12 against the next category, not 8/25. Returns ``count0 / count1`` for a
    RELATIVE_FREQUENCY item; returns ``None`` for any other mode (no relative frequency asked)
    and for an unexpected shape (defensive — the verifier then reports OTHER rather than a false
    match). Returned as a SymPy ``Rational`` so the verifier compares values directly; the
    generator guarantees ``count1 != total`` (there is always a third category) so the wrong
    denominator differs from the correct one and the match is diagnostic.
    """
    if not operands:
        return None
    mode_code, *counts = operands
    if mode_code != CATEGORICAL_MODE_CODE["relative_frequency"]:
        return None
    if len(counts) < 2 or counts[1] == 0:
        return None  # defensive: need a second category as the (wrong) denominator
    return Rational(counts[0], counts[1])


def keep_original_sign(n: Rational) -> Rational:
    """sign-error: return ``n`` unchanged when its OPPOSITE (``-n``) was asked.

    The opposite of ``n`` flips it across zero (``-n``); the learner who makes the sign error
    leaves the sign as-is and returns ``n`` — 'the opposite of -7 is -7', or 7 for the opposite
    of 7. Returned as a SymPy ``Rational`` so the verifier compares values directly; it differs
    from the correct ``-n`` whenever ``n != 0`` (the generator never produces zero).
    """
    return n


def flip_result_sign(ops: tuple[Rational, ...]) -> Rational:
    """sign-rule-error: compute the right MAGNITUDE but apply the wrong sign on multiply/divide.

    Operands are ``(a, b, mode)`` where ``mode == 1`` is multiplication and ``mode == 0`` is
    division. The correct result is ``a * b`` or ``a / b``; the learner who makes the sign-rule
    error gets the magnitude right but flips the sign — treating an unlike-sign pair as positive
    (or a like-sign pair as negative), so -3 × 4 becomes 12 instead of -12, and -12 ÷ -4 becomes
    -3 instead of 3. Modeled as ``-(correct)`` because flipping the one sign rule negates the
    result regardless of the operands' signs. Returned as a SymPy ``Rational`` so the verifier
    compares values directly; it differs from the correct result whenever that result is nonzero
    (the generator never produces a zero operand, and division always divides evenly, so the
    quotient is a nonzero integer). The generator passes integer-valued operands.
    """
    a, b, mode = ops
    correct = a * b if mode == 1 else Rational(a, b)
    return -correct


def forget_triangle_half(operands: tuple[Rational, ...]) -> Rational | None:
    """forgot-triangle-half: compute a TRIANGLE's area as base x height, dropping the 1/2 (6.G.1).

    The area generator encodes an item as ``(base, height, mode)`` where ``mode == 0`` is a
    TRIANGLE (correct area ``1/2 · base · height``) and ``mode == 1`` is a parallelogram/rectangle
    (correct area ``base · height``). The learner who makes this error reaches for the rectangle
    formula on a triangle — answering ``base · height`` (the bounding parallelogram) instead of
    half of it, so a triangle of base 8 and height 3 becomes 24 instead of 12.

    Returned as a SymPy ``Rational`` so the verifier compares values directly; the un-halved area
    ``base · height`` is always DISTINCT from the correct ``base · height / 2`` because the
    generator keeps base and height positive (so the product is nonzero), making the match always
    diagnostic. Returns ``None`` for the parallelogram mode — ``base · height`` IS the correct
    answer there, so there is no error to model — and for an unexpected operand shape (defensive;
    the verifier then reports OTHER rather than a false match).
    """
    if len(operands) != 3:
        return None  # defensive: a trapezoid's 4-tuple is a different model's job; report OTHER
    base, height, mode = operands
    if mode == 0:  # triangle: answered the bounding parallelogram b·h, dropping the 1/2
        return base * height
    return None  # parallelogram/rectangle: b·h is correct, no half to forget


def forget_trapezoid_half(operands: tuple[Rational, ...]) -> Rational | None:
    """forgot-trapezoid-half: answer (base1 + base2)·height, skipping the averaging 1/2 (6.G.1).

    A trapezoid item is encoded as the 4-tuple ``(base1, base2, height, mode)`` where ``mode == 2``
    (the only mode with two parallel sides). The correct area AVERAGES the bases:
    ``1/2 · (base1 + base2) · height``. The learner who makes this error sums the two bases and
    multiplies by the height but never halves — answering ``(base1 + base2) · height`` — so the
    area comes out exactly twice too big (the trapezoid analogue of forgot-triangle-half).

    Returned as a SymPy ``Rational`` so the verifier compares values directly; the un-halved value
    is always DISTINCT from the correct half because the bases and height are positive (so the sum
    is nonzero). Gated on ARITY and MODE: returns ``None`` for any tuple that is not the
    trapezoid's 4-tuple (the triangle/parallelogram 3-tuple is forget_triangle_half's job) and for
    a non-trapezoid mode (defensive — the verifier then reports OTHER rather than a false match),
    exactly as ``decimal_point_misplacement`` and ``percent_as_amount`` gate on their shape.
    """
    if len(operands) != 4:
        return None  # defensive: triangle/parallelogram 3-tuple (or any other shape) is not ours
    base1, base2, height, mode = operands
    if mode != 2:  # only a trapezoid has two parallel sides to average
        return None
    return (base1 + base2) * height


def evaluate_left_to_right(a: int, x: int, b: int) -> Rational:
    """order-of-operations-slip: evaluate ``a*x + b`` left-to-right as ``a*(x + b)``.

    The learner substitutes correctly but combines the operations in reading order — adding ``x``
    and ``b`` first, then multiplying by ``a`` — instead of honoring precedence (multiply before
    add). 'Evaluate 3x + 2 when x = 4' becomes ``3*(4 + 2) = 18`` rather than ``3*4 + 2 = 14``.
    Returned as a SymPy ``Rational`` so the verifier compares values directly; it differs from the
    correct ``a*x + b`` whenever ``a >= 2`` and ``b >= 1`` (the generator's scope), since then
    ``a*(x + b) - (a*x + b) = (a - 1)*b > 0``.
    """
    return Rational(a * (x + b))


def add_edges_instead_of_multiplying(
    length: Rational, width: Rational, height: Rational
) -> Rational:
    """add-edges-error: find a prism's volume by ADDING the edges instead of multiplying them.

    The volume of a right rectangular prism is ``V = l*w*h``; the learner who makes this error sums
    the three edge lengths (``l + w + h``) — confusing volume with a perimeter-style total — so the
    answer is wrong (3/2 + 2 + 5/2 = 6 rather than 3/2 * 2 * 5/2 = 15/2). Returned as a SymPy
    ``Rational`` so the verifier compares values directly; the generator resamples the one case
    where the sum equals the product, so the summed value always differs from the correct volume
    and the match is always diagnostic.
    """
    return length + width + height


def count_three_faces_only(length: Rational, width: Rational, height: Rational) -> Rational:
    """count-three-faces: find surface area summing only ONE face per pair, dropping the doubling.

    The surface area of a right rectangular prism is ``SA = 2*(l*w + l*h + w*h)`` — six faces in
    three matching pairs. The learner who makes this error adds only one face from each pair
    (``l*w + l*h + w*h``) and forgets the matching opposites, so the answer is exactly HALF the true
    surface area (2x3x4 -> 26 rather than 52). Returned as a SymPy ``Rational`` so the verifier
    compares values directly; since ``l*w + l*h + w*h > 0`` for positive edges, the three-face value
    is always distinct from the correct ``2*(...)`` and the match is always diagnostic.
    """
    return length * width + length * height + width * height


def mean_signed_deviation(data: tuple[Rational, ...]) -> Rational | None:
    """forgot-absolute-value: average the SIGNED deviations from the mean, skipping absolute value.

    The mean absolute deviation is the mean of the |deviations| from the data's mean. The learner
    who makes this error averages the deviations WITHOUT taking absolute values: ``mean(x_i - x̄)``.
    Because the deviations from the mean always sum to zero, this is identically 0 — a clean,
    always-diagnostic wrong value, since the generator only emits data sets with a positive spread
    (the true MAD is > 0). Returned as a SymPy ``Rational`` so the verifier compares values
    directly. ``data`` is the variable-length data set (the problem's operands); returns ``None``
    on an empty set (defensive — the verifier then reports OTHER rather than divide by zero).
    """
    if not data:
        return None
    mean = sum(data, Rational(0)) / len(data)
    return sum((x - mean for x in data), Rational(0)) / len(data)


def multiply_base_by_exponent(base: int, exponent: int) -> Rational:
    """multiply-base-by-exponent: compute a power as ``base * exponent``, not ``base ** exponent``.

    The learner reads ``base^exponent`` as one multiplication of the base by the exponent (3^4 ->
    3*4 = 12) rather than repeated multiplication of the base by itself (3*3*3*3 = 81). Returned
    as a SymPy ``Rational`` so the verifier compares values directly; it differs from the correct
    ``base ** exponent`` for every item in the generator's scope (base >= 2, exponent >= 2, with
    the single ``2^2 == 2*2`` collision excluded), so a match is always diagnostic.
    """
    return Rational(base * exponent)


def add_instead_of_applying_rate(rate: int, value: int) -> Rational:
    """dependent-independent-swap: apply a multiplicative rule y = a·x as ADDITIVE — a + x (6.EE.9).

    For the relationship ``y = rate·x``, the dependent value at ``x = value`` is ``rate * value``.
    The learner who confuses the relationship reads the rate as something to ADD to the input rather
    than to multiply it by, computing ``rate + value`` ("y = 3x at x = 4" -> 3 + 4 = 7 instead of
    3 × 4 = 12). Returned as a SymPy ``Rational`` so the verifier compares values directly; it
    differs from the correct ``rate * value`` for every item in the generator's scope
    (``rate >= 2`` and ``value >= 2`` with the single ``2 + 2 == 2 * 2`` collision excluded), since
    then ``rate * value - (rate + value) = (rate - 1)*(value - 1) - 1 > 0``, so a match is always
    diagnostic.
    """
    return Rational(rate + value)


def inverse_operation_error(operands: tuple[Rational, ...]) -> Rational | None:
    """inverse-operation-error: solve a one-step equation with the WRONG inverse.

    The one-step generator encodes a problem as ``(mode, p, q)``: mode 0 is the additive equation
    ``x + p = q`` (correct ``x = q - p``); mode 1 is the multiplicative equation ``p*x = q``
    (correct ``x = q / p``). The learner who makes this error reaches for the operation they SEE
    rather than its inverse:

    - additive (``x + p = q``): ADDS ``p`` instead of subtracting, getting ``q + p``;
    - multiplicative (``p*x = q``): SUBTRACTS ``p`` instead of dividing, getting ``q - p``.

    Returned as a SymPy ``Rational`` so the verifier compares values directly. The generator
    guarantees this wrong value differs from the correct solution (``p != 0`` for the additive
    case, and an explicit resample for the rare multiplicative coincidence), so the misconception
    is always diagnostic. Returns ``None`` for an unexpected operand shape (defensive; the verifier
    then reports OTHER rather than over-claiming a match).
    """
    if len(operands) != 3:
        return None
    mode, p, q = operands
    if mode == 0:  # x + p = q  ->  added p instead of subtracting it
        return q + p
    if mode == 1:  # p*x = q  ->  subtracted p instead of dividing by it
        return q - p
    return None


def solution_substitution_error(operands: tuple[Rational, ...]) -> Rational | None:
    """solution-substitution-error: a wrong-sign isolate-x error on x + b = c (6.EE.5).

    The equation-solutions SOLVE item encodes its equation as ``(b, c)`` for ``x + b = c`` (correct
    solution ``c - b``). The learner who makes this error moves the constant to the other side
    WITHOUT flipping its sign, answering ``c + b`` ('x + 4 = 9' -> x = 9 + 4 = 13 instead of
    9 - 4 = 5). Returned as a SymPy ``Rational`` so the verifier compares values directly. The
    generator keeps ``b > 0``, so ``c + b`` always differs from the correct ``c - b`` (they coincide
    only at b = 0), making the misconception diagnostic. Returns ``None`` for an unexpected operand
    shape (defensive; the verifier then reports OTHER rather than over-claiming a match).
    """
    if len(operands) != 2:
        return None
    b, c = operands
    return c + b


def add_withdrawal_instead_of_subtracting(operands: tuple[Rational, ...]) -> Rational | None:
    """add-withdrawal-instead-of-subtracting: a check-register sign slip (TEKS 6.14C).

    The check-register ENDING-BALANCE item encodes its data as ``operands = (start,
    *signed_transactions)`` — the starting balance followed by each transaction as a SIGNED amount
    (deposits +, withdrawals −). The correct running balance is the SymPy sum of all of them. The
    learner who makes this error ADDS a withdrawal instead of subtracting it, so the FIRST
    withdrawal (the first negative transaction) flips from ``−W`` to ``+W`` — a ``2W`` swing — so
    the answer is ``correct + 2W``. Returned as a SymPy ``Rational`` so the verifier compares values
    directly; the generator always includes at least one nonzero withdrawal, so ``2W > 0`` and the
    slip always differs from the correct balance (diagnostic). Returns ``None`` if there is no
    withdrawal to flip (defensive; the verifier then reports OTHER rather than over-claiming).
    """
    if len(operands) < 2:
        return None
    correct = sum(operands, Rational(0))
    for amount in operands[1:]:
        if (
            amount < 0
        ):  # the first withdrawal: adding it instead of subtracting is a +2|amount| swing
            return correct - 2 * amount
    return None


def forgot_to_multiply_by_years(operands: tuple[Rational, ...]) -> Rational | None:
    """forgot-multiply-by-years: read the annual figure as the lifetime total (TEKS 6.14H).

    The lifetime-income item encodes its data as ``operands = (mode, *args)``: mode 0 is the
    LIFETIME-INCOME item ``(mode, salary, years)`` (correct ``salary * years``); mode 1 is the
    income-COMPARISON item ``(mode, salary_a, salary_b, years)`` (correct ``(salary_a − salary_b) *
    years``). The learner who makes this error forgets the ``× years`` step and answers the ANNUAL
    figure — the salary itself (mode 0) or the annual difference ``salary_a − salary_b`` (mode 1).
    Returned as a SymPy ``Rational`` so the verifier compares values directly. The generator keeps
    ``years >= 2`` and a positive annual figure, so the un-multiplied value always differs from the
    correct product (diagnostic). Returns ``None`` for an unexpected operand shape (defensive).
    """
    if len(operands) == 3 and operands[0] == 0:  # (mode=0, salary, years) -> answered salary
        return operands[1]
    if len(operands) == 4 and operands[0] == 1:  # (mode=1, a, b, years) -> answered a - b
        return operands[1] - operands[2]
    return None


def confuse_coefficient_with_constant(operands: tuple[Rational, ...]) -> Rational | None:
    """part-confusion: name the wrong number when asked for a part of an expression (6.EE.2b).

    The expression-parts generator encodes an item as ``(mode, coefficient, constant)``: mode 0
    asks for the COEFFICIENT (correct = ``coefficient``), mode 1 asks for the CONSTANT (correct =
    ``constant``), mode 2 asks the TERM COUNT (no coefficient/constant to confuse). The learner who
    makes this error swaps the two prominent numbers:

    - coefficient asked (mode 0): answers the CONSTANT — 4 instead of 7 for "coefficient of x in
      7x + 4";
    - constant asked (mode 1): answers the COEFFICIENT — 6 instead of 9 for "constant of 6x + 9".

    Returned as a SymPy ``Rational`` so the verifier compares values directly. The generator keeps
    ``coefficient != constant``, so the swapped value always differs from the correct answer (the
    match is diagnostic). Returns ``None`` for the term-count mode — the swap does not apply — and
    for an unexpected operand shape (defensive; the verifier then reports OTHER, not a false match).
    """
    if len(operands) != 3:
        return None
    mode, coefficient, constant = operands
    if mode == 0:  # coefficient asked -> answered the constant
        return constant
    if mode == 1:  # constant asked -> answered the coefficient
        return coefficient
    return None  # term-count: no coefficient/constant to swap


def triangle_formula_error(operands: tuple[Rational, ...]) -> Rational | None:
    """triangle-formula-error: apply the WRONG fixed relationship for a triangle (TEKS 6.8A).

    The triangle generator encodes an item as ``(a, b, mode)``: mode 0 finds a MISSING ANGLE from
    two known angles ``a, b`` (correct = ``180 - a - b``); mode 1 finds the AREA from a base ``a``
    and height ``b`` (correct = ``a*b/2``). The learner who makes this error uses the wrong fixed
    relationship:

    - missing angle (mode 0): subtracts from 90 instead of 180 (a right angle, not a straight one),
      getting ``90 - a - b``;
    - area (mode 1): drops the ½ and answers ``a*b`` (the rectangle's area, twice the triangle's).

    Returned as a SymPy ``Rational`` so the verifier compares values directly. Each wrong value
    differs from the correct one by a fixed amount — the angle is off by exactly 90, and the area
    by a factor of 2 (``a, b > 0`` ⇒ ``a*b != a*b/2``) — so the misconception is always diagnostic.
    Returns ``None`` for an unexpected operand shape or mode (defensive; the verifier then reports
    OTHER rather than over-claiming a match).
    """
    if len(operands) != 3:
        return None
    a, b, mode = operands
    if mode == 0:  # missing angle: subtracted from 90 instead of 180
        return 90 - a - b
    if mode == 1:  # area: dropped the ½, answered base × height
        return a * b
    return None


def reversed_operands(correct_expression: str | None) -> str | None:
    """reversed-operands: write a non-commutative expression with its two operands swapped.

    Given the CANONICAL answer string (e.g. ``"p - 7"`` or ``"n/3"``), return the order-reversed
    expression a learner who translates the words left-to-right would write (``"7 - p"``,
    ``"3/n"``). Returns ``None`` when reversing changes nothing — a commutative top-level operation
    (``p + 7`` == ``7 + p``, ``3*n`` == ``n*3``) or anything not a clean two-operand subtraction or
    division — so the verifier never matches an "error" that is actually still correct.

    This is the one place we reason over an expression's STRUCTURE rather than a magnitude; it uses
    SymPy (domain/ owns math, CLAUDE.md §7) and is pure/deterministic. Subtraction ``a - b`` is a
    SymPy ``Add(a, -b)``; division ``a / b`` is a ``Mul(a, b**-1)``. We detect exactly the
    two-term forms the write-expressions generator emits and swap them.
    """
    if correct_expression is None:
        return None
    expr = sympify(correct_expression)

    # Subtraction a - b: an Add of exactly two terms where one carries a negative coefficient.
    if isinstance(expr, Add) and len(expr.args) == 2:
        first, second = expr.args
        # Identify which term is the subtracted one (negative coefficient).
        if second.could_extract_minus_sign() and not first.could_extract_minus_sign():
            a, b = first, -second  # canonical a - b
            return str(sstr(b - a))  # reversed: b - a
        if first.could_extract_minus_sign() and not second.could_extract_minus_sign():
            a, b = second, -first
            return str(sstr(b - a))
        return None  # a + b (both positive) is commutative — no wrong order

    # Division a / b: a Mul containing exactly one inverse power (b ** -1).
    if isinstance(expr, Mul):
        inverse = [arg for arg in expr.args if isinstance(arg, Pow) and arg.exp == -1]
        if len(inverse) == 1:
            denominator = inverse[0].base
            numerator = expr / inverse[0]  # the rest of the product
            return str(sstr(denominator / numerator))  # reversed: b / a
        return None  # plain product a*b is commutative

    return None


# The flipped-direction operator map, on the variable-on-left canonical relational classes: keep
# the bound, reverse the comparison. Strictness is preserved (> <-> <, >= <-> <=) — the error is the
# DIRECTION, not the boundary inclusion (that distinct slip is out of scope for this misconception).
_FLIPPED_RELATION: dict[type[Relational], type[Relational]] = {
    StrictGreaterThan: StrictLessThan,
    StrictLessThan: StrictGreaterThan,
    GreaterThan: LessThan,
    LessThan: GreaterThan,
}


def flipped_inequality(correct_inequality: str | None) -> str | None:
    """flipped-inequality: write the relational pointing the WRONG way, keeping the bound.

    Given the CANONICAL answer string (e.g. ``"x >= 5"`` or ``"x < 13"``), return the
    wrong-direction inequality a learner who reverses the comparison would write (``"x <= 5"``,
    ``"x > 13"``) — same variable, same bound, mirrored operator. Returns ``None`` only when the
    input is not a parseable one-variable relational (so the verifier never matches a fabricated
    error and never crashes on garbage). Always defined for a real inequality, so — unlike the
    commutative-safe ``reversed_operands`` — every generated item has a genuinely wrong flipped
    form.

    Uses SymPy (domain/ owns math, CLAUDE.md §7): ``.canonical`` puts the variable on the left and
    normalizes the operator class, then we swap that class for its mirror and re-render.
    """
    if correct_inequality is None:
        return None
    try:
        parsed = sympify(correct_inequality, evaluate=False)
    except (SympifyError, SyntaxError, TypeError, ValueError, AttributeError, IndexError):
        # IndexError: SymPy's evaluate=False parser raises it on empty / non-expression input.
        return None
    if not isinstance(parsed, Relational) or len(parsed.free_symbols) != 1:
        return None
    canonical = parsed.canonical
    flipped_cls = _FLIPPED_RELATION.get(type(canonical))
    if flipped_cls is None:  # e.g. an equality (Eq) — not a directional inequality
        return None
    flipped = flipped_cls(canonical.lhs, canonical.rhs)
    return str(sstr(flipped))


def distributive_error(source_expression: str | None) -> str | None:
    """distributive-error: distribute a multiplier onto only the FIRST term of a sum.

    Given the GIVEN (un-expanded) expression the learner is asked to rewrite — a product of a
    numeric coefficient and a sum, e.g. ``"3*(x + 2)"`` — return the partially-distributed form a
    learner who forgets to reach the other terms would write (``"3*x + 2"``). Returns ``None`` when
    the source is not a clean ``coeff * (sum of >= 2 terms)`` product (nothing to mis-distribute),
    or when the partial form is coincidentally still equivalent to the full expansion — so the
    verifier never matches an "error" that is actually still correct.

    Like ``reversed_operands`` this reasons over the expression's STRUCTURE with SymPy (domain/
    owns math, CLAUDE.md §7) and is pure/deterministic. A product ``coeff * (a + b + ...)`` is a
    SymPy ``Mul`` whose args are a ``Number`` and an ``Add``; the error multiplies the coefficient
    into only the Add's FIRST term and appends the remaining terms un-multiplied.
    """
    if source_expression is None:
        return None
    # Parse UNEVALUATED so a folded product ``c*(v + b)`` survives as a Mul(coeff, Add) rather than
    # auto-distributing to c*v + c*b on parse — the folded form is what we mis-distribute.
    expr = sympify(source_expression, evaluate=False)

    if not isinstance(expr, Mul):
        return None

    # Split the product into its numeric coefficient and the remaining (non-numeric) factors.
    coeff, rest = expr.as_coeff_Mul()
    if coeff == 1 or not isinstance(rest, Add) or len(rest.args) < 2:
        return None  # not a "number times a (multi-term) sum" — nothing to mis-distribute

    terms = rest.args
    # The error: multiply the coefficient into the first term only; leave the rest untouched.
    partial = coeff * terms[0] + Add(*terms[1:])
    full = expr.expand()  # the CORRECT distribution, for the harmless-case guard
    if partial == full:
        return None  # the partial form is coincidentally still the full expansion
    return str(sstr(partial))


# An integer-coordinate point tuple: "(x,y)" with optional sign and surrounding whitespace. This is
# the ONLY shape a coordinate answer is allowed to take — a strictly-two-integer ordered pair, NOT
# an expression — so parsing never evaluates arbitrary input (CLAUDE.md §8.2). A learner who types a
# decimal, a third coordinate, or a variable produces no match, which the caller scores wrong.
_POINT_LITERAL = re.compile(r"\(\s*([+-]?\d+)\s*,\s*([+-]?\d+)\s*\)")


def parse_points(text: str | None) -> frozenset[tuple[int, int]] | None:
    """Parse a coordinate answer string to a SET of integer ``(x, y)`` points, or ``None``.

    The canonical shape is a comma-separated list of integer-coordinate tuples — a single point
    ``"(2,-1)"`` or a polygon vertex list ``"(0,0),(3,0),(3,2)"``. We match each ``(int, int)``
    tuple with ``_POINT_LITERAL`` (never ``eval``/``sympify`` — a coordinate is two integers, not an
    expression) and collect them into a ``frozenset``, so the answer is ORDER-INSENSITIVE and
    duplicate-free (the verifier grades by set equality; a polygon's vertices match in any order).

    Returns ``None`` when the string is not a clean list of integer points: empty, malformed,
    decimal/variable coordinates, a 1- or 3-tuple, or any leftover non-whitespace text outside the
    matched tuples. Returning ``None`` (never raising) lets the verifier score garbled learner input
    wrong instead of crashing on it (CLAUDE.md §8.2). This is the single source of truth for how a
    coordinate answer string becomes a comparable set — the verifier and the simulator both read it.
    """
    if text is None:
        return None
    matches = list(_POINT_LITERAL.finditer(text))
    if not matches:
        return None
    # Reject trailing junk: everything outside the matched tuples must be commas/whitespace, so a
    # "(1,2,3)" or "(1.5,2)" (which leaves un-matched characters) is rejected rather than half-read.
    leftover = _POINT_LITERAL.sub("", text)
    if leftover.strip(", \t\n"):
        return None
    return frozenset((int(x), int(y)) for x, y in (m.groups() for m in matches))


def swap_coordinates(correct_points: str | None) -> str | None:
    """coordinate-swap: plot/read each point with its two coordinates transposed, (x, y) -> (y, x).

    Given the CANONICAL answer string (e.g. ``"(2,-1)"`` or ``"(0,0),(3,0),(3,2)"``), return the
    coordinate-swapped answer a learner who moves up first then across (or reflects across y = x)
    would produce (``"(-1,2)"``, ``"(0,0),(0,3),(2,3)"``). Returns ``None`` when swapping yields the
    SAME set of points — every point already lies on y = x, or the figure is symmetric across it —
    so the verifier never flags a still-correct answer as the misconception. Returns ``None`` on an
    unparseable canonical string (a construction bug surfaces elsewhere, not here).

    Pure/deterministic, domain-owned (CLAUDE.md §7); it reasons over the point SET, the one place
    this KC's "math" lives. The result is rendered in the same ``(x,y),(x,y)`` shape the generator
    emits so the verifier can re-parse it through ``parse_points``.
    """
    original = parse_points(correct_points)
    if original is None:
        return None
    swapped = frozenset((y, x) for (x, y) in original)
    if swapped == original:
        return None  # symmetric across y = x — swapping changes nothing, so there is no wrong form
    # Render in a stable order so the output is deterministic (the verifier re-parses to a set, so
    # order does not affect correctness; we sort only for reproducibility, PROJECT.md §4.1).
    return ",".join(f"({x},{y})" for x, y in sorted(swapped))


def classify_sets_for_value(value: Rational) -> tuple[str, ...]:
    """The number SETS a rational ``value`` belongs to, ordered small → large (TEKS 6.2A).

    The single source of truth for membership — the generator and verifier both read it, so the
    "correct answer" is one computed fact, never a stored guess (ARCHITECTURE.md §4). Computed from
    the value with SymPy, NO LLM (CLAUDE.md §8.2). The nested-subset rule:

      - ``rational``: every value in this Grade-6 lesson is rational (the outermost set).
      - ``integer``: the value is a whole number (denominator 1 in reduced form).
      - ``whole``: a non-negative integer (0, 1, 2, …).
      - ``natural``: a positive integer (the counting numbers 1, 2, 3, …).

    Returns the matching labels in ``NUMBER_SET_LABELS`` order (small → large), e.g. ``5`` →
    ``("natural", "whole", "integer", "rational")``; ``0`` → ``("whole", "integer", "rational")``;
    ``-3`` → ``("integer", "rational")``; ``1/2`` → ``("rational",)``.
    """
    is_integer = value.q == 1  # SymPy Rational is always reduced, so q == 1 iff an integer
    is_whole = is_integer and value >= 0
    is_natural = is_integer and value > 0
    membership = {
        "natural": is_natural,
        "whole": is_whole,
        "integer": is_integer,
        "rational": True,  # in-scope values are all rational
    }
    return tuple(label for label in NUMBER_SET_LABELS if membership[label])


def omit_rational_for_integer(correct_sets: str | None) -> str | None:
    """integer-not-rational: drop ``rational`` from an INTEGER's set, as a learner who doesn't
    realize every integer is rational would.

    Given the CANONICAL answer string (a comma-separated, small→large label list, e.g.
    ``"integer,rational"`` or ``"natural,whole,integer,rational"``), return the same list with
    ``rational`` removed — BUT only when the value is an integer (its set contains ``integer``), so
    the result is a genuinely-wrong, still-non-empty set. Returns ``None`` when the misconception
    changes nothing or makes no sense: a non-integer value (``rational``-only, where dropping it
    leaves an empty set and the error doesn't apply), a ``None`` input, or a set without
    ``rational``. Returning ``None`` means the verifier never flags an "error" the learner could not
    have made here. Pure/deterministic; reasons over labels, not the LLM.
    """
    if correct_sets is None:
        return None
    labels = [label.strip() for label in correct_sets.split(",") if label.strip()]
    if "integer" not in labels or "rational" not in labels:
        return None  # not an integer (or already missing rational) — the error doesn't apply
    remaining = [label for label in labels if label != "rational"]
    return ",".join(remaining)


def subtract_across(num1: int, den1: int, num2: int, den2: int) -> WrongFraction:
    """natural-number-bias on subtraction: a/b - c/d -> (a-c)/(b-d).

    The subtraction analog of the across error: the learner operates on the parts
    separately (RESEARCH.md §1.2, §6.4 — relabeled natural-number-bias rather than
    add-across, a deliberate citation-honesty choice). The denominator subtraction
    can go zero or negative (e.g. 2/3 - 1/6 -> 1/-3), which is meaningless for a
    piece size; we keep it raw because that impossibility is the signal the bank
    records and the number line / area model expose.
    """
    return WrongFraction(numerator=num1 - num2, denominator=den1 - den2)


def natural_number_bias_compare(
    frac1: tuple[int, int],
    frac2: tuple[int, int],
) -> tuple[int, int]:
    """natural-number-bias on magnitude: which fraction the learner judges LARGER.

    The learner reads each fraction as two whole numbers. The denominator carries
    the dominant 'how big' signal (the most-documented error — a larger denominator
    is read as a larger amount; RESEARCH.md §1.2, Gabriel et al. 2013), so we
    compare denominators first; on a tie (same bottom) we fall back to comparing
    numerators as whole numbers. Returns whichever fraction the bias deems bigger —
    which is wrong precisely when the bigger-denominator fraction is the smaller
    magnitude (1/6 vs 1/2 -> the bias picks 1/6).
    """
    _, den1 = frac1
    _, den2 = frac2
    if den1 != den2:
        return frac1 if den1 > den2 else frac2
    # Same denominator: the digits that differ are the numerators, so the bias
    # (correctly, here) picks the bigger numerator — but for the same WHOLE-number
    # reason, not magnitude reasoning.
    num1, _ = frac1
    num2, _ = frac2
    return frac1 if num1 >= num2 else frac2


def natural_number_bias_number_line(num: int, den: int) -> NumberLineMisplacement:
    """natural-number-bias on number-line placement: place by the digits.

    The learner reads the denominator as a whole-number position rather than the
    fraction's magnitude, so the marker lands near the denominator value — off the
    0–1 line for 1/2 (lands near 2) and far to the right for 1/8 (reads 8 as
    'big'), though 1/8 is one of the smallest amounts (RESEARCH.md §1.2; Braithwaite
    & Siegler 2018 number-line estimation; Gabriel et al. 2013 large-denominator
    case). ``biased_position`` is expressed as a Rational so it can be compared to
    the true value uniformly.
    """
    return NumberLineMisplacement(
        true_value=Rational(num, den),
        biased_position=Rational(den),  # the denominator read as a whole-number position
    )


def reduce_means_smaller_judges_same(
    frac1: tuple[int, int],
    frac2: tuple[int, int],
) -> YesNo:
    """reduce-means-smaller on an 'are these the same amount?' item.

    Defined over a pair the learner is asked to judge equal. A learner who believes
    that the form with smaller numbers (the reduced form) names a smaller amount
    concludes the two are NOT the same, answering 'no' — even though they are equal
    (RESEARCH.md §1.2; Barbieri et al. 2024). Every reduce-means-smaller probe in
    the bank (EQ-005, EQ-006, EQ-010) is exactly such an equal pair, so the wrong
    answer is uniformly 'no'. The pair is taken as input (rather than hard-coded)
    so the generator is general, but the misconception's verdict on a same-amount
    judgment does not depend on the specific numbers.
    """
    # The arguments document that this applies to a same-amount judgment; the
    # verdict ('no') is the misconception's signature regardless of the pair.
    del frac1, frac2
    return "no"


def equal_sign_as_procedural_relational() -> EqualSignVerdict:
    """equal-sign-as-procedural on a relational 'are these the same?' item.

    There is no operation to run on a same-amount judgment, so the operational
    reader — whose only meaning for '=' is 'compute and write the answer' — has no
    procedure to fall back on and defaults to 'no' (RESEARCH.md §1.2; McNeil et al.
    2006). Takes no arguments because the verdict does not depend on the specific
    fractions: on ANY relational item with nothing to compute, the answer is 'no'
    and ``tried_to_compute`` is ``False``. Every such probe in the bank (EQ-001,
    EQ-002, EQ-010) yields 'no'.
    """
    return EqualSignVerdict(answer="no", tried_to_compute=False)


def procedure_without_concept(correct_answer: object) -> ProcedureWithoutConceptResult:
    """procedure-without-concept: the CORRECT answer, flagged as unjustified.

    This generator is the one that does NOT fabricate a wrong number (the brief's
    nuance). The procedural learner runs the algorithm correctly on routine items,
    so the answer carried is the correct one; the diagnostic tell is that they
    cannot explain it and fail error-finding, captured as ``can_justify=False``
    (PROJECT.md §4.2 Persona 2; RESEARCH.md §1.2; Lenz & Wittmann 2021). On an
    error-finding item the "correct answer" passed in is whatever the learner
    endorses (e.g. the presented-but-wrong 'yes (4/3)' in SUB-005); ``can_justify``
    is still ``False`` because the failure is the absence of a reasonableness check,
    not the production of a specific number. The mastery model uses this flag, not
    a value, to keep procedural fluency from passing as conceptual mastery (§3.4).
    """
    return ProcedureWithoutConceptResult(answer=correct_answer, can_justify=False)
