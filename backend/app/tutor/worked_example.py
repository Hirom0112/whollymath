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

from app.domain.knowledge_components import KnowledgeComponentId
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
    KnowledgeComponentId.ONE_STEP_EQUATIONS: _one_step_equations_steps,
}


__all__ = [
    "WorkedExample",
    "WorkedStep",
    "worked_example_for",
]
