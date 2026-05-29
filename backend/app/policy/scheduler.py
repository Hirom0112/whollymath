"""The live problem scheduler — interleaving + representation rotation (Slice 4.x MVP).

PROJECT.md §3.6 / decision 0.D.5: mastery evidence must come from an INTERLEAVED set
(≥3 items across ≥2 KCs), not a blocked run of one KC, and from ≥2 representations of the
KC (the §3.4 rules the mastery model enforces). The earlier live default just stayed on the
KC just practiced in one representation — so the experience was monotonous AND the mastery
model's interleaving (rule 4) and representation-diversity (rule 2) rules could never fire,
making mastery unreachable in the live product even though the model was correct.

This module is the small, deterministic scheduler that fixes that. Given the session's GOAL
KC (the cold-start route) and how many problems have been served, it picks the next
``(kc, representation)`` so that:

  - the goal KC is rotated through the representations the LIVE surface can actually render
    and answer (so rule 2 becomes satisfiable), and
  - a companion KC is interleaved in on a fixed cadence (so rule 4 — ≥2 KCs — fires).

Pure and deterministic (CLAUDE.md §8.1): no LLM, no DB, no randomness — the same inputs give
the same schedule (PROJECT.md §4.1). It deliberately encodes only what the current frontend
can render+answer; KCs/representations without a live answer widget are not scheduled (a
surface must never serve a problem with no usable input — the coherence rule this whole pass
is about). The full adaptive, HelpNeed-driven scheduler is still future work; this is the
honest interleaving MVP that makes the live journey varied and mastery reachable.
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId, Representation

_KC = KnowledgeComponentId
_REP = Representation

# Representations the LIVE surface can render AND answer, per KC, in rotation order. This is
# the contract with the frontend widgets: SYMBOLIC → the fraction editor / yes-no, NUMBER_LINE
# → the draggable marker (placement OR an arithmetic result that lands in 0–1). A KC with two
# entries can satisfy the mastery model's "≥2 representations" rule (§3.4 rule 2) live.
_LIVE_REPRESENTATIONS: dict[KnowledgeComponentId, tuple[Representation, ...]] = {
    _KC.ADDITION_UNLIKE: (_REP.SYMBOLIC, _REP.NUMBER_LINE),
    _KC.SUBTRACTION_UNLIKE: (_REP.SYMBOLIC, _REP.NUMBER_LINE),
    # SYMBOLIC = fill-the-top / yes-no; WORD_PROBLEM = a story "same amount?" yes-no judgment.
    _KC.EQUIVALENCE: (_REP.SYMBOLIC, _REP.WORD_PROBLEM),
    # NUMBER_LINE = drag the marker; SYMBOLIC = "is a greater than b?" magnitude comparison.
    _KC.NUMBER_LINE_PLACEMENT: (_REP.NUMBER_LINE, _REP.SYMBOLIC),
    # SYMBOLIC = the whole-number "shared piece-size" entry (§3.4.1). PRACTICE-ONLY for now: only
    # one live representation, so is_masterable_live is False — the AREA_MODEL alignment form (the
    # second representation that makes it masterable) is added once its surface widget exists.
    _KC.COMMON_DENOMINATOR: (_REP.SYMBOLIC,),
}

# The companion KC interleaved alongside each goal so a session always spans ≥2 KCs (rule 4).
# Chosen to be pedagogically adjacent and to have a live answer widget.
_COMPANION: dict[KnowledgeComponentId, KnowledgeComponentId] = {
    _KC.ADDITION_UNLIKE: _KC.SUBTRACTION_UNLIKE,
    _KC.SUBTRACTION_UNLIKE: _KC.ADDITION_UNLIKE,
    _KC.EQUIVALENCE: _KC.ADDITION_UNLIKE,
    _KC.NUMBER_LINE_PLACEMENT: _KC.EQUIVALENCE,
    # Common denominator interleaves with equivalence (it IS applied equivalence — §3.4.1) so a
    # CD lesson spans ≥2 KCs and next_spec never lacks a companion on the cadence turn.
    _KC.COMMON_DENOMINATOR: _KC.EQUIVALENCE,
}

# Every third served problem is the companion KC; the other two are the goal. This keeps the
# session focused on the route the learner chose while guaranteeing the interleaving the
# mastery rule needs (≥2 KCs, with the goal among them) — 0.D.5 cadence, applied live.
_COMPANION_EVERY = 3


def live_representations(kc: KnowledgeComponentId) -> tuple[Representation, ...]:
    """The representations the live surface can render AND answer for ``kc`` (the contract
    with the frontend widgets). Used by the scheduler and the live transfer probe."""
    return _LIVE_REPRESENTATIONS.get(kc, (_REP.SYMBOLIC,))


def next_spec(
    goal_kc: KnowledgeComponentId, served_index: int
) -> tuple[KnowledgeComponentId, Representation]:
    """Pick the next ``(kc, representation)`` to serve.

    ``served_index`` is the 0-based index of the problem being served AFTER the cold-start
    item (0 = the first follow-on problem). Every ``_COMPANION_EVERY``-th item is the
    companion KC; the rest are the goal KC, rotated through its live representations so the
    learner answers it more than one way (rule 2). Deterministic in its two inputs.
    """
    if served_index < 0:
        raise ValueError("served_index must be >= 0")

    if (served_index + 1) % _COMPANION_EVERY == 0:
        companion = _COMPANION[goal_kc]
        return companion, live_representations(companion)[0]

    reps = live_representations(goal_kc)
    goal_items_before = sum(1 for i in range(served_index) if (i + 1) % _COMPANION_EVERY != 0)
    return goal_kc, reps[goal_items_before % len(reps)]


def is_masterable_live(goal_kc: KnowledgeComponentId) -> bool:
    """Whether a learner can reach the mastery model's bar on this KC with the CURRENT live
    surface — i.e. the KC has ≥2 live representations (rule 2) and a companion to interleave
    with (rule 4). Honest signal for the experience: a route that returns False can be
    practiced and shows progress, but cannot yet hit declared mastery."""
    return len(live_representations(goal_kc)) >= 2 and goal_kc in _COMPANION


__all__ = ["is_masterable_live", "live_representations", "next_spec"]
