"""The reactive-remediation router (Slice P0.4) — drops a struggling learner one level down.

This is the live wiring CURRICULUM_STANDARD.md §11 describes: when a 6th grader struggles on a
grade-level lesson, drop them to the prerequisite the lesson rests on, make them master it, then
resume the parent where they paused. The pieces this composes are ALREADY BUILT and committed:

  - the WHEN — the §11.2 trigger is the existing §3.7 ``SustainedHelpNeedGate``
    (``intervention_gate``) firing on the live HelpNeed stream; this module invents no new trigger.
  - the routing TABLE — ``domain.prerequisites.REMEDIATION_ROUTING`` / ``remediation_targets`` maps
    each grade-6 KC to its one-level-down prerequisite(s). Owned by ``domain``; never edited here.
  - the flow STATE MACHINE — ``policy.remediation_flow`` (the "R" state, the pause/resume edges).
  - the wire PROJECTION — ``api.remediation_view`` shapes the active flow into ``RemediationView``.

What THIS module adds, and why it lives in ``policy`` (not ``domain``): the §11.3 SELECTOR that
picks ONE prerequisite from a lesson's row, and the §11.4 HARD-GATE predicate. Both read learner
state (the per-KC mastery the BKT model tracks) and policy semantics (the magnitude/operation error
flavor the §3.6 surface policy already routes on), so they are decision logic, not the static
prerequisite data — they belong beside the other policy rules, and keeping them here leaves
``domain/prerequisites.py`` untouched (the KC-lane boundary).

Pure / deterministic (CLAUDE.md §7, §8.1/§8.2): no SymPy, no LLM, no DB — same inputs, same target.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.prerequisites import remediation_targets
from app.domain.verifier import ErrorCategory

# A KC mastery probability that has not been observed this session defaults to this when the
# selector reads it — high enough that an UNTOUCHED prerequisite never looks like the "weakest" one
# (the lowest-mastery rule §11.3 signal 2 should point at a skill the learner has actually shown
# weakness on, not one we simply have no evidence for). A missing entry is normal runtime data (the
# learner hasn't reached that KC yet), not a programming error — so we stay total rather than
# raising (§8.5 applies to programmer mistakes; this is data absence).
_UNKNOWN_MASTERY = 1.0

# The §11.3 error-category bias as an explicit, source-faithful classification of the FOUNDATION
# prerequisites by error flavor. §11.3 names the bias by concrete example: a MAGNITUDE slip (the
# learner misjudged how big the amount is) points at the magnitude skill — placing a number on the
# line; an OPERATION slip (the procedure broke) points at the arithmetic skill — adding/subtracting
# fractions. We pin exactly those, the same magnitude↔number-line / operation↔arithmetic split the
# §3.6 surface policy routes a wrong answer on (MAGNITUDE→S2 number line, OPERATION→S3 fraction
# bars; ``transitions._state_for_error_kind``). A prerequisite NOT listed here (equivalence, common
# denominator, and any future/unbuilt KC) carries no magnitude-vs-operation flavor — so signal 1
# abstains for it and signal 2 (lowest mastery) decides alone. An explicit map (rather than deriving
# the flavor from the registry's representation list) is used deliberately: the representation lists
# are too broad to separate the conceptual prereqs (equivalence advertises the same surfaces as
# addition), so a derivation would misclassify; this states the §11.3 intent directly and reads
# plainly (CLAUDE.md §8.5).
_MAGNITUDE_FLAVORED: frozenset[KnowledgeComponentId] = frozenset(
    {KnowledgeComponentId.NUMBER_LINE_PLACEMENT}
)
_OPERATION_FLAVORED: frozenset[KnowledgeComponentId] = frozenset(
    {KnowledgeComponentId.ADDITION_UNLIKE, KnowledgeComponentId.SUBTRACTION_UNLIKE}
)


def _error_flavor_matches(prereq: KnowledgeComponentId, error_category: ErrorCategory) -> bool:
    """Whether ``prereq`` matches the §11.3 error-category bias for ``error_category``.

    §11.3 signal 1: a MAGNITUDE error biases toward the magnitude-flavored prerequisite (the number
    line, ``_MAGNITUDE_FLAVORED``); an OPERATION error biases toward the operation-flavored one (the
    fraction add/subtract procedure, ``_OPERATION_FLAVORED``). A prereq in neither set, or a
    FORMAT/OTHER/NONE error (which carry no magnitude-vs-operation signal), matches nothing — so
    signal 1 abstains and signal 2 (lowest mastery) decides alone.
    """
    if error_category is ErrorCategory.MAGNITUDE:
        return prereq in _MAGNITUDE_FLAVORED
    if error_category is ErrorCategory.OPERATION:
        return prereq in _OPERATION_FLAVORED
    return False


def select_remediation_target(
    parent_kc: KnowledgeComponentId,
    *,
    error_category: ErrorCategory,
    mastery: Mapping[KnowledgeComponentId, float],
) -> KnowledgeComponentId | None:
    """Pick the ONE prerequisite to drop ``parent_kc`` to, per CURRICULUM_STANDARD.md §11.3.

    Returns ``None`` when ``parent_kc`` is terminal — the five foundation fraction KCs, which carry
    no routed drop (§11.1: no auto-drop below the foundation; a learner struggling there stays and
    works it). Otherwise it picks from the lesson's listed prerequisites (``remediation_targets``)
    using the two §11.3 signals, in order:

      1. **Error-category bias** narrows the candidates to the flavor the slip points at — a
         MAGNITUDE error to the number-line-flavored prereq(s), an OPERATION error to the
         add/subtract-flavored one(s) (see ``_error_flavor_matches``). If the error has no flavored
         match in the row, this signal abstains and ALL listed prereqs stay in play.
      2. **Lowest mastery** decides within whatever set signal 1 left — drop to the WEAKEST of
         those, the one the learner most needs to shore up (BKT per-KC probability, lowest wins).

    Ties (equal mastery) break on the §11.1 listing order (the natural primary first), so the choice
    is deterministic (PROJECT.md §4.1). ``mastery`` is the per-KC probability lookup; a KC absent
    from it is treated as ``_UNKNOWN_MASTERY`` so an untouched prereq never reads as weakest.
    """
    candidates = remediation_targets(parent_kc)
    if not candidates:
        return None  # terminal foundation KC — no drop (§11.1)

    # Signal 1: keep only the error-flavored prereqs, if any of the row matches the error flavor.
    flavored = tuple(c for c in candidates if _error_flavor_matches(c, error_category))
    in_play = flavored if flavored else candidates

    # Signal 2: the weakest of those (lowest BKT mastery); listing order breaks ties because ``min``
    # is stable over the source tuple, which is the §11.1 listing order (natural primary first).
    return min(in_play, key=lambda kc: mastery.get(kc, _UNKNOWN_MASTERY))


__all__ = ["select_remediation_target"]
