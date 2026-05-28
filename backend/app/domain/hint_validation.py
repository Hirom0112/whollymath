"""The SymPy gate that an LLM-rephrased hint preserved every numeric claim (Slice 5.6).

The domain produces the verified-correct canonical hint text deterministically
(``tutor/worked_example.py`` — each ``WorkedStep.shown`` is canonical, SymPy-grounded
text). The LLM only REPHRASES that text warmly (``persona_surface/hint_renderer.py``).
Before a rephrase may be shown to a learner it must pass this gate: SymPy confirms the
rephrase preserved EXACTLY the numeric facts of the canonical text — it dropped none,
altered none, and invented none. This is the "SymPy-validated" half of locked decision
0.D.3 ("LLM slot-fill → SymPy-validated → ≤2 retries → pre-written fallback").

This is the SymPy boundary for that gate, so it lives in ``domain/`` — SymPy is allowed
ONLY here (CLAUDE.md §7, §8.2; ARCHITECTURE.md §14 invariant 5). It runs on help moments
(off the sub-100ms turn loop), where the worked example is assembled anyway.

Safety posture — mirrored from ``verifier.py`` (``_parse_to_rational``): we NEVER call
``eval`` or ``sympify`` on free text. The candidate is model-generated prose, so treating
it as an evaluable expression would widen the input surface and could let an injected
expression masquerade as a number. Instead we scan for number TOKENS with a tight regex
(an ``a/b`` fraction or a bare integer) and build each ``Rational`` from parsed ``int``s.
The comparison is over VALUE (a ``Rational`` set), so an unreduced "2/4" and "1/2" are the
same claim — the gate judges the numeric magnitude, exactly as the verifier does (§3.1
does not require lowest terms).

No LLM, no DB, no network here — a pure, deterministic string→set→bool pipeline.
"""

from __future__ import annotations

import re

from sympy import Rational

# A number TOKEN is either an ``a/b`` fraction or a bare integer, with a word boundary on
# each side so "12" in "12ths" is not mistaken for a standalone integer and a fraction's
# two halves are captured together (not as two integers). The fraction alternative comes
# FIRST so "1/3" matches as one fraction rather than the integer "1" then "/3".
_NUMBER_TOKEN = re.compile(r"\b\d+/\d+\b|\b\d+\b")


def extract_rationals(text: str) -> set[Rational]:
    """Parse every integer and ``a/b`` fraction token in ``text`` into the distinct values.

    Returns the SET of distinct ``sympy.Rational`` magnitudes named by digit tokens in the
    text. "1/3" yields the single value ``Rational(1, 3)`` (not the integers 1 and 3);
    a standalone "12" yields ``Rational(12)``. Repeated or equal-valued tokens collapse
    (a set of VALUES), so "2/4" and "1/2" contribute one entry. Spelled-out numbers carry
    no digit token and so contribute nothing — the gate is over digits, deliberately
    (a warm rephrase that spells numbers out has dropped the digit claim the canonical
    text made; see the module docstring).

    We never ``eval``/``sympify`` the text (verifier.py's posture); a zero-denominator
    token (``n/0``) is an undefined magnitude, so it is skipped rather than built into a
    raising ``Rational``.
    """
    values: set[Rational] = set()
    for token in _NUMBER_TOKEN.findall(text):
        if "/" in token:
            numerator_text, _, denominator_text = token.partition("/")
            numerator = int(numerator_text)
            denominator = int(denominator_text)
            if denominator == 0:
                continue  # undefined magnitude — not a numeric claim we can compare
            values.add(Rational(numerator, denominator))
        else:
            values.add(Rational(int(token)))
    return values


def numeric_claims_preserved(canonical_text: str, candidate_text: str) -> bool:
    """True iff ``candidate_text`` carries EXACTLY the canonical text's distinct numbers.

    The gate (decision 0.D.3): the LLM rephrase must neither drop, alter, nor add any
    numeric fact relative to the verified canonical text. We compare the distinct-value
    SETS from ``extract_rationals`` — value-equality, so an unreduced restatement of the
    same magnitude still passes, but a changed/missing/extra number fails. SymPy decides
    the equality (it backs ``Rational`` comparison); no LLM is consulted (§8.2).
    """
    return extract_rationals(candidate_text) == extract_rationals(canonical_text)


__all__ = ["extract_rationals", "numeric_claims_preserved"]
