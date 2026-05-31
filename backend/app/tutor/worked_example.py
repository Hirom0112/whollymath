"""The S4 worked-example backend (Slice 3.6).

S4 is the worked-example surface state (PROJECT.md §3.5 row S4; ARCHITECTURE.md §7):
"A solved problem with steps revealed one at a time, each accompanied by a 'why did
this work?' question. Used sparingly." A learner reaches S4 after ≥2 consecutive
errors (PROJECT.md §3.6 row 133 / ARCHITECTURE.md §7 the ``S1/S2/S3 --> S4`` edges) —
the help-avoidance research says don't wait too long. This module turns the
``Problem`` the learner got stuck on into that S4 content: an ordered tuple of
``WorkedStep``s walking the KC's CANONICAL correct procedure (ARCHITECTURE.md §4
"Each KC carries its canonical correct procedure"), each step carrying a one-line
conceptual "why did this work?" prompt.

What lives here, and nothing else: the assembly of the worked example from a
``Problem``. Like ``tutor/transfer_probe.py`` (the precedent for a tutor-adjacent
feature), it leans on the domain ``Problem`` for the math it carries and uses
``sympy.Rational`` + ``math.lcm`` only to COMPUTE the intermediate display values
(the common denominator, the rewritten numerators, the running total). The
correctness AUTHORITY — ``domain.verifier.verify`` — is NOT called here and is not
imported: that boundary stays in ``domain/`` (CLAUDE.md §8.2; ARCHITECTURE.md §14
invariants 2 and 5). The module is pure and deterministic: the same ``Problem``
yields the same ``WorkedExample`` every call (PROJECT.md §4.1), with no LLM, no DB,
and no network (CLAUDE.md §8.1).

The final step's revealed value always equals ``problem.correct_value`` — the worked
example must land on exactly the answer the problem already carries. This is an
internal self-consistency property, asserted by the tests via ``Rational`` equality,
never by re-deriving correctness through the verifier.

KC coverage:

  - ADDITION_UNLIKE / SUBTRACTION_UNLIKE: the full four-step canonical procedure
    (common denominator → rewrite each fraction → combine the numerators → check
    simplest form).
  - COMMON_DENOMINATOR: name the two piece sizes, then the smallest shared size (LCM).
  - EQUIVALENCE: read off the scale factor, then scale the top to name the same amount.
  - NUMBER_LINE_PLACEMENT: a single "locate by magnitude" step — there is no
    multi-step arithmetic procedure to reveal, but S4 is reachable from ANY state on
    ≥2 consecutive errors (PROJECT.md §3.6 row 133), so the surface gets one honest,
    defensible step rather than an empty / raised result. (Decision flagged for review.)

A ``Problem`` an operation KC needs operands for but which carries none cannot be
worked through, so we raise loudly (CLAUDE.md §8.5) rather than ship a hollow example.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from sympy import Rational

from app.domain.center_spread import CENTER_MEDIAN, SPREAD_RANGE
from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.misconceptions import (
    CATEGORICAL_MODE_CODE,
    DATA_DISPLAY_QUESTION_CODE,
    SUMMARY_STAT_MODE_CODE,
)
from app.domain.problem_generators import Problem

# ─── The worked-example value types ──────────────────────────────────────────


@dataclass(frozen=True)
class WorkedStep:
    """One revealed step of a worked example, with its "why did this work?" prompt.

    Frozen — a worked step is a fact about the explanation, not mutable state
    (ARCHITECTURE.md §14, CLAUDE.md §8.4). Fields:

    - ``shown``           the kid-facing step content (e.g. "Find a common
      denominator: the smallest is 12.").
    - ``why_prompt``      the one-line conceptual "why did this work?" question that
      accompanies the step (the §3.5 S4 requirement that EVERY revealed step carries
      one). Plain conceptual copy — no claim needing a source.
    - ``revealed_value``  the exact ``Rational`` magnitude this step lands on, when the
      step produces one (the running/intermediate value the display can echo);
      ``None`` for narrative steps that set up rather than compute. The LAST step's
      ``revealed_value`` always equals ``problem.correct_value``.
    """

    shown: str
    why_prompt: str
    revealed_value: Rational | None = None


@dataclass(frozen=True)
class WorkedExample:
    """The S4 worked example for one ``Problem``: its ordered steps and final value.

    Frozen, with a tuple of steps so the whole object is hashable and genuinely
    immutable. ``steps`` are in canonical procedure order (first revealed first).
    ``final_value`` is the answer the example lands on and, by construction, equals
    ``problem.correct_value`` — the worked example must agree with the problem it
    explains (self-consistency, asserted in tests without the SymPy verifier).
    """

    problem: Problem
    steps: tuple[WorkedStep, ...]

    @property
    def final_value(self) -> Rational:
        """The magnitude the last step lands on (== ``problem.correct_value``)."""
        final = self.steps[-1].revealed_value
        if final is None:  # every builder's last step carries a value; guard the reader
            raise ValueError(
                f"worked example for {self.problem.problem_id} has no final value: "
                "the last step revealed no magnitude"
            )
        return final


# ─── Operand access (fail loudly when the procedure needs a pair it lacks) ───


def _require_pair(problem: Problem) -> tuple[Rational, Rational]:
    """Return the problem's two operands, or raise if it does not carry a clean pair.

    The arithmetic and common-denominator procedures are defined over two operand
    fractions; a problem of those KCs that carries no operand pair cannot be worked
    through, so we raise rather than ship a hollow example (CLAUDE.md §8.5).
    """
    operands = problem.operands
    if operands is None or len(operands) != 2:
        raise ValueError(
            f"{problem.kc.value} worked example needs two operands; "
            f"problem {problem.problem_id} carries {operands!r}"
        )
    return operands[0], operands[1]


def _require_single(problem: Problem) -> Rational:
    """Return the problem's single operand, or raise if it does not carry exactly one.

    The equivalence and number-line procedures are defined over one operand fraction.
    """
    operands = problem.operands
    if operands is None or len(operands) != 1:
        raise ValueError(
            f"{problem.kc.value} worked example needs one operand; "
            f"problem {problem.problem_id} carries {operands!r}"
        )
    return operands[0]


# ─── Per-KC canonical procedures ─────────────────────────────────────────────
#
# Each builder walks the KC's canonical correct procedure (ARCHITECTURE.md §4),
# computing intermediate display values with Rational / math.lcm — never deciding
# correctness (that is the verifier's job, in domain/). The final step's
# revealed_value is the problem's answer by construction.


def _addition_or_subtraction_steps(
    problem: Problem, *, is_addition: bool
) -> tuple[WorkedStep, ...]:
    """The four canonical steps for add/subtract with unlike denominators.

    common denominator → rewrite each fraction over it → combine the numerators →
    check simplest form. The intermediate values are computed exactly with
    ``math.lcm`` and integer arithmetic on the numerators; the combined result and
    the final simplified value are ``Rational``, so the last step lands on exactly
    ``problem.correct_value``.
    """
    first, second = _require_pair(problem)
    common = math.lcm(int(first.q), int(second.q))
    first_top = int(first.p) * (common // int(first.q))
    second_top = int(second.p) * (common // int(second.q))
    combined_top = first_top + second_top if is_addition else first_top - second_top
    combined = Rational(combined_top, common)  # may not be in lowest terms yet
    simplified = first + second if is_addition else first - second

    verb = "add" if is_addition else "subtract"
    operator = "+" if is_addition else "-"
    combine_phrase = "Add the top numbers" if is_addition else "Subtract the top numbers"

    already_simplest = combined == simplified
    simplify_shown = (
        f"Check it's in simplest form: {simplified.p}/{simplified.q} is already simplest."
        if already_simplest
        else (
            f"Put it in simplest form: {combined_top}/{common} simplifies to "
            f"{simplified.p}/{simplified.q}."
        )
    )

    return (
        WorkedStep(
            shown=(
                f"Find a common denominator for {first.p}/{first.q} and "
                f"{second.p}/{second.q}: the smallest is {common}."
            ),
            why_prompt="Why do the pieces have to be the same size before we combine them?",
            revealed_value=Rational(common),
        ),
        WorkedStep(
            shown=(
                f"Rewrite each fraction with {common} on the bottom: "
                f"{first.p}/{first.q} = {first_top}/{common}, "
                f"{second.p}/{second.q} = {second_top}/{common}."
            ),
            why_prompt="Why does renaming a fraction this way not change how much it is?",
        ),
        WorkedStep(
            shown=(
                f"{combine_phrase}: {first_top} {operator} {second_top} = {combined_top}, "
                f"over {common} → {combined_top}/{common}."
            ),
            why_prompt=f"Why do we {verb} only the top numbers and keep the bottom the same?",
            revealed_value=combined,
        ),
        WorkedStep(
            shown=simplify_shown,
            why_prompt="Why does simplest form name the same amount as before?",
            revealed_value=simplified,
        ),
    )


def _common_denominator_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The canonical steps for finding a common denominator: piece sizes → smallest shared.

    Names the two current piece sizes, then the smallest size that works for both
    (their LCM) — the answer ``problem.correct_value`` carries as a ``Rational``
    whole number.
    """
    first, second = _require_pair(problem)
    common = math.lcm(int(first.q), int(second.q))
    return (
        WorkedStep(
            shown=(
                f"The two pieces are different sizes: {first.p}/{first.q} is in "
                f"{first.q}ths and {second.p}/{second.q} is in {second.q}ths."
            ),
            why_prompt="Why can't we compare or combine pieces of two different sizes?",
        ),
        WorkedStep(
            shown=(
                f"Find the smallest size both fit into: the smallest common multiple of "
                f"{first.q} and {second.q} is {common}."
            ),
            why_prompt="Why do we want the SMALLEST shared size and not just any shared size?",
            revealed_value=Rational(common),
        ),
    )


def _equivalence_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The canonical steps for renaming a fraction to an equivalent form.

    The generator's equivalence problem fills the blank in ``base = ?/new_denom``; the
    canonical procedure is to read off the scale factor (``new_denom / base.q``) and
    multiply the top by it. The renamed fraction names the SAME amount as ``base``, so
    the final value is ``base`` (== ``problem.correct_value``).
    """
    base = _require_single(problem)
    new_denominator = _new_denominator_from_statement(problem, base)
    scale = new_denominator // int(base.q)
    new_top = int(base.p) * scale
    return (
        WorkedStep(
            shown=(
                f"See how the bottom changes: {base.q} becomes {new_denominator}, "
                f"which is {base.q} × {scale}."
            ),
            why_prompt="Why does the bottom number tell us how many equal pieces there are?",
        ),
        WorkedStep(
            shown=(
                f"Multiply the top by the same {scale}: {base.p} × {scale} = {new_top}, "
                f"so {base.p}/{base.q} = {new_top}/{new_denominator}."
            ),
            why_prompt="Why must we multiply top and bottom by the same number?",
            revealed_value=base,  # the equivalent form names the same amount as `base`
        ),
    )


def _new_denominator_from_statement(problem: Problem, base: Rational) -> int:
    """Recover the equivalence target denominator from the problem statement.

    The generator phrases it as ``base.p/base.q is the same as ?/<new_denominator>``.
    We read the denominator that follows the ``?/`` so the worked example explains the
    exact problem shown, not a re-sampled one. Raises loudly if the expected shape is
    absent (CLAUDE.md §8.5) — an equivalence problem we cannot read is one we must not
    pretend to explain.
    """
    marker = "?/"
    index = problem.statement.find(marker)
    if index == -1:
        raise ValueError(
            f"equivalence problem {problem.problem_id} has no '?/<denominator>' to "
            f"build a worked example from: {problem.statement!r}"
        )
    tail = problem.statement[index + len(marker) :]
    digits = ""
    for char in tail:
        if char.isdigit():
            digits += char
        else:
            break
    if not digits:
        raise ValueError(
            f"equivalence problem {problem.problem_id} has no denominator after '?/': "
            f"{problem.statement!r}"
        )
    new_denominator = int(digits)
    if new_denominator % int(base.q) != 0:
        raise ValueError(
            f"equivalence target denominator {new_denominator} is not a multiple of "
            f"{base.q} in problem {problem.problem_id}; cannot read a whole scale factor"
        )
    return new_denominator


def _number_line_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The single "locate by magnitude" step for number-line placement.

    Coverage decision (flagged for review): NUMBER_LINE_PLACEMENT has no multi-step
    arithmetic procedure to reveal. But S4 is reachable from ANY state on ≥2
    consecutive errors (PROJECT.md §3.6 row 133 / ARCHITECTURE.md §7), so the surface
    must carry honest content. We give ONE defensible step that reasons about
    magnitude — the very thing placement is about (the KC description:
    "reasoning about its magnitude rather than its digits") — landing on the target
    fraction, which IS ``problem.correct_value`` (its position on the unit interval).
    """
    target = _require_single(problem)
    return (
        WorkedStep(
            shown=(
                f"{target.p}/{target.q} means {target.p} out of {target.q} equal parts "
                f"of the line from 0 to 1, so it sits {target.p}/{target.q} of the way along "
                f"— a bit "
                + ("under" if 2 * int(target.p) < int(target.q) else "over")
                + " halfway."
            ),
            why_prompt=(
                "Why does a fraction's place on the line come from its size, not its digits?"
            ),
            revealed_value=target,
        ),
    )


def _unit_rate_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The 'share the total into equal parts' steps for a unit rate (Grade-6 Unit 1).

    ``operands = (total, count)``; the unit rate is ``total / count``, which equals
    ``problem.correct_value`` by construction (the last step lands on it). Raises if the
    operands are missing (CLAUDE.md §8.5 — a hollow example would mislead).
    """
    operands = problem.operands
    if operands is None or len(operands) != 2:
        raise ValueError(f"unit-rate problem {problem.problem_id} needs (total, count) operands")
    total, count = int(operands[0]), int(operands[1])
    rate = problem.correct_value
    each = f"{rate.p}/{rate.q}" if rate.q != 1 else f"{rate.p}"
    return (
        WorkedStep(
            shown=f"A unit rate is the amount for ONE. Here {total} is shared over {count} units.",
            why_prompt="Why does 'for one' mean splitting the total into equal shares?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"Split the total into {count} equal shares: {total} divided by {count}.",
            why_prompt="Why divide the total by the count, and not the count by the total?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"Each single unit is {each}.",
            why_prompt="Why is this the amount for exactly one unit?",
            revealed_value=rate,
        ),
    )


def _ratio_language_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The 'count the whole, then the part' steps for a part-to-whole ratio (Grade-6 Unit 1).

    ``operands = (part, other)``; the part-whole fraction is ``part / (part + other)``, which
    equals ``problem.correct_value`` by construction (the last step lands on it). Raises if the
    operands are missing (CLAUDE.md §8.5 — a hollow example would mislead).
    """
    operands = problem.operands
    if operands is None or len(operands) != 2:
        raise ValueError(f"ratio-language problem {problem.problem_id} needs (part, other)")
    part, other = int(operands[0]), int(operands[1])
    total = part + other
    answer = problem.correct_value
    each = f"{answer.p}/{answer.q}" if answer.q != 1 else f"{answer.p}"
    return (
        WorkedStep(
            shown=f"Count ALL the counters first: {part} and {other} make {total} in all.",
            why_prompt="Why is the whole the total of both colours, not just the other colour?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"The asked colour is {part} of those {total}.",
            why_prompt="Why does 'fraction of the whole' put the total on the bottom?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"So the fraction of the whole is {each}.",
            why_prompt="Why is this less than one whole when only some counters are that colour?",
            revealed_value=answer,
        ),
    )


def _equivalent_ratios_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The 'multiply both terms by the same factor' steps for an equivalent ratio.

    ``operands = (a, b, target_den)``; the scale factor is ``target_den / b`` and the missing
    term is ``a * factor``, which equals ``problem.correct_value`` by construction. Raises if
    the operands are missing (CLAUDE.md §8.5).
    """
    operands = problem.operands
    if operands is None or len(operands) != 3:
        raise ValueError(f"equivalent-ratios problem {problem.problem_id} needs (a, b, target)")
    a, b, target_den = int(operands[0]), int(operands[1]), int(operands[2])
    factor = target_den // b
    return (
        WorkedStep(
            shown=f"The bottom went from {b} to {target_den} — that is times {factor}.",
            why_prompt="Why must both terms grow by the same factor to stay an equal ratio?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"Do the same to the top: {a} times {factor}.",
            why_prompt="Why multiply (not add) to keep the ratio equal?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"The missing number is {a * factor}.",
            why_prompt="Why does this keep the two ratios naming the same comparison?",
            revealed_value=problem.correct_value,
        ),
    )


def _percent_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The 'per 100, then of the whole' steps for a percent-of problem.

    ``operands = (percent, whole)``; the answer is ``percent/100 * whole ==
    problem.correct_value``. Raises if the operands are missing (CLAUDE.md §8.5).
    """
    operands = problem.operands
    if operands is None or len(operands) != 2:
        raise ValueError(f"percent problem {problem.problem_id} needs (percent, whole)")
    percent, whole = int(operands[0]), int(operands[1])
    answer = problem.correct_value
    each = f"{answer.p}/{answer.q}" if answer.q != 1 else f"{answer.p}"
    return (
        WorkedStep(
            shown=f"{percent}% means {percent} out of 100, i.e. the fraction {percent}/100.",
            why_prompt="Why is a percent just a fraction with a denominator of 100?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"Take that fraction OF the whole: {percent}/100 of {whole}.",
            why_prompt="Why does 'percent of' mean multiply the fraction by the whole?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"That is {each}.",
            why_prompt="Why should this be smaller than the whole when the percent is under 100?",
            revealed_value=answer,
        ),
    )


def _multiply_fractions_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The 'multiply across, then simplify' steps for a fraction product (Grade-6 Unit 2).

    ``operands = (first, second)``; the product is ``first * second ==
    problem.correct_value``. Raises if the operands are missing (CLAUDE.md §8.5).
    """
    operands = problem.operands
    if operands is None or len(operands) != 2:
        raise ValueError(f"multiply-fractions problem {problem.problem_id} needs (first, second)")
    first, second = operands
    answer = problem.correct_value
    each = f"{answer.p}/{answer.q}" if answer.q != 1 else f"{answer.p}"
    return (
        WorkedStep(
            shown=(
                f"Multiply the tops together and the bottoms together: "
                f"({first.p}x{second.p})/({first.q}x{second.q})."
            ),
            why_prompt="Why do you multiply straight across, with no common denominator?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"That is {first.p * second.p}/{first.q * second.q}.",
            why_prompt="Why is a part OF a part smaller than either fraction you started with?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"Simplify: {each}.",
            why_prompt="Why does reducing keep the same value with smaller numbers?",
            revealed_value=answer,
        ),
    )


def _divide_fractions_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The 'flip the divisor, then multiply across' steps for a fraction quotient (Grade-6 Unit 2).

    ``operands = (first, second)``; the quotient is ``first / second ==
    problem.correct_value``. Raises if the operands are missing (CLAUDE.md §8.5).
    """
    operands = problem.operands
    if operands is None or len(operands) != 2:
        raise ValueError(f"divide-fractions problem {problem.problem_id} needs (first, second)")
    first, second = operands
    answer = problem.correct_value
    each = f"{answer.p}/{answer.q}" if answer.q != 1 else f"{answer.p}"
    return (
        WorkedStep(
            shown=(
                f"Flip the second fraction (the divisor): {second.p}/{second.q} "
                f"becomes {second.q}/{second.p}."
            ),
            why_prompt="Why does dividing by a fraction mean multiplying by its reciprocal?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=(
                f"Now multiply across: ({first.p}x{second.q})/({first.q}x{second.p}) = "
                f"{first.p * second.q}/{first.q * second.p}."
            ),
            why_prompt="Why is dividing by a number less than one whole making the answer bigger?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"Simplify: {each}.",
            why_prompt="Why does reducing keep the same value with smaller numbers?",
            revealed_value=answer,
        ),
    )


def _unit_conversion_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The 'each big unit holds this many small ones, so multiply' steps for a unit conversion.

    ``operands = (quantity, factor)``; the answer is ``quantity * factor ==
    problem.correct_value``. Raises if the operands are missing (CLAUDE.md §8.5).
    """
    operands = problem.operands
    if operands is None or len(operands) != 2:
        raise ValueError(f"unit-conversion problem {problem.problem_id} needs (quantity, factor)")
    quantity, factor = int(operands[0]), int(operands[1])
    answer = problem.correct_value
    return (
        WorkedStep(
            shown=f"Each big unit is made of {factor} small units.",
            why_prompt="Why does one bigger unit contain several of the smaller unit?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"For {quantity} of them, multiply: {quantity} times {factor}.",
            why_prompt="Why multiply by the factor (not divide) to convert to the smaller unit?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"That is {answer.p} small units.",
            why_prompt="Why should the count grow when the unit gets smaller?",
            revealed_value=answer,
        ),
    )


def _gcf_lcm_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The 'list factors / list multiples, take the right one' steps for a GCF or LCM problem.

    ``operands = (a, b, mode)``; ``mode`` 1 == LCM asked, 0 == GCF asked. The answer is
    ``problem.correct_value`` (a whole number). Walks the canonical procedure for whichever
    aggregate was asked, landing on the answer. Raises if the operands are missing (CLAUDE.md §8.5).
    """
    operands = problem.operands
    if operands is None or len(operands) != 3:
        raise ValueError(f"gcf-lcm problem {problem.problem_id} needs (a, b, mode) operands")
    a, b, mode = int(operands[0]), int(operands[1]), int(operands[2])
    answer = problem.correct_value
    if mode == 1:  # LCM asked
        return (
            WorkedStep(
                shown=f"The LCM is the SMALLEST number that BOTH {a} and {b} divide into.",
                why_prompt="Why is it a multiple of both, and not a factor of them?",
                revealed_value=None,
            ),
            WorkedStep(
                shown=f"Count up by {a} and by {b}; find the first total they land on together.",
                why_prompt="Why is the first shared landing the LEAST common multiple?",
                revealed_value=None,
            ),
            WorkedStep(
                shown=f"That shared total is {answer.p}.",
                why_prompt="Why must this be at least as big as the larger of the two numbers?",
                revealed_value=answer,
            ),
        )
    return (  # GCF asked
        WorkedStep(
            shown=f"The GCF is the LARGEST number that divides BOTH {a} and {b} with no remainder.",
            why_prompt="Why is it a factor of both, and not a multiple of them?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"List what divides {a}, list what divides {b}, and find the biggest they share.",
            why_prompt="Why is the biggest shared divisor the GREATEST common factor?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"That biggest shared divisor is {answer.p}.",
            why_prompt="Why must this be no bigger than the smaller of the two numbers?",
            revealed_value=answer,
        ),
    )


def _multi_digit_division_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The 'how many times the divisor fits, mind the place value' steps for an exact division.

    ``operands = (dividend, divisor)``; the quotient is ``dividend // divisor ==
    problem.correct_value``. Raises if the operands are missing (CLAUDE.md §8.5).
    """
    operands = problem.operands
    if operands is None or len(operands) != 2:
        raise ValueError(f"division problem {problem.problem_id} needs (dividend, divisor)")
    dividend, divisor = int(operands[0]), int(operands[1])
    answer = problem.correct_value
    return (
        WorkedStep(
            shown=f"Divide {dividend} by {divisor}: how many whole times does {divisor} fit?",
            why_prompt="Why does exact division mean it fits a whole number of times, no leftover?",
            revealed_value=None,
        ),
        WorkedStep(
            shown="Work left to right, placing each quotient digit over its place in the dividend.",
            why_prompt="Why does the place of each quotient digit set the size of the answer?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"The quotient is {answer.p}.",
            why_prompt=f"Why does {answer.p} times {divisor} land back on {dividend}?",
            revealed_value=answer,
        ),
    )


def _decimal_operations_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The 'multiply the digits, then place the point by total places' steps for a decimal product.

    ``operands = (first, second)`` (exact decimals with power-of-ten denominators); the product is
    ``first * second == problem.correct_value``. Walks the canonical place-value procedure, landing
    on the answer. Raises if the operands are missing (CLAUDE.md §8.5).
    """
    operands = problem.operands
    if operands is None or len(operands) != 2:
        raise ValueError(f"decimal-operations problem {problem.problem_id} needs (first, second)")
    first, second = operands
    answer = problem.correct_value
    places_first = _terminating_decimal_places(first)
    places_second = _terminating_decimal_places(second)
    total_places = places_first + places_second
    return (
        WorkedStep(
            shown="Ignore the points for a moment and multiply the numbers as whole numbers.",
            why_prompt="Why can you multiply the digits first and worry about the point after?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=(
                f"Count the decimal places in both factors: {places_first} plus {places_second} "
                f"makes {total_places}. The product needs {total_places} places after the point."
            ),
            why_prompt="Why do the decimal places of the two factors ADD in the product?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"Place the point that many digits from the right: {_decimal_text(answer)}.",
            why_prompt="Why is the product smaller than each factor when both are below one?",
            revealed_value=answer,
        ),
    )


def _integer_add_subtract_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The 'move along the number line by the signed amount' steps for an integer sum (Unit-INT).

    ``operands = (a, b)`` of opposite signs; the sum is ``a + b == problem.correct_value``. Raises
    if the operands are missing (CLAUDE.md §8.5).
    """
    operands = problem.operands
    if operands is None or len(operands) != 2:
        raise ValueError(f"integer problem {problem.problem_id} needs (a, b) operands")
    a, b = int(operands[0]), int(operands[1])
    answer = problem.correct_value
    direction = "right (up)" if b > 0 else "left (down)"
    return (
        WorkedStep(
            shown=f"Start at {a} on the number line.",
            why_prompt="Why is the first number where you begin, before moving?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"Adding {b} moves you {abs(b)} to the {direction} — toward the other sign.",
            why_prompt="Why does a negative move you the opposite way from a positive?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"You land on {answer.p}.",
            why_prompt="Why is the result smaller than just adding the two sizes together?",
            revealed_value=answer,
        ),
    )


def _absolute_value_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The 'distance from zero, drop the sign' steps for an absolute-value problem (Unit 3).

    ``operands = (value,)``; the answer is ``abs(value) == problem.correct_value``. Raises if the
    operands are missing (CLAUDE.md §8.5).
    """
    operands = problem.operands
    if operands is None or len(operands) != 1:
        raise ValueError(f"absolute-value problem {problem.problem_id} needs a (value,) operand")
    value = int(operands[0])
    answer = problem.correct_value
    return (
        WorkedStep(
            shown=f"Absolute value is the DISTANCE of {value} from zero on the number line.",
            why_prompt="Why is absolute value a distance, and never which side of zero?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"Count the steps from {value} back to zero, ignoring the sign.",
            why_prompt="Why can a distance never be negative?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"That distance is {answer.p}.",
            why_prompt="Why do a number and its opposite share the same absolute value?",
            revealed_value=answer,
        ),
    )


def _signed_numbers_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The 'flip the sign across zero' steps for an opposite-of-a-number problem (Grade-6 Unit 3).

    ``operands = (n,)``; the opposite is ``-n == problem.correct_value``. Raises if the operand is
    missing (CLAUDE.md §8.5).
    """
    operands = problem.operands
    if operands is None or len(operands) != 1:
        raise ValueError(f"signed-numbers problem {problem.problem_id} needs (n,) operand")
    n = int(operands[0])
    answer = problem.correct_value
    side = "left of zero (negative)" if n > 0 else "right of zero (positive)"
    return (
        WorkedStep(
            shown=f"The opposite is the SAME distance from zero as {n}, on the other side.",
            why_prompt="Why does an opposite keep the distance from zero but switch sides?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"{n} sits on one side of zero; its opposite is {side}.",
            why_prompt="Why does flipping the side flip the sign of the number?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"So the opposite is {answer.p}.",
            why_prompt="Why is the opposite of an opposite the number you started with?",
            revealed_value=answer,
        ),
    )


_STAT_NAME_BY_CODE: dict[int, str] = {code: name for name, code in SUMMARY_STAT_MODE_CODE.items()}


def _summary_statistics_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The steps for a summary-statistic problem (Grade-6 Unit 7, 6.SP.3).

    ``operands = (mode_code, *data)`` (a leading stat-mode sentinel; see
    ``SUMMARY_STAT_MODE_CODE``). The narration is statistic-specific (mean / median / mode /
    range), and the final step lands on ``problem.correct_value``. Raises if the operands are
    missing or empty (CLAUDE.md §8.5).
    """
    operands = problem.operands
    if operands is None or len(operands) < 2:
        raise ValueError(
            f"summary-statistics problem {problem.problem_id} needs (mode_code, *data) operands"
        )
    mode = _STAT_NAME_BY_CODE[int(operands[0])]
    data = [int(v) for v in operands[1:]]
    answer = problem.correct_value
    listing = ", ".join(str(v) for v in data)
    setup, work = _summary_statistic_narration(mode, data)
    return (
        WorkedStep(
            shown=f"To find the {mode}, look at all the values: {listing}.",
            why_prompt=f"Why does the {mode} summarize the whole data set with one number?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=setup,
            why_prompt=f"Why is this the right step for the {mode}?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"{work} So the {mode} is {answer}.",
            why_prompt=f"Why does this give the {mode}?",
            revealed_value=answer,
        ),
    )


def _summary_statistic_narration(mode: str, data: list[int]) -> tuple[str, str]:
    """The (setup, work) narration lines for one statistic — kept text-only, no claim to cite."""
    if mode == "mean":
        total = sum(data)
        return (
            f"Add the values, then divide by how many there are ({len(data)}).",
            f"The total is {total}, and {total} divided by {len(data)} is the mean.",
        )
    if mode == "median":
        ordered = ", ".join(str(v) for v in sorted(data))
        return (
            f"Put the values in order first: {ordered}.",
            "The median is the value in the middle of the sorted list.",
        )
    if mode == "mode":
        return (
            "Find the value that appears most often.",
            "The mode is the value that shows up the most times.",
        )
    return (  # range
        "Find the largest and the smallest value.",
        f"The range is the largest ({max(data)}) minus the smallest ({min(data)}).",
    )


_DISPLAY_QUESTION_BY_CODE: dict[int, str] = {
    code: name for name, code in DATA_DISPLAY_QUESTION_CODE.items()
}
_DISPLAY_BIN_WIDTH = 10  # mirrors the generator's histogram bin width

_CATEGORICAL_NAME_BY_CODE: dict[int, str] = {
    code: name for name, code in CATEGORICAL_MODE_CODE.items()
}


def _data_displays_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The steps for a data-display reading problem (Grade-6 Unit 7, 6.SP.4).

    ``operands = (question_code, param, *data)`` (a leading question-type sentinel; see
    ``DATA_DISPLAY_QUESTION_CODE``). The narration is question-specific (count-above /
    most-frequent / bin-frequency), and the final step lands on ``problem.correct_value``. Raises
    if the operands are missing or too short (CLAUDE.md §8.5).
    """
    operands = problem.operands
    if operands is None or len(operands) < 3:
        raise ValueError(
            f"data-displays problem {problem.problem_id} needs (question_code, param, *data) ops"
        )
    question = _DISPLAY_QUESTION_BY_CODE[int(operands[0])]
    param = int(operands[1])
    data = [int(v) for v in operands[2:]]
    answer = problem.correct_value
    listing = ", ".join(str(v) for v in data)
    setup, work = _data_display_narration(question, param, data)
    return (
        WorkedStep(
            shown=f"Read the display one data point at a time: {listing}.",
            why_prompt="Why does each dot (or tally) stand for one data point?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=setup,
            why_prompt="Why is this the right way to read this question off the display?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"{work} So the answer is {answer}.",
            why_prompt="Why does reading the display this way give the answer?",
            revealed_value=answer,
        ),
    )


def _categorical_data_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The steps for a categorical-data summary (Grade-6 Unit 7, TEKS 6.12D).

    ``operands = (mode_code, *category_counts)`` (a leading mode sentinel; see
    ``CATEGORICAL_MODE_CODE``). The narration is mode-specific (count difference / total /
    relative frequency), and the final step lands on ``problem.correct_value``. Raises if the
    operands are missing or too short (CLAUDE.md §8.5).
    """
    operands = problem.operands
    if operands is None or len(operands) < 3:
        raise ValueError(
            f"categorical-data problem {problem.problem_id} needs (mode_code, *counts) operands"
        )
    mode = _CATEGORICAL_NAME_BY_CODE[int(operands[0])]
    counts = [int(c) for c in operands[1:]]
    answer = problem.correct_value
    listing = ", ".join(str(c) for c in counts)
    if mode == "count_difference":
        setup = "For 'how many more', subtract the second category's count from the first."
        work = f"That is {counts[0]} - {counts[1]}, so the difference is {answer}."
    elif mode == "total":
        setup = "For the total surveyed, add the count from every category."
        work = f"Adding {listing} gives {answer} in all."
    else:  # relative_frequency
        setup = "A relative frequency is one category's count OVER the total surveyed."
        work = f"That is {counts[0]} out of {sum(counts)}, so the fraction is {answer}."
    return (
        WorkedStep(
            shown=f"First read the count for each category: {listing}.",
            why_prompt="Why do we read every category's count from the breakdown first?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=setup,
            why_prompt=f"Why is this the right step for the {mode.replace('_', ' ')}?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=work,
            why_prompt="Why does this summarize the categorical data with one number?",
            revealed_value=answer,
        ),
    )


def _data_display_narration(question: str, param: int, data: list[int]) -> tuple[str, str]:
    """The (setup, work) narration lines for one display question — text-only, no claim to cite."""
    if question == "count_above":
        above = [v for v in data if v > param]
        return (
            f"Count every data point greater than {param} — count a repeated value once per dot.",
            f"The data points above {param} are {', '.join(str(v) for v in above)}.",
        )
    if question == "most_frequent":
        return (
            "Find the value with the tallest stack of dots — the one that appears most often.",
            "The most frequent value is the one that shows up the most times.",
        )
    hi = param + _DISPLAY_BIN_WIDTH - 1
    in_bin = [v for v in data if param <= v <= hi]
    return (
        f"Count every data point that falls in the {param}-{hi} bin.",
        f"The data points in that bin are {', '.join(str(v) for v in in_bin)}.",
    )


def _integer_multiply_divide_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The 'magnitude first, then the sign rule' steps for an integer ×/÷ problem (Unit-INT).

    ``operands = (a, b, mode)`` with ``mode == 1`` multiply / ``0`` divide; the answer is ``a*b``
    or ``a/b == problem.correct_value``. Raises if the operands are missing (CLAUDE.md §8.5).
    """
    operands = problem.operands
    if operands is None or len(operands) != 3:
        raise ValueError(f"integer ×/÷ problem {problem.problem_id} needs (a, b, mode) operands")
    a, b = int(operands[0]), int(operands[1])
    multiply = int(operands[2]) == 1
    answer = problem.correct_value
    verb = "Multiply" if multiply else "Divide"
    op_word = "product" if multiply else "quotient"
    magnitude = abs(answer.p)
    same_sign = (a > 0) == (b > 0)
    sign_word = "positive" if same_sign else "negative"
    rule = (
        "the signs are the SAME, so the result is positive"
        if same_sign
        else "the signs are DIFFERENT, so the result is negative"
    )
    return (
        WorkedStep(
            shown=f"{verb} the sizes first, ignoring signs: the {op_word} has size {magnitude}.",
            why_prompt="Why can you find the size before you worry about the sign?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"Now the sign rule: {rule}.",
            why_prompt="Why do like signs give a positive result and unlike signs a negative one?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"So the answer is {sign_word}: {answer.p}.",
            why_prompt="Why does the sign rule decide the answer once you know its size?",
            revealed_value=answer,
        ),
    )


def _triangle_properties_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The triangle-property steps — angle sum to 180° OR ½·base·height (Grade-6 Unit 6, 6.8A).

    ``operands = (a, b, mode)`` with ``mode == 0`` the missing-angle item (answer ``180 - a - b``)
    and ``mode == 1`` the area item (answer ``a*b/2 == problem.correct_value``). Raises if the
    operands are missing (CLAUDE.md §8.5).
    """
    operands = problem.operands
    if operands is None or len(operands) != 3:
        raise ValueError(f"triangle problem {problem.problem_id} needs (a, b, mode) operands")
    a, b = int(operands[0]), int(operands[1])
    answer = problem.correct_value
    if int(operands[2]) == 0:  # missing angle
        return (
            WorkedStep(
                shown="The three angles of a triangle always add to 180°.",
                why_prompt="Why do a triangle's three angles always total a straight angle?",
                revealed_value=None,
            ),
            WorkedStep(
                shown=f"The two you know total {a} + {b} = {a + b}°.",
                why_prompt="Why does adding the two known angles tell you what is left for the"
                " third?",
                revealed_value=None,
            ),
            WorkedStep(
                shown=f"So the third angle is 180 - {a + b} = {answer.p}°.",
                why_prompt="Why subtract from 180 and not from 90?",
                revealed_value=answer,
            ),
        )
    return (  # area
        WorkedStep(
            shown=f"A triangle's area is HALF the base times the height: ½ · {a} · {b}.",
            why_prompt="Why is a triangle's area half the base times the height?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"First multiply the base and height: {a} · {b} = {a * b}.",
            why_prompt="Why does base × height give the rectangle that the triangle fills half of?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"Now take half: {a * b} ÷ 2 = {answer}.",
            why_prompt="Why would forgetting the ½ give twice the real area?",
            revealed_value=answer,
        ),
    )


def _evaluate_expression_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The 'substitute, then multiply before add' steps for an evaluate-expression problem (Unit 4).

    ``operands = (a, x, b)``; the answer is ``a*x + b == problem.correct_value``. Raises if the
    operands are missing (CLAUDE.md §8.5). The middle step lands the product ``a*x`` so the learner
    sees precedence applied before the final addition.
    """
    operands = problem.operands
    if operands is None or len(operands) != 3:
        raise ValueError(
            f"evaluate-expression problem {problem.problem_id} needs (a, x, b) operands"
        )
    a, x, b = (int(operand) for operand in operands)
    product = Rational(a * x)
    answer = problem.correct_value
    return (
        WorkedStep(
            shown=f"Put the value in for x: {a}x + {b} becomes {a}·{x} + {b}.",
            why_prompt="Why does substituting the value let us evaluate the expression?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"Multiply BEFORE you add: {a}·{x} = {product.p}.",
            why_prompt="Why do we do the multiplication before the addition?",
            revealed_value=product,
        ),
        WorkedStep(
            shown=f"Now add the {b}: {product.p} + {b} = {answer.p}.",
            why_prompt="Why would adding first (before multiplying) give a different answer?",
            revealed_value=answer,
        ),
    )


def _exponents_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The 'repeated multiplication' steps for an evaluate-a-power problem (Grade-6 Unit 4).

    ``operands = (base, exp)``; the answer is ``base ** exp == problem.correct_value``. Raises if
    the operands are missing (CLAUDE.md §8.5). The middle step WRITES OUT the base ``exp`` times so
    the learner sees the exponent as a repeat COUNT, not a factor to multiply the base by.
    """
    operands = problem.operands
    if operands is None or len(operands) != 2:
        raise ValueError(f"exponents problem {problem.problem_id} needs (base, exp) operands")
    base, exp = (int(operand) for operand in operands)
    answer = problem.correct_value
    expanded = " x ".join([str(base)] * exp)
    return (
        WorkedStep(
            shown=f"{base}^{exp} means multiply {base} by itself {exp} times — not {base} x {exp}.",
            why_prompt="Why does the small raised number count the multiplications?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"Write it out: {base}^{exp} = {expanded}.",
            why_prompt="Why is multiplying the base by itself different from multiplying it once?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"Multiply across: {expanded} = {answer.p}.",
            why_prompt="Why does a bigger exponent make the value grow so fast?",
            revealed_value=answer,
        ),
    )


def _fmt_rational(value: Rational) -> str:
    """Render a Rational kid-facing — a whole number, else 'p/q' (no decimals, like the surface)."""
    return str(value.p) if value.q == 1 else f"{value.p}/{value.q}"


def _volume_fractional_edges_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The 'multiply all three edges' steps for a prism-volume problem (Grade-6 Unit 6, 6.G.2).

    ``operands = (l, w, h)``; the answer is ``l*w*h == problem.correct_value`` (an exact Rational).
    Raises if the operand triple is missing (CLAUDE.md §8.5). The middle step lands the partial
    product ``l*w`` so the learner sees the volume built up by multiplying, never by adding.
    """
    operands = problem.operands
    if operands is None or len(operands) != 3:
        raise ValueError(f"volume problem {problem.problem_id} needs (l, w, h) operands")
    length, width, height = operands
    partial = length * width
    answer = problem.correct_value
    edge_l, edge_w, edge_h = _fmt_rational(length), _fmt_rational(width), _fmt_rational(height)
    return (
        WorkedStep(
            shown=(
                f"Volume fills the box, so MULTIPLY the three edges: {edge_l} x {edge_w} x "
                f"{edge_h} — don't add them."
            ),
            why_prompt="Why does multiplying the edges give the space inside, but adding does not?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"Multiply two edges first: {edge_l} x {edge_w} = {_fmt_rational(partial)}.",
            why_prompt="Why can we multiply the fractions straight across, tops and bottoms?",
            revealed_value=partial,
        ),
        WorkedStep(
            shown=f"Multiply by the last edge: {_fmt_rational(partial)} x {edge_h} = "
            f"{_fmt_rational(answer)}.",
            why_prompt="Why is the volume bigger than any one edge but built only by multiplying?",
            revealed_value=answer,
        ),
    )


def _surface_area_nets_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The 'add all six faces' steps for a prism surface-area problem (Grade-6 Unit 6, 6.G.4).

    ``operands = (l, w, h)``; the answer is ``2*(l*w + l*h + w*h) == problem.correct_value``. Raises
    if the operand triple is missing (CLAUDE.md §8.5). The middle step lands the three-face subtotal
    so the learner sees that the surface area is that subtotal DOUBLED — every face has a twin.
    """
    operands = problem.operands
    if operands is None or len(operands) != 3:
        raise ValueError(f"surface-area problem {problem.problem_id} needs (l, w, h) operands")
    length, width, height = operands
    three_faces = length * width + length * height + width * height
    answer = problem.correct_value
    edge_l, edge_w, edge_h = _fmt_rational(length), _fmt_rational(width), _fmt_rational(height)
    return (
        WorkedStep(
            shown=(
                f"Unfold the prism into its net: SIX rectangular faces in three matching pairs. "
                f"Find one face of each pair: {edge_l} x {edge_w}, {edge_l} x {edge_h}, and "
                f"{edge_w} x {edge_h}."
            ),
            why_prompt="Why does every face of a box have an identical face on the opposite side?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=(
                f"Add those three face areas: {_fmt_rational(length * width)} + "
                f"{_fmt_rational(length * height)} + {_fmt_rational(width * height)} = "
                f"{_fmt_rational(three_faces)}."
            ),
            why_prompt="Why is this only HALF of the surface area so far?",
            revealed_value=three_faces,
        ),
        WorkedStep(
            shown=(
                f"Double it for the matching opposite faces: 2 x {_fmt_rational(three_faces)} = "
                f"{_fmt_rational(answer)}."
            ),
            why_prompt="Why multiply by 2 instead of counting only the three faces we listed?",
            revealed_value=answer,
        ),
    )


def _mean_absolute_deviation_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The 'mean, then average the distances' steps for a MAD problem (Grade-6 Unit 7, 6.SP.5c).

    ``operands`` is the data set (a variable-length tuple); the answer is the mean of the absolute
    deviations from the data's mean == ``problem.correct_value``. Raises if the data set is missing
    (CLAUDE.md §8.5). The middle steps land the mean and the list of |deviations| so the learner
    sees that the absolute value is what keeps the spread from cancelling to zero.
    """
    data = problem.operands
    if not data:
        raise ValueError(f"MAD problem {problem.problem_id} needs a data set operand")
    n = len(data)
    mean = sum(data, Rational(0)) / n
    abs_devs = tuple(abs(x - mean) for x in data)
    values_text = ", ".join(_fmt_rational(x) for x in data)
    devs_text = ", ".join(_fmt_rational(d) for d in abs_devs)
    answer = problem.correct_value
    return (
        WorkedStep(
            shown=(
                f"First find the mean of {values_text}: add them and divide by {n}, "
                f"giving {_fmt_rational(mean)}."
            ),
            why_prompt="Why do we measure each value's distance from the MEAN, not from zero?",
            revealed_value=mean,
        ),
        WorkedStep(
            shown=(
                f"Find how far each value is from {_fmt_rational(mean)} — the ABSOLUTE deviations: "
                f"{devs_text}. A distance is never negative."
            ),
            why_prompt="Why take the absolute value instead of the signed difference?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=(
                f"Average those distances: their sum divided by {n} is {_fmt_rational(answer)} — "
                f"the mean absolute deviation."
            ),
            why_prompt="Why does a larger MAD mean the data is more spread out?",
            revealed_value=answer,
        ),
    )


def _center_spread_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The center/spread steps for a KC_center_spread_shape problem (Grade-6 Unit 7, 6.SP.2).

    ``operands = (mode_flag, *sorted_data)``; the final step lands ``problem.correct_value`` (the
    median, the range, or the IQR for that item's mode). Raises if the operands are missing or too
    short (CLAUDE.md §8.5). Each mode gets its own concrete steps that name the rule being applied.
    """
    operands = problem.operands
    if operands is None or len(operands) < 2:
        raise ValueError(f"center-spread problem {problem.problem_id} needs (mode, *data) operands")
    mode = int(operands[0])
    data = operands[1:]
    listed = ", ".join(_fmt_rational(v) for v in data)
    answer = problem.correct_value
    if mode == CENTER_MEDIAN:
        return (
            WorkedStep(
                shown=f"Order the values from least to greatest: {listed}.",
                why_prompt="Why does the median require the data to be in order first?",
                revealed_value=None,
            ),
            WorkedStep(
                shown="The median is the middle value (or the average of the two middle values).",
                why_prompt="Why does the middle value summarize the center of the data?",
                revealed_value=None,
            ),
            WorkedStep(
                shown=f"So the median is {_fmt_rational(answer)}.",
                why_prompt="Why can the center be a value that is not in the data set?",
                revealed_value=answer,
            ),
        )
    if mode == SPREAD_RANGE:
        low, high = _fmt_rational(min(data)), _fmt_rational(max(data))
        return (
            WorkedStep(
                shown=f"Find the largest and smallest values: max = {high}, min = {low}.",
                why_prompt="Why do only the extremes matter for the range?",
                revealed_value=None,
            ),
            WorkedStep(
                shown=f"The range is the DIFFERENCE: {high} - {low} = {_fmt_rational(answer)}.",
                why_prompt="Why subtract instead of add to measure how spread out the data is?",
                revealed_value=answer,
            ),
        )
    # SPREAD_IQR
    return (
        WorkedStep(
            shown=f"Order the values and split them into a lower and an upper half: {listed}.",
            why_prompt="Why split the data in half to find the quartiles?",
            revealed_value=None,
        ),
        WorkedStep(
            shown="Q1 is the median of the lower half; Q3 is the median of the upper half.",
            why_prompt="Why are the quartiles the medians of each half?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"The IQR is Q3 - Q1 = {_fmt_rational(answer)}.",
            why_prompt="Why does the IQR ignore the extreme values that the range uses?",
            revealed_value=answer,
        ),
    )


def _one_step_equations_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The 'apply the inverse, isolate x' steps for a one-step equation (Grade-6 Unit 5).

    ``operands = (mode, p, q)``: mode 0 is the additive equation ``x + p = q`` (undo by
    subtracting p); mode 1 is the multiplicative equation ``p*x = q`` (undo by dividing by p).
    The final step lands on ``problem.correct_value`` (the value of x). Raises if the operand
    triple is missing (CLAUDE.md §8.5).
    """
    operands = problem.operands
    if operands is None or len(operands) != 3:
        raise ValueError(f"one-step problem {problem.problem_id} needs (mode, p, q) operands")
    mode, p, q = int(operands[0]), int(operands[1]), int(operands[2])
    answer = problem.correct_value
    if mode == 0:
        equation = f"x + {p} = {q}"
        inverse = f"Subtract {p} from BOTH sides to undo the addition: x = {q} - {p}."
        why_inverse = "Why does subtracting the same amount from both sides keep it balanced?"
    else:
        equation = f"{p}x = {q}"
        inverse = f"Divide BOTH sides by {p} to undo the multiplication: x = {q} / {p}."
        why_inverse = "Why does dividing both sides by the same number keep it balanced?"
    return (
        WorkedStep(
            shown=f"The equation is {equation}. The goal is to get x by itself.",
            why_prompt="Why do we want x alone on one side?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=inverse,
            why_prompt=why_inverse,
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"So x = {answer.p}.",
            why_prompt="Why can we check this by putting the value back into the equation?",
            revealed_value=answer,
        ),
    )


def _write_expression_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The 'name the operation, get the order right' steps for a write-expression problem (Unit 4).

    The answer is an EXPRESSION, not a magnitude, so the steps land on the canonical
    ``problem.correct_expression`` string rather than a Rational — the last step's
    ``revealed_value`` stays ``None`` (a narrative/expression step, the documented non-magnitude
    case) and its ``shown`` carries the expression. Raises if missing (CLAUDE.md §8.5)."""
    canonical = problem.correct_expression
    if canonical is None:
        raise ValueError(f"write-expression problem {problem.problem_id} needs an expression")
    return (
        WorkedStep(
            shown="Pick a letter for the unknown, then read the phrase for the operation.",
            why_prompt="Why does a variable let you write the relationship without a fixed number?",
            revealed_value=None,
        ),
        WorkedStep(
            shown="Mind the ORDER: 'less than' and 'divided by' put the named amount second.",
            why_prompt="Why does order matter for subtraction and division but not addition?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"The expression is {canonical}.",
            why_prompt="Why does this expression say the same thing as the phrase?",
            revealed_value=None,
        ),
    )


def _equivalent_expression_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The 'rewrite without changing the value' steps for an equivalent-expression problem (Unit 4).

    The answer is an EXPRESSION, not a magnitude, so the steps land on the canonical
    ``problem.correct_expression`` string rather than a Rational — the last step's
    ``revealed_value`` stays ``None`` (a narrative/expression step, the documented non-magnitude
    case) and its ``shown`` carries the equivalent expression. Raises if missing (§8.5)."""
    canonical = problem.correct_expression
    if canonical is None:
        raise ValueError(f"equivalent-expression problem {problem.problem_id} needs an expression")
    return (
        WorkedStep(
            shown="Look for a product to expand or like terms to combine.",
            why_prompt="Why can you rewrite an expression without changing what it equals?",
            revealed_value=None,
        ),
        WorkedStep(
            shown="Distribute the multiplier to EVERY term inside, or add the matching terms.",
            why_prompt="Why must the outside factor reach the second term too, not just the first?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"The equivalent expression is {canonical}.",
            why_prompt="Why does this have the same value as the one you started with?",
            revealed_value=None,
        ),
    )


def _inequality_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The 'name the direction, decide inclusion' steps for a write-inequality problem (Unit 5).

    The answer is an INEQUALITY, not a magnitude, so the steps land on the canonical
    ``problem.correct_inequality`` string rather than a Rational — the last step's
    ``revealed_value`` stays ``None`` (a narrative/relational step, the documented non-magnitude
    case) and its ``shown`` carries the inequality. Raises if missing (§8.5)."""
    canonical = problem.correct_inequality
    if canonical is None:
        raise ValueError(f"write-inequality problem {problem.problem_id} needs an inequality")
    return (
        WorkedStep(
            shown="Let x stand for the number, then read which way the allowed values go.",
            why_prompt="Why does a variable let you describe a whole RANGE of numbers at once?",
            revealed_value=None,
        ),
        WorkedStep(
            shown="Decide if the boundary is INCLUDED — 'at least/at most' use >= or <=.",
            why_prompt="Why does 'at least 5' include 5 but 'more than 5' does not?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"The inequality is {canonical}.",
            why_prompt="Why does this inequality describe exactly the numbers the words allow?",
            revealed_value=None,
        ),
    )


def _coordinate_plane_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The 'read the order, then plot' steps for a coordinate-plane problem (Unit 3).

    The answer is a SET of points, not a magnitude, so the steps land on the canonical
    ``problem.correct_points`` string rather than a Rational — the last step's ``revealed_value``
    stays ``None`` (a narrative/coordinate step, the documented non-magnitude case) and its
    ``shown`` carries the points. Raises if missing (§8.5)."""
    canonical = problem.correct_points
    if canonical is None:
        raise ValueError(f"coordinate problem {problem.problem_id} needs correct_points")
    return (
        WorkedStep(
            shown="Start at the center (0, 0), the origin where the two axes cross.",
            why_prompt="Why is every point measured from the origin?",
            revealed_value=None,
        ),
        WorkedStep(
            shown="Move ACROSS by the first number (x), then UP or DOWN by the second (y).",
            why_prompt="Why does the order of the two numbers change where the point lands?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"The point(s) plot at {canonical}.",
            why_prompt="Why does each sign decide which side of an axis the point sits on?",
            revealed_value=None,
        ),
    )


def _classify_number_sets_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The 'walk the nested sets from largest in' steps for a classify problem (Unit 3, TEKS 6.2A).

    The answer is a SET of labels, not a magnitude, so the steps land on the canonical
    ``problem.correct_sets`` string rather than a Rational — the last step's ``revealed_value``
    stays ``None`` (the documented non-magnitude case) and its ``shown`` names the set. Raises if
    missing (§8.5)."""
    canonical = problem.correct_sets
    if canonical is None:
        raise ValueError(f"classify problem {problem.problem_id} needs a correct_sets")
    sets_text = ", ".join(canonical.split(","))
    return (
        WorkedStep(
            shown="Every number here is rational, so start with the biggest set: rational.",
            why_prompt="Why is every fraction and integer a rational number?",
            revealed_value=None,
        ),
        WorkedStep(
            shown="Work inward: is it an integer? a whole number (≥ 0)? a counting number?",
            why_prompt="Why does a number in a smaller set also belong to every larger one?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"So it belongs to: {sets_text}.",
            why_prompt="Why can a negative or a fraction be rational but not a whole number?",
            revealed_value=None,
        ),
    )


def _statistical_questions_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The 'does the answer vary?' steps for a statistical-question item (Unit 7, 6.SP.1).

    The answer is a YES/NO verdict, not a magnitude, so (like ``_classify_number_sets_steps``)
    the steps land on the verdict in the final step's ``shown`` text and keep ``revealed_value``
    ``None`` (the documented non-magnitude case). The truth rides in ``operands`` exactly as the
    verifier reads it (equal ⇒ statistical/YES). Raises if the operands are missing (§8.5)."""
    operands = problem.operands
    if operands is None or len(operands) != 2:
        raise ValueError(f"statistical-question problem {problem.problem_id} needs two operands")
    statistical = bool(operands[0] == operands[1])
    verdict = "IS a statistical question" if statistical else "is NOT a statistical question"
    why_vary = (
        "Why do its answers vary across the group?"
        if statistical
        else "Why does its single fixed answer make it non-statistical?"
    )
    return (
        WorkedStep(
            shown="A statistical question anticipates variability: its answers VARY across cases.",
            why_prompt="Why does variability, not the topic, decide if a question is statistical?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f'Ask: "{problem.statement}" — would different people answer it differently?',
            why_prompt="Why isn't a question statistical just because it names people or numbers?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"So this {verdict}.",
            why_prompt=why_vary,
            revealed_value=None,
        ),
    )


def _expression_parts_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The 'name the part of the expression' steps for an expression-parts item (Unit 4, 6.EE.2b).

    ``operands = (mode, coefficient, constant)``; mode 0 names the coefficient, 1 the constant, 2
    the term count. The final step lands on ``problem.correct_value`` (the part's value). Raises if
    the operands are missing/malformed (CLAUDE.md §8.5)."""
    operands = problem.operands
    if operands is None or len(operands) != 3:
        raise ValueError(f"expression-parts problem {problem.problem_id} needs (mode, c, k)")
    mode = int(operands[0])
    answer = problem.correct_value
    if mode == 0:  # coefficient
        return (
            WorkedStep(
                shown="A coefficient is the number multiplying a variable — find the x term.",
                why_prompt="Why is the coefficient the number attached to the variable?",
                revealed_value=None,
            ),
            WorkedStep(
                shown="Read the number written in front of x (not the number standing alone).",
                why_prompt="Why is the constant — the number on its own — NOT the coefficient?",
                revealed_value=None,
            ),
            WorkedStep(
                shown=f"So the coefficient is {answer.p}.",
                why_prompt="Why does the coefficient tell you how many of the variable you have?",
                revealed_value=answer,
            ),
        )
    if mode == 1:  # constant
        return (
            WorkedStep(
                shown="A constant term is a number on its own — no variable attached to it.",
                why_prompt="Why is the constant the term with no variable?",
                revealed_value=None,
            ),
            WorkedStep(
                shown="Find the number standing alone (not the one multiplying x).",
                why_prompt="Why is the number in front of x NOT the constant?",
                revealed_value=None,
            ),
            WorkedStep(
                shown=f"So the constant term is {answer.p}.",
                why_prompt="Why does the constant stay the same no matter what the variable is?",
                revealed_value=answer,
            ),
        )
    return (  # mode 2: term count
        WorkedStep(
            shown="Terms are the parts of the expression joined by + or - signs.",
            why_prompt="Why do the plus and minus signs separate one term from the next?",
            revealed_value=None,
        ),
        WorkedStep(
            shown="Count each part: every variable piece and every standalone number is one term.",
            why_prompt="Why does each piece between the signs count as a single term?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"So the expression has {answer.p} terms.",
            why_prompt="Why does counting the terms not depend on the values of the variables?",
            revealed_value=answer,
        ),
    )


def _area_polygons_steps(problem: Problem) -> tuple[WorkedStep, ...]:
    """The 'base x height, then halve a triangle' steps for an area problem (Grade-6 Unit 6).

    ``operands = (base, height, mode)`` with ``mode == 0`` a triangle / ``1`` a
    parallelogram/rectangle; the answer is ``base*height/2`` or ``base*height ==
    problem.correct_value``. Raises if the operands are missing (CLAUDE.md §8.5). The triangle
    path shows the bounding parallelogram ``base*height`` first, then halves it — so the learner
    sees WHY the 1/2 is there (a triangle is half its bounding parallelogram).
    """
    operands = problem.operands
    if operands is None or len(operands) != 3:
        raise ValueError(f"area problem {problem.problem_id} needs (base, height, mode) operands")
    base, height = int(operands[0]), int(operands[1])
    triangle = int(operands[2]) == 0
    box = Rational(base * height)
    answer = problem.correct_value
    if triangle:
        return (
            WorkedStep(
                shown=(
                    f"A triangle fits inside a box base x height: {base} x {height} = {box.p} "
                    f"square units."
                ),
                why_prompt="Why does the box (base x height) hold the whole triangle?",
                revealed_value=None,
            ),
            WorkedStep(
                shown="The triangle is exactly HALF that box, so take half of the box's area.",
                why_prompt="Why does a triangle cover exactly half of its bounding box?",
                revealed_value=None,
            ),
            WorkedStep(
                shown=f"So the area is half of {box.p}: {box.p} / 2 = {answer.p}.",
                why_prompt="Why would using base x height (without the half) double the answer?",
                revealed_value=answer,
            ),
        )
    return (
        WorkedStep(
            shown="A rectangle or parallelogram's area is base x height — no halving.",
            why_prompt="Why does base x height give the full area of a parallelogram?",
            revealed_value=None,
        ),
        WorkedStep(
            shown=f"Multiply the sides: {base} x {height} = {answer.p} square units.",
            why_prompt="Why does sliding a parallelogram into a rectangle keep its area the same?",
            revealed_value=answer,
        ),
    )


def _terminating_decimal_places(value: Rational) -> int:
    """Decimal places a terminating rational needs — ``max(power of 2, power of 5)`` in its
    reduced denominator (SymPy reduces 2/10 to 1/5, so we factor q rather than assume a
    power-of-ten denominator): 1/5 → 1, 3/20 → 2, 3 → 0."""
    den = value.q
    twos = fives = 0
    while den % 2 == 0:
        den //= 2
        twos += 1
    while den % 5 == 0:
        den //= 5
        fives += 1
    return max(twos, fives)


def _decimal_text(value: Rational) -> str:
    """Render an exact terminating rational as a finite decimal string.

    Pure integer arithmetic, no float (CLAUDE.md §8.2 — no float touches a shown value). Scales
    the value to an integer by the place count, then inserts the point; an integer renders bare."""
    places = _terminating_decimal_places(value)
    if places == 0:
        return str(value.p)
    scaled = int(value * (10**places))  # exact: value has exactly ``places`` decimal places
    sign = "-" if scaled < 0 else ""
    digits = str(abs(scaled)).zfill(places + 1)
    return f"{sign}{digits[:-places]}.{digits[-places:]}"


# ─── The public builder ───────────────────────────────────────────────────────


def worked_example_for(problem: Problem) -> WorkedExample:
    """Build the S4 worked example for the ``Problem`` the learner got stuck on.

    Walks the KC's canonical correct procedure (ARCHITECTURE.md §4) into an ordered
    tuple of ``WorkedStep``s, each with a conceptual "why did this work?" prompt
    (PROJECT.md §3.5 S4). The final step lands on ``problem.correct_value`` by
    construction. Deterministic, pure, no LLM / DB / verifier (CLAUDE.md §8.1/§8.2).

    Raises ``ValueError`` for a problem whose KC procedure needs operands it does not
    carry (CLAUDE.md §8.5 — fail loudly rather than ship a hollow example).
    """
    builder = _STEP_BUILDERS.get(problem.kc)
    if builder is None:
        raise ValueError(f"no worked-example procedure for KC {problem.kc.value}")
    return WorkedExample(problem=problem, steps=builder(problem))


# The per-KC step builders, table-driven (HR.A4) so the engine looks up the procedure rather than
# branching on the KC id — a new lesson registers its builder as a ROW, not an ``elif``. The step
# TEXT stays tutor-rendered here (it is not domain data, so it does not live on the LessonSpec —
# see lesson_spec.py's layering note); table-driving is the generalization, KC-by-KC content stays.
_STEP_BUILDERS: dict[KnowledgeComponentId, Callable[[Problem], tuple[WorkedStep, ...]]] = {
    KnowledgeComponentId.ADDITION_UNLIKE: lambda p: _addition_or_subtraction_steps(
        p, is_addition=True
    ),
    KnowledgeComponentId.SUBTRACTION_UNLIKE: lambda p: _addition_or_subtraction_steps(
        p, is_addition=False
    ),
    KnowledgeComponentId.COMMON_DENOMINATOR: _common_denominator_steps,
    KnowledgeComponentId.EQUIVALENCE: _equivalence_steps,
    KnowledgeComponentId.NUMBER_LINE_PLACEMENT: _number_line_steps,
    KnowledgeComponentId.RATIO_LANGUAGE: _ratio_language_steps,
    KnowledgeComponentId.UNIT_RATE: _unit_rate_steps,
    KnowledgeComponentId.EQUIVALENT_RATIOS: _equivalent_ratios_steps,
    KnowledgeComponentId.PERCENT: _percent_steps,
    KnowledgeComponentId.MULTIPLY_FRACTIONS: _multiply_fractions_steps,
    KnowledgeComponentId.DIVIDE_FRACTIONS: _divide_fractions_steps,
    KnowledgeComponentId.UNIT_CONVERSION: _unit_conversion_steps,
    KnowledgeComponentId.GCF_LCM: _gcf_lcm_steps,
    KnowledgeComponentId.MULTI_DIGIT_DIVISION: _multi_digit_division_steps,
    KnowledgeComponentId.DECIMAL_OPERATIONS: _decimal_operations_steps,
    KnowledgeComponentId.ABSOLUTE_VALUE: _absolute_value_steps,
    KnowledgeComponentId.INTEGER_ADD_SUBTRACT: _integer_add_subtract_steps,
    KnowledgeComponentId.SIGNED_NUMBERS: _signed_numbers_steps,
    KnowledgeComponentId.WRITE_EXPRESSIONS: _write_expression_steps,
    KnowledgeComponentId.EVALUATE_EXPRESSIONS: _evaluate_expression_steps,
    KnowledgeComponentId.EXPONENTS: _exponents_steps,
    KnowledgeComponentId.ONE_STEP_EQUATIONS: _one_step_equations_steps,
    KnowledgeComponentId.EQUIVALENT_EXPRESSIONS: _equivalent_expression_steps,
    KnowledgeComponentId.INEQUALITIES: _inequality_steps,
    KnowledgeComponentId.COORDINATE_PLANE: _coordinate_plane_steps,
    KnowledgeComponentId.CLASSIFY_NUMBER_SETS: _classify_number_sets_steps,
    KnowledgeComponentId.EXPRESSION_PARTS: _expression_parts_steps,
    KnowledgeComponentId.INTEGER_MULTIPLY_DIVIDE: _integer_multiply_divide_steps,
    KnowledgeComponentId.TRIANGLE_PROPERTIES: _triangle_properties_steps,
    KnowledgeComponentId.AREA_POLYGONS: _area_polygons_steps,
    KnowledgeComponentId.VOLUME_FRACTIONAL_EDGES: _volume_fractional_edges_steps,
    # 6.G.3 reuses KC_coordinate_plane's "read the order, then plot" steps — the answer is the same
    # point-set form, and the steps land on the canonical points whether one corner or four.
    KnowledgeComponentId.POLYGONS_COORDINATE_PLANE: _coordinate_plane_steps,
    KnowledgeComponentId.SURFACE_AREA_NETS: _surface_area_nets_steps,
    KnowledgeComponentId.MEAN_ABSOLUTE_DEVIATION: _mean_absolute_deviation_steps,
    KnowledgeComponentId.CENTER_SPREAD_SHAPE: _center_spread_steps,
    KnowledgeComponentId.SUMMARY_STATISTICS: _summary_statistics_steps,
    KnowledgeComponentId.DATA_DISPLAYS: _data_displays_steps,
    KnowledgeComponentId.CATEGORICAL_DATA: _categorical_data_steps,
    KnowledgeComponentId.STATISTICAL_QUESTIONS: _statistical_questions_steps,
}


__all__ = [
    "WorkedExample",
    "WorkedStep",
    "worked_example_for",
]
