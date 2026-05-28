"""HelpNeed training labels — the "unproductive state" target (Slice 3.4).

The HelpNeed predictor estimates the probability that a learner is in an
UNPRODUCTIVE state at a turn (PROJECT.md §3.7, ARCHITECTURE.md §8). To train it on
the EDM Cup traces we need a label per parsed turn: was this turn unproductive?

**Definition (decision 2026-05-27).** A turn is unproductive when the learner

  - gave up — asked for the answer (``requested_answer``), OR
  - never solved it — the turn did not reach a correct response (``not correct``), OR
  - floundered — made ``WRONG_ATTEMPT_THRESHOLD`` (3) or more WRONG tries, OR
  - leaned on help — used ``HINT_DEPENDENCE_THRESHOLD`` (2) or more hints.

Otherwise it is PRODUCTIVE — including the important case of a single wrong try
followed by self-correction. Distinguishing productive struggle from unproductive
struggle is the whole point (PROJECT.md §3.7; the design protects productive
struggle, cf. the 0.D.5 productive-struggle window). The thresholds are tunable and
named so a change is a deliberate, reviewed edit (the decision log will show it).

No LLM, no SymPy, no DB here (CLAUDE.md §8.1/§8.2) — a pure function of one
``EdmCupTurn``. Deterministic: same turn ⇒ same label (PROJECT.md §4.1).
"""

from __future__ import annotations

from app.helpneed.parse_edmcup import EdmCupTurn

# 3+ WRONG tries is floundering (even if the learner eventually gets it). Two wrong
# tries then a self-correction stays "productive" — the decision deliberately blesses
# a bounded amount of struggle. Tunable in week 4-5 against the personas (0.D.5 style).
WRONG_ATTEMPT_THRESHOLD = 3

# 2+ hints on one problem is hint-dependence (the §3.7 failure mode); one hint is fine.
HINT_DEPENDENCE_THRESHOLD = 2


def is_unproductive(turn: EdmCupTurn) -> bool:
    """Whether ``turn`` is an UNPRODUCTIVE state (the HelpNeed=1 label, §3.7).

    ``attempt_count`` counts response events (wrong + correct); the WRONG tries are
    that minus the one correct response when the turn ended correctly. We threshold
    on wrong tries so "3+ wrong" means genuine floundering, not "answered on the 3rd
    try after two reasonable misses".
    """
    wrong_attempts = turn.attempt_count - (1 if turn.correct else 0)
    return (
        turn.requested_answer
        or not turn.correct
        or wrong_attempts >= WRONG_ATTEMPT_THRESHOLD
        or turn.hint_count >= HINT_DEPENDENCE_THRESHOLD
    )


__all__ = [
    "HINT_DEPENDENCE_THRESHOLD",
    "WRONG_ATTEMPT_THRESHOLD",
    "is_unproductive",
]
