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
    # Grade-6 Unit 2: SYMBOLIC = the product entered in the fraction editor; AREA_MODEL = the same
    # numeric answer over a fraction-area picture (FractionAreaStimulus, already wired) —
    # the EVALUATE_EXPRESSIONS pattern, no new input widget. MASTERABLE: two live representations.
    # (Promoted 2026-06-04 per the panel audit; the second rep already renders.)
    _KC.MULTIPLY_FRACTIONS: (_REP.SYMBOLIC, _REP.AREA_MODEL),
    # Grade-6 Unit 2: SYMBOLIC = the quotient in the fraction editor; AREA_MODEL = the same answer
    # over the "how many c/d fit in a/b" area picture (FractionAreaStimulus). MASTERABLE (2 reps).
    _KC.DIVIDE_FRACTIONS: (_REP.SYMBOLIC, _REP.AREA_MODEL),
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
    # Grade-6 Unit 2: SYMBOLIC = the decimal answer in the editor (parsed exactly by the verifier);
    # AREA_MODEL = the same answer over the place-value picture (DecimalPlaceValueStimulus, already
    # wired in scene.py). MASTERABLE: two live representations, no new input widget.
    # (Promoted 2026-06-04 per the panel audit; the second rep already renders.)
    _KC.DECIMAL_OPERATIONS: (_REP.SYMBOLIC, _REP.AREA_MODEL),
    # Grade-6 Unit 3: SYMBOLIC = the distance in the editor; NUMBER_LINE = the same scalar over the
    # AbsoluteValueStimulus picture (distance-from-zero, already wired). MASTERABLE (2 reps).
    # (Promoted 2026-06-04 per the panel audit; absolute value IS a distance, so the line is it.)
    _KC.ABSOLUTE_VALUE: (_REP.SYMBOLIC, _REP.NUMBER_LINE),
    # Grade-6 Unit-INT: SYMBOLIC = the signed sum; NUMBER_LINE = the same answer over the directed-
    # jump picture (IntegerJumpStimulus, already wired). MASTERABLE (2 reps). (Promoted 2026-06-04.)
    _KC.INTEGER_ADD_SUBTRACT: (_REP.SYMBOLIC, _REP.NUMBER_LINE),
    # Grade-6 Unit 3: SYMBOLIC = the opposite in the editor; NUMBER_LINE = the same answer over the
    # SignedPointStimulus picture (reflection across zero, already wired). MASTERABLE (2 reps).
    # (Promoted 2026-06-04 per the panel audit; signed numbers ARE positions on the line.)
    _KC.SIGNED_NUMBERS: (_REP.SYMBOLIC, _REP.NUMBER_LINE),
    # Grade-6 Unit 4: EXPRESSION = the typed algebra string (the ExpressionInput widget). Live on
    # EXPRESSION (not SYMBOLIC) — this KC's default + only answer surface; the WORD_PROBLEM rep is
    # the phrase framing with no surface state. PRACTICE-ONLY (one live rep); a second masterable
    # surface (e.g. a tile/builder) would be added here when its widget lands.
    _KC.WRITE_EXPRESSIONS: (_REP.EXPRESSION,),
    # Grade-6 Unit 4: SYMBOLIC = the numeric value entered in the editor ("evaluate 3x + 2 when
    # x = 4"); AREA_MODEL = the same total read off an array/area picture (a rows of x squares plus
    # b extra). Both surfaces are LIVE and answered with the SAME numeric value, so this KC is
    # MASTERABLE (two real representations meet §3.4 rule 2) — unlike the practice-only Grade-6 KCs.
    _KC.EVALUATE_EXPRESSIONS: (_REP.SYMBOLIC, _REP.AREA_MODEL),
    # Grade-6 Unit 4: SYMBOLIC = the power "base^exp" evaluated in the editor; AREA_MODEL = the same
    # value read off a geometric picture (a side-base square's area for ^2, a cube's volume for ^3).
    # Both surfaces are LIVE and answered with the SAME numeric value, so this KC is MASTERABLE (two
    # real representations meet §3.4 rule 2) — like EVALUATE_EXPRESSIONS, not the practice-only KCs.
    _KC.EXPONENTS: (_REP.SYMBOLIC, _REP.AREA_MODEL),
    # Grade-6 Unit 5: the FIRST Grade-6 KC built MASTERABLE-LIVE. SYMBOLIC = the equation
    # (x + 5 = 12 / 3x = 12) with x entered in the editor; WORD_PROBLEM = the same equation as a
    # story, still answered with the value of x (its surface state is SYMBOLIC_FOCUS, like the
    # equivalence word-problem). TWO live reps ⇒ is_masterable_live is True — a learner can be
    # correct in two representations of the one skill (mastery rule 2).
    _KC.ONE_STEP_EQUATIONS: (_REP.SYMBOLIC, _REP.WORD_PROBLEM),
    # Grade-6 Unit 4: EXPRESSION = the typed algebra string (the ExpressionInput widget). Live on
    # EXPRESSION (not SYMBOLIC) — its only answer surface; WORD_PROBLEM is the ontology framing with
    # no surface state, and SYMBOLIC maps to the fraction editor, which cannot accept a typed
    # algebra answer. PRACTICE-ONLY (one live rep); a second masterable surface (e.g. an
    # expression-tile builder) would be added here when its widget lands.
    _KC.EQUIVALENT_EXPRESSIONS: (_REP.EXPRESSION,),
    # Grade-6 Unit 5: INEQUALITY = the typed relational string (the inequality input widget). Live
    # on INEQUALITY (its only answer surface; WORD_PROBLEM is the constraint framing with no surface
    # state). PRACTICE-ONLY (one live rep, like KC_write_expressions); a second masterable surface
    # (e.g. a number-line range picker) would be added here when its widget lands.
    _KC.INEQUALITIES: (_REP.INEQUALITY,),
    # Grade-6 Unit 3: COORDINATE_PLANE = the four-quadrant point-plotting grid (the coordinate-plane
    # widget). Live on COORDINATE_PLANE (its default + only answer surface); the WORD_PROBLEM rep is
    # the phrase framing with no surface state. PRACTICE-ONLY (one live rep) — a second masterable
    # surface (e.g. a symbolic "name the coordinates" entry) would be added here when its widget
    # lands and the answer can be graded the same way.
    _KC.COORDINATE_PLANE: (_REP.COORDINATE_PLANE,),
    # Grade-6 Unit 3 (TEKS 6.2A): NUMBER_SETS = the set-of-labels answer (the ClassifySets widget).
    # Live on NUMBER_SETS — its only answer surface; WORD_PROBLEM is the ontology framing with no
    # surface state. PRACTICE-ONLY (one live rep); a second masterable surface (e.g. a Venn-diagram
    # placement widget) would be added here when its widget lands.
    _KC.CLASSIFY_NUMBER_SETS: (_REP.NUMBER_SETS,),
    # Grade-6 Unit 4: SYMBOLIC = the single whole number (coefficient / constant / term-count)
    # entered in the existing NUMERIC editor. Live on SYMBOLIC — its only answer surface;
    # WORD_PROBLEM is the phrase framing with no surface state. PRACTICE-ONLY (one live rep); there
    # is no second concrete widget for naming a part, so SYMBOLIC stays the only live surface.
    _KC.EXPRESSION_PARTS: (_REP.SYMBOLIC,),
    # Grade-6 Unit-INT (TEKS 6.3C/D): SYMBOLIC = the signed product/quotient; NUMBER_LINE = the same
    # answer (a product is repeated directed jumps from zero). MASTERABLE (2 reps). Pictureless for
    # now — no scene deriver yet (EVALUATE_EXPRESSIONS/MULTI_DIGIT_DIVISION precedent: masterable
    # without a picture); the directed-jump scene is a later polish. (Promoted 2026-06-04.)
    _KC.INTEGER_MULTIPLY_DIVIDE: (_REP.SYMBOLIC, _REP.NUMBER_LINE),
    # Grade-6 Unit 6 (TEKS 6.8A): SYMBOLIC = the missing angle / area as a single number entered in
    # the editor. PRACTICE-ONLY for now; the AREA_MODEL rep (the triangle FIGURE — its angles and
    # its base×height region) is the natural masterable second surface, added here once a
    # triangle-figure input widget lands — deferred to avoid over-scoping this build.
    _KC.TRIANGLE_PROPERTIES: (_REP.SYMBOLIC,),
    # Grade-6 Unit 6: SYMBOLIC = the area computed from the base/height formula entered in the
    # NUMERIC editor; AREA_MODEL = the SAME area read off a unit-square grid (count the squares the
    # shape covers). Both surfaces are LIVE and answered with the SAME numeric area, so this KC is
    # MASTERABLE (two real representations meet §3.4 rule 2) — like EVALUATE_EXPRESSIONS /
    # EXPONENTS, not the practice-only Grade-6 KCs. Area is literally an area-model quantity, so
    # AREA_MODEL is the natural second surface here.
    _KC.AREA_POLYGONS: (_REP.SYMBOLIC, _REP.AREA_MODEL),
    # Grade-6 Unit 6 (6.G.2): SYMBOLIC = the numeric volume (a Rational fraction) entered in the
    # editor. PRACTICE-ONLY for now; the AREA_MODEL rep (a prism's volume IS a 3D area-model — the
    # stack-of-unit-cubes picture) is the natural masterable second surface, but it has no widget
    # yet, so adding it here would promote it — deferred to avoid over-scoping this build.
    _KC.VOLUME_FRACTIONAL_EDGES: (_REP.SYMBOLIC,),
    # Grade-6 Unit 6 (6.G.3): COORDINATE_PLANE = the four-quadrant point-plotting grid (REUSES
    # KC_coordinate_plane's coordinate-plane widget). Live on COORDINATE_PLANE (its default + only
    # answer surface); the WORD_PROBLEM rep is the phrase framing with no surface state.
    # PRACTICE-ONLY (one live rep, like KC_coordinate_plane) — a second masterable surface awaits
    # its own widget.
    _KC.POLYGONS_COORDINATE_PLANE: (_REP.COORDINATE_PLANE,),
    # Grade-6 Unit 6 (6.G.4): SYMBOLIC = the total surface area entered in the editor. PRACTICE-ONLY
    # for now; the AREA_MODEL rep (a net IS an area-model — the six unfolded rectangular faces) is
    # the natural masterable second surface, but it has no widget yet, so adding it here would
    # promote it — deferred to avoid over-scoping this build.
    _KC.SURFACE_AREA_NETS: (_REP.SYMBOLIC,),
    # Grade-6 Unit 7 (6.SP.5c): SYMBOLIC = the MAD value; NUMBER_LINE = the same answer over the
    # set's dot plot (each deviation is a distance from the mean). The plot already renders via
    # stats_stimulus (wired in service.py). MASTERABLE (2 reps). (Promoted 2026-06-04 per panel.)
    _KC.MEAN_ABSOLUTE_DEVIATION: (_REP.SYMBOLIC, _REP.NUMBER_LINE),
    # Grade-6 Unit 7 (6.SP.2): SYMBOLIC = the median/range/IQR; NUMBER_LINE = the same answer read
    # off the data set's dot plot (center & spread along the line). Plot renders via stats_stimulus.
    # MASTERABLE (2 reps). (Promoted 2026-06-04 per panel audit.)
    _KC.CENTER_SPREAD_SHAPE: (_REP.SYMBOLIC, _REP.NUMBER_LINE),
    # Grade-6 Unit 7 (6.SP.3): SYMBOLIC = the single statistic; NUMBER_LINE = the same answer read
    # off the dot plot (the data set IS points on the line). Plot renders via stats_stimulus.
    # MASTERABLE (2 reps). (Promoted 2026-06-04 per panel audit.)
    _KC.SUMMARY_STATISTICS: (_REP.SYMBOLIC, _REP.NUMBER_LINE),
    # Grade-6 Unit 7 (6.SP.4): SYMBOLIC = the count/value read off the display; NUMBER_LINE = the
    # same answer over the rendered dot plot / histogram itself (stats_stimulus, wired in
    # service.py). MASTERABLE (2 reps) — the display IS the standard. (Promoted 2026-06-04.)
    _KC.DATA_DISPLAYS: (_REP.SYMBOLIC, _REP.NUMBER_LINE),
    # Grade-6 Unit 7 (TEKS 6.12D): SYMBOLIC = the single summary value entered in the editor.
    # PRACTICE-ONLY for now; the AREA_MODEL rep (a bar/area graph of the category breakdown) is the
    # natural masterable second surface — but adding it here would promote it, deferred to avoid
    # over-scoping this build.
    _KC.CATEGORICAL_DATA: (_REP.SYMBOLIC,),
    # Grade-6 Unit 7 (6.SP.1): SYMBOLIC = the YES/NO verdict on whether a question is statistical
    # (reuses the yes/no answer surface, NO new widget). PRACTICE-ONLY (one live answer surface);
    # WORD_PROBLEM is the SAME judgment with no separate surface state, so it is advertised for the
    # ≥2-rep contract but is not a live answer surface (and never an error target).
    _KC.STATISTICAL_QUESTIONS: (_REP.SYMBOLIC,),
    # Grade-6 Unit 4/5 (6.EE.9): SYMBOLIC = the scalar dependent value y entered in the
    # NUMBER_ENTRY editor ("y = 3x, find y at x = 4"); COORDINATE_PLANE = the SAME relationship
    # answered by plotting the point (x, y) (REUSES the live coordinate-plane widget). BOTH surfaces
    # are LIVE and built from the same (a, x) relationship, so this KC is MASTERABLE (two real
    # representations meet §3.4 rule 2) — like EVALUATE_EXPRESSIONS, not the practice-only Grade-6
    # KCs. Each rep has a real surface state, so an error on one routes honestly to the other.
    _KC.DEPENDENT_VARS: (_REP.SYMBOLIC, _REP.COORDINATE_PLANE),
    # Grade-6 Unit 5 (6.EE.5): NUMBER_LINE = the YES/NO solution test ("Is x = N a solution to
    # x + b = c?", a candidate at a point on the line; reuses the yes/no answer surface, NO new
    # widget); SYMBOLIC = the scalar solve ("Which value makes x + b = c true?", c − b entered in
    # the NUMBER_ENTRY editor — this is a SYMBOLIC SCALAR KC, not a fraction KC). BOTH surfaces are
    # LIVE and built from the same x + b = c equation, so this KC is MASTERABLE (two real
    # representations meet §3.4 rule 2) — like DEPENDENT_VARS. Each rep has a real surface state, so
    # an error on one routes honestly to the other (never to WORD_PROBLEM, which is not a rep here).
    _KC.EQUATION_SOLUTIONS: (_REP.NUMBER_LINE, _REP.SYMBOLIC),
    # Grade-6 Unit 8 (TEKS 6.14C): SYMBOLIC = the ending balance entered in the NUMBER_ENTRY editor
    # (a currency/decimal answer — a SYMBOLIC SCALAR KC, not a fraction KC); NUMBER_LINE = an
    # overdraft YES/NO check ("is the balance enough to cover a $X withdrawal?", reusing the yes/no
    # answer surface, NO new widget). BOTH surfaces are LIVE and built from one register, so the
    # KC is MASTERABLE (two real representations meet §3.4 rule 2) — like EQUATION_SOLUTIONS. Each
    # rep has a real surface state, so an error on one routes honestly to the other.
    _KC.CHECK_REGISTER: (_REP.SYMBOLIC, _REP.NUMBER_LINE),
    # Grade-6 Unit 8 (TEKS 6.14H): SYMBOLIC = the lifetime-income / income-difference scalar entered
    # in the NUMBER_ENTRY editor. PRACTICE-ONLY (one live answer surface, like UNIT_RATE); the
    # WORD_PROBLEM rep is the salary-scenario framing with no separate surface state, advertised for
    # the ≥2-rep contract but not a live answer surface (and never an error target).
    _KC.LIFETIME_INCOME: (_REP.SYMBOLIC,),
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
