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
    # Grade-6 Unit 1: SYMBOLIC = the part-whole fraction entered in the editor. PRACTICE-ONLY
    # (one live representation, like COMMON_DENOMINATOR) until a ratio word-problem widget lands
    # (T3), at which point adding WORD_PROBLEM here makes it masterable with no other change.
    _KC.RATIO_LANGUAGE: (_REP.SYMBOLIC,),
    # Grade-6 Unit 1: SYMBOLIC = the numeric "amount for ONE" entry. PRACTICE-ONLY (one live
    # representation, like COMMON_DENOMINATOR) until a numeric word-problem widget lands (T3),
    # at which point adding WORD_PROBLEM here makes it masterable with no other change.
    _KC.UNIT_RATE: (_REP.SYMBOLIC,),
    _KC.EQUIVALENT_RATIOS: (_REP.SYMBOLIC,),  # numeric missing-term entry; practice-only
    _KC.PERCENT: (_REP.SYMBOLIC,),  # numeric "percent of" entry; practice-only
    # Grade-6 Unit 2 (T2): SYMBOLIC = the product entered in the fraction editor. PRACTICE-ONLY
    # until the AREA_MODEL multiply widget lands (T3), then adding AREA_MODEL makes it masterable.
    _KC.MULTIPLY_FRACTIONS: (_REP.SYMBOLIC,),
    # Grade-6 Unit 2 (T2): SYMBOLIC = the quotient entered in the fraction editor. PRACTICE-ONLY
    # (like MULTIPLY_FRACTIONS) until the AREA_MODEL division widget lands (T3), then adding
    # AREA_MODEL here makes it masterable with no other change.
    _KC.DIVIDE_FRACTIONS: (_REP.SYMBOLIC,),
    # Grade-6 Unit 1: SYMBOLIC = the numeric "how many small units" entry. PRACTICE-ONLY (one live
    # representation, like UNIT_RATE) until a numeric word-problem widget lands (T3), at which point
    # adding WORD_PROBLEM here makes it masterable with no other change.
    _KC.UNIT_CONVERSION: (_REP.SYMBOLIC,),
    # Grade-6 Unit 2: SYMBOLIC = the single integer (GCF or LCM) entered in the editor. PRACTICE-
    # ONLY until a whole-number NUMBER_LINE factor/multiple widget lands (T3), then adding
    # NUMBER_LINE here makes it masterable with no other change.
    _KC.GCF_LCM: (_REP.SYMBOLIC,),
    # Grade-6 Unit 2: SYMBOLIC = the integer quotient entered in the editor. PRACTICE-ONLY until
    # the AREA_MODEL equal-groups widget lands (T3), then adding AREA_MODEL makes it masterable.
    _KC.MULTI_DIGIT_DIVISION: (_REP.SYMBOLIC,),
    # Grade-6 Unit 2: SYMBOLIC = the decimal product entered in the editor (the decimal-string
    # answer the verifier now parses exactly). PRACTICE-ONLY until the AREA_MODEL decimal-grid
    # widget lands (T3), then adding AREA_MODEL here makes it masterable with no other change.
    _KC.DECIMAL_OPERATIONS: (_REP.SYMBOLIC,),
}

# NOTE (2026-05-29): cross-skill interleaving was REMOVED — lessons are now single-skill (a
# number-line lesson is number-line questions only; product-owner decision). The mastery
# model's varied-practice gate (rule 4) is now met within the skill by rotating its
# representations (see ``next_spec`` + ``mastery_model._has_interleaved_mastery_set``), so the
# old ``_COMPANION`` map and companion cadence are gone.

# The easy→hard difficulty ramp (CP.B; CURRICULUM_DRAFT.md §1.1). Each served problem gets a
# difficulty tier (1=friendliest … 4=hardest, matching ``problem_generators._DENOM_BY_DIFFICULTY``)
# that climbs every ``_RAMP_STEP`` problems, so a lesson opens with a gentle warm-up and quickly
# works up to genuine 6th-grade rigor (large denominators, then improper, then negatives on the
# number-line skill) — "warm up, then increase difficulty". Capped at the top tier, so a learner
# practising past the ramp stays hard (never wraps back to easy). A SMALL step keeps the climb
# brisk so the hard content shows up early, not buried 8+ problems in. Deterministic in
# ``served_index`` like the rest of the scheduler.
_RAMP_STEP = 2
_MAX_DIFFICULTY = 4


def difficulty_for(served_index: int) -> int:
    """The difficulty tier for the problem at ``served_index`` (0-based, after the cold-start
    item). Climbs one tier every ``_RAMP_STEP`` problems, capped at ``_MAX_DIFFICULTY`` — an
    easy→hard ramp that never regresses (CP.B). ``served_index`` < 0 is treated as the first
    rung (tier 1) so a caller need not special-case the opening problem."""
    if served_index < 0:
        return 1
    return min(_MAX_DIFFICULTY, 1 + served_index // _RAMP_STEP)


def live_representations(kc: KnowledgeComponentId) -> tuple[Representation, ...]:
    """The representations the live surface can render AND answer for ``kc`` (the contract
    with the frontend widgets). Used by the scheduler and the live transfer probe."""
    return _LIVE_REPRESENTATIONS.get(kc, (_REP.SYMBOLIC,))


def next_spec(
    goal_kc: KnowledgeComponentId, served_index: int
) -> tuple[KnowledgeComponentId, Representation]:
    """Pick the next ``(kc, representation)`` to serve.

    **Single-skill lessons (2026-05-29 product-owner decision).** A lesson stays on the GOAL
    KC the whole way — a "number-line lesson" is number-line questions only, never a different
    skill mixed in. We rotate the goal KC through its live representations (e.g. number-line
    PLACING then COMPARING) so the learner answers it more than one way; that representation
    mix is what now satisfies the mastery model's varied-practice gate (rule 4, within-skill
    path) and its representation-diversity rule (rule 2). No cross-skill companion is served.

    ``served_index`` is the 0-based index of the problem being served AFTER the first item.
    Deterministic in its two inputs.
    """
    if served_index < 0:
        raise ValueError("served_index must be >= 0")
    reps = live_representations(goal_kc)
    return goal_kc, reps[served_index % len(reps)]


def next_spec_after_outcome(
    goal_kc: KnowledgeComponentId,
    served_index: int,
    *,
    last_correct: bool,
    last_kc: KnowledgeComponentId,
    last_format: Representation,
) -> tuple[KnowledgeComponentId, Representation]:
    """Pick the next ``(kc, representation)`` taking the LAST answer's outcome into account.

    This wraps ``next_spec`` with the adaptive re-practice rule. On a CORRECT answer the
    schedule interleaves exactly as before (``next_spec`` — the goal rotated through its
    representations, the companion on the §0.D.5 cadence), so the interleaving the mastery
    model needs (§3.4 rule 4) is unchanged.

    On a WRONG answer the learner gets MORE practice on the SAME skill they just struggled
    on — the next problem stays on ``last_kc`` (the KC actually answered, which may be the
    goal or the interleaved companion) in the SAME representation they missed (``last_format``,
    a similar type/difficulty), rather than rotating to a different KC. This is the fix for the
    reported "wrong answer rotates to another skill" symptom: a struggling learner should not be
    pulled onto a new KC the moment they slip. ``last_format`` is honored only if it is a live
    representation for ``last_kc`` (so we never serve a dead surface); otherwise we fall back to
    that KC's first live representation.

    Pure and deterministic in its inputs, like ``next_spec`` — the surface-transition policy
    (S1↔S5) is decided separately by ``policy.transitions`` and is unaffected here; this only
    chooses WHICH KC/representation to draw the next problem from.
    """
    if last_correct:
        return next_spec(goal_kc, served_index)
    reps = live_representations(last_kc)
    repractice_format = last_format if last_format in reps else reps[0]
    return last_kc, repractice_format


def is_masterable_live(goal_kc: KnowledgeComponentId) -> bool:
    """Whether a learner can reach the mastery model's bar on this KC with the CURRENT live
    surface. With single-skill lessons (no cross-KC companion), the gate is simply ≥2 live
    representations: that satisfies BOTH rule 2 (representation diversity) and the within-skill
    path of rule 4 (varied practice across representations). A KC with only one live
    representation (common-denominator, until the fraction-bars widget ships) can be practiced
    and show progress but cannot yet hit declared mastery — an honest signal for the experience."""
    return len(live_representations(goal_kc)) >= 2


__all__ = [
    "difficulty_for",
    "is_masterable_live",
    "live_representations",
    "next_spec",
    "next_spec_after_outcome",
]
