"""The policy-enforceable refuse-rules (Slice 2.7 / PROJECT.md §3.8).

The PRD explicitly asks us to define what the interface refuses to change
automatically (PROJECT.md §3.8, ARCHITECTURE.md §7, §14 invariant 6). "Adapt with
restraint" (ARCHITECTURE.md §2) — a UI that constantly morphs is a worse result
than one that holds still. The §3.8 refuse-rules are the guard rails.

Of the six §3.8 rules, FOUR are POLICY-enforceable (pure decision logic — this
module) and TWO are FRONTEND/UI concerns (deferred to the frontend):

  POLICY-ENFORCEABLE (here):
    1. Never change state mid-problem        -> ``is_state_change_allowed``
    3. Never change state because of a pause  -> enforced in ``transitions.py``
       (an ``IdleNudge`` can only yield a ``Nudge``/``NoChange``, never a
       ``StateChange``); re-asserted by the refuse-rule tests.
    4. Never present a new state without a label -> enforced by ``Transition``
       carrying a non-empty ``label`` on every path (``transitions.py``).
    5. Never auto-help in the first 60s except on a wrong answer or explicit hint
       request -> ``may_auto_help``.

  DEFERRED TO THE FRONTEND (NOT built here — these are render-time UI concerns,
  not decision logic; CLAUDE.md §7 keeps UI in ``frontend/``):
    2. Never silently remove the learner's own work — prior work is preserved in a
       "your previous work" panel. (A UI rendering rule.)
    6. When help IS shown, render it inline in the workspace, not as a separate
       dialog (the Maniktala Assertions pattern). (A UI rendering rule.)

This module is pure decision logic: no SymPy, no LLM, no DB (CLAUDE.md §7,
§8.1/§8.2; ARCHITECTURE.md §14 invariants 1 & 5).
"""

from __future__ import annotations

from dataclasses import dataclass

# PROJECT.md §0.D.5 / §3.8 rule 5: the productive-struggle window. Auto-help is
# refused during the FIRST 60 seconds of a problem unless the learner already got
# a wrong answer or explicitly asked for a hint. Tunable in weeks 4-5 (PROJECT.md
# §8); named so the boundary is not a magic number.
PRODUCTIVE_STRUGGLE_WINDOW_SECONDS = 60


def is_state_change_allowed(*, problem_in_progress: bool) -> bool:
    """Refuse-rule 1: a state change is allowed only BETWEEN problems.

    "State changes happen between problems, not during one" (PROJECT.md §3.8 rule 1,
    ARCHITECTURE.md §7). The tutor session loop computes a transition with
    ``transitions.next_transition`` but must gate APPLYING it on this guard: if a
    problem is in progress, hold the transition until the problem ends. Keeping the
    guard separate from ``next_transition`` keeps the policy pure (decide now, apply
    when allowed) and makes the rule independently testable.
    """
    return not problem_in_progress


@dataclass(frozen=True)
class AutoHelpRequest:
    """The inputs refuse-rule 5 needs to decide whether proactive help may fire.

    Frozen value object describing the current problem's help context:

    - ``seconds_into_problem``: elapsed time on the CURRENT problem.
    - ``had_wrong_answer``: whether the learner has already submitted a wrong
      answer on this problem (a wrong answer opens the help window early).
    - ``explicit_hint_request``: whether the learner explicitly asked for a hint
      (an explicit request always opens the window — the learner asked).

    This describes *proactive* (auto) help only — the HelpNeed layer firing on its
    own (ARCHITECTURE.md §8). It does not gate help the learner explicitly requests
    beyond recording that the request happened.
    """

    seconds_into_problem: int
    had_wrong_answer: bool
    explicit_hint_request: bool


def may_auto_help(request: AutoHelpRequest) -> bool:
    """Refuse-rule 5: may proactive help fire now? Protects productive struggle.

    "Never auto-help in the first 60 seconds of a problem, except in response to a
    wrong answer or explicit hint request" (PROJECT.md §3.8 rule 5; §0.D.5
    productive-struggle window = 60s). So help may fire when ANY of:

      - the learner has made a wrong answer on this problem, OR
      - the learner explicitly requested a hint, OR
      - the protected first-60s window has fully elapsed
        (``seconds_into_problem > 60`` — the window is the FIRST 60 seconds, so 60s
        exactly is still inside it).

    Outside those, proactive help is refused: the learner is in early, silent
    struggle and the UI must not interrupt (ARCHITECTURE.md §2, §14 invariant 6).
    """
    if request.had_wrong_answer or request.explicit_hint_request:
        return True
    return request.seconds_into_problem > PRODUCTIVE_STRUGGLE_WINDOW_SECONDS


__all__ = [
    "PRODUCTIVE_STRUGGLE_WINDOW_SECONDS",
    "AutoHelpRequest",
    "is_state_change_allowed",
    "may_auto_help",
]
