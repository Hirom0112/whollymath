"""The per-lesson contract: one frozen ``LessonSpec`` per KC the engine reads (Slice HR.A1).

The hyperreactive win condition is UNIFORM — a lesson plugs into the live loop because it declares
a spec, not because the engine hard-codes ``if kc is ...`` (HYPERREACTIVE.md §3). This module is
that GATE: it defines the spec + a registry (mirroring the KC and misconception registries) and
populates the 5 fraction lessons. The later slices wire each subsystem to READ this spec — the
verifier loops ``spec.misconceptions`` (HR.A2), signal routing reads ``spec.error_routes`` (HR.A3),
worked-examples / hints / the transfer probe go spec-driven (HR.A4).

Layering (CLAUDE.md §7): this lives in ``domain/`` and therefore imports ONLY domain — it must not
reach up into ``tutor/`` or ``policy/`` (that would invert the layers). So the spec carries the
DOMAIN-level contract — which representations + widgets a lesson offers, where each error category
routes, which misconceptions apply, the procedural generator + difficulty tiers, the transfer-probe
shape, and the standards codes. The tutor-rendered banks (worked-example step text, hint nudge
copy, the concrete transfer items) stay in ``tutor/`` and are refactored to READ this spec in
HR.A4 — they do not move into ``domain/``. Everything here is frozen, deterministic, and pure.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain.curriculum import all_units
from app.domain.knowledge_components import KnowledgeComponentId, Representation, get_kc
from app.domain.misconceptions import MISCONCEPTION_REGISTRY, MisconceptionId
from app.domain.problem_generators import Problem, generate_problem
from app.domain.verifier import ErrorCategory

# The supported procedural-difficulty tiers (problem_generators._DENOM_BY_DIFFICULTY has 1..4).
_DIFFICULTY_TIERS: tuple[int, ...] = (1, 2, 3, 4)


class WidgetId(StrEnum):
    """The live workspace widget that renders a representation (the frontend WidgetContract, HR.A5).

    A backend declaration of which widget each representation needs, so "error routing targets a
    REAL widget" is checkable here and the frontend ``selectWidget`` has one source of truth. The
    matching SVG components live in ``frontend/src/workspace/`` (FractionBar, NumberLine,
    SymbolicEditor — CLAUDE.md §7)."""

    FRACTION_EDITOR = "fraction_editor"  # symbolic
    NUMBER_LINE = "number_line"
    FRACTION_BARS = "fraction_bars"  # area model
    WORD_PROBLEM = "word_problem"
    EXPRESSION = "expression"  # the free-text ExpressionInput (a typed algebra string)
    INEQUALITY = "inequality"  # the free-text inequality input (a typed relational string)
    COORDINATE_PLANE = "coordinate_plane"  # the four-quadrant point-plotting grid widget
    CLASSIFY_SETS = "classify_sets"  # the ClassifySets widget (pick the number sets a value is in)


_WIDGET_FOR_REPRESENTATION: dict[Representation, WidgetId] = {
    Representation.SYMBOLIC: WidgetId.FRACTION_EDITOR,
    Representation.NUMBER_LINE: WidgetId.NUMBER_LINE,
    Representation.AREA_MODEL: WidgetId.FRACTION_BARS,
    Representation.WORD_PROBLEM: WidgetId.WORD_PROBLEM,
    Representation.EXPRESSION: WidgetId.EXPRESSION,
    Representation.INEQUALITY: WidgetId.INEQUALITY,
    Representation.COORDINATE_PLANE: WidgetId.COORDINATE_PLANE,
    Representation.NUMBER_SETS: WidgetId.CLASSIFY_SETS,
}


def widget_for_representation(representation: Representation) -> WidgetId:
    """The live widget that renders a representation — the single source of truth (HR.A1/A5).

    The wire carries this on each ``ProblemView`` so the frontend ``selectWidget(problemView)``
    reads ``widget_id`` directly instead of branching on the KC (HR.A5 — a new widget plugs in for
    free). Raises ``KeyError`` for an unmapped representation (every representation maps today)."""
    return _WIDGET_FOR_REPRESENTATION[representation]


@dataclass(frozen=True)
class ErrorRoute:
    """Where an error category sends the learner — the table HR.A3's signal routing reads.

    A wrong answer of ``error_category`` routes the learner into ``representation`` (a different
    surface than the symbolic default) with a plain-language ``label`` for why. ``representation``
    MUST be one the lesson offers (the contract test enforces it), so routing can never target a
    widget the lesson does not render."""

    error_category: ErrorCategory
    representation: Representation
    label: str


@dataclass(frozen=True)
class TransferProbeSpec:
    """The shape of a lesson's S5 transfer probe (HR.A4 reads this to build the items).

    ``has_error_finding`` is True only for lessons with a wrong-answer model strong enough to pose
    a "reject this claim" item (the ADD/SUB across-error families today); others run a
    representation-only probe. ``probe_representations`` are the surfaces the probe draws transfer
    items from."""

    has_error_finding: bool
    probe_representations: tuple[Representation, ...]


@dataclass(frozen=True)
class LessonSpec:
    """The frozen per-KC contract the hyperreactive engine reads instead of branching on the KC.

    Bundles the DOMAIN-level pieces of a lesson: its representations (+ the widgets that render
    them), where each error category routes, the misconceptions it can exhibit, its procedural
    generator (via :meth:`generate`) + difficulty tiers, its transfer-probe shape, and the CCSS +
    TEKS codes. See the module docstring for why the tutor-rendered banks are NOT here."""

    kc: KnowledgeComponentId
    representations: tuple[Representation, ...]
    error_routes: tuple[ErrorRoute, ...]
    misconceptions: tuple[MisconceptionId, ...]
    transfer_probe: TransferProbeSpec
    difficulty_tiers: tuple[int, ...]
    ccss_code: str | None
    teks_code: str | None

    @property
    def widgets(self) -> tuple[WidgetId, ...]:
        """The live widget for each representation, in representation order."""
        return tuple(_WIDGET_FOR_REPRESENTATION[rep] for rep in self.representations)

    def widget_for(self, representation: Representation) -> WidgetId:
        """The widget that renders ``representation`` (raises ``KeyError`` if unmapped)."""
        return _WIDGET_FOR_REPRESENTATION[representation]

    def generate(
        self,
        seed: int,
        surface_format: Representation | None = None,
        difficulty: int | None = None,
    ) -> Problem:
        """Generate a procedural problem for this lesson — the spec's bound generator (HR.A1).

        Delegates to the domain ``generate_problem`` for this KC, so the engine calls
        ``spec.generate(seed)`` rather than ``generate_problem(kc, seed)`` (reads the spec, not the
        KC id). Deterministic in ``seed``."""
        return generate_problem(self.kc, seed, surface_format, difficulty)


class LessonSpecRegistry:
    """Indexed access to every lesson spec, mirroring ``KnowledgeComponentRegistry`` (HR.A1)."""

    def __init__(self, specs: tuple[LessonSpec, ...]) -> None:
        self._by_kc: dict[KnowledgeComponentId, LessonSpec] = {s.kc: s for s in specs}

    def all(self) -> tuple[LessonSpec, ...]:
        """Every registered lesson spec, in registration order."""
        return tuple(self._by_kc.values())

    def get(self, kc: KnowledgeComponentId | str) -> LessonSpec:
        """The spec for a KC; raises ``KeyError`` for an unregistered KC."""
        key = KnowledgeComponentId(kc) if isinstance(kc, str) else kc
        return self._by_kc[key]


def _codes_for_kc(kc: KnowledgeComponentId) -> tuple[str | None, str | None]:
    """Resolve a KC's representative (CCSS, TEKS) codes from the curriculum catalog.

    Codes live per ``CatalogLesson`` (a KC can recur across lessons), so we take the first lesson
    tagged with this KC that carries any code as the representative — recorded here for the decision
    log (CLAUDE.md §8.4). ``(None, None)`` when no tagged lesson carries a code."""
    for unit in all_units():
        for lesson in unit.lessons:
            if lesson.kc_id == kc.value and (lesson.ccss_code or lesson.teks_code):
                return lesson.ccss_code, lesson.teks_code
    return None, None


def _misconceptions_for_kc(kc: KnowledgeComponentId) -> tuple[MisconceptionId, ...]:
    """The misconception ids the bank maps to this KC (filtered by ``applicable_kcs``)."""
    return tuple(m.id for m in MISCONCEPTION_REGISTRY.all() if kc in m.applicable_kcs)


def _spec(
    kc: KnowledgeComponentId,
    error_routes: tuple[ErrorRoute, ...],
    transfer_probe: TransferProbeSpec,
) -> LessonSpec:
    """Assemble a spec, pulling representations/misconceptions/codes from the single sources."""
    ccss, teks = _codes_for_kc(kc)
    return LessonSpec(
        kc=kc,
        representations=get_kc(kc).representations,
        error_routes=error_routes,
        misconceptions=_misconceptions_for_kc(kc),
        transfer_probe=transfer_probe,
        difficulty_tiers=_DIFFICULTY_TIERS,
        ccss_code=ccss,
        teks_code=teks,
    )


_KC = KnowledgeComponentId
_R = Representation
_E = ErrorCategory

# The 5 fraction lesson specs. Each error route targets a NON-symbolic representation the lesson
# actually offers (the contract test enforces membership), mirroring the engine's current intent:
# magnitude errors → see the size (number line); operation errors → model the parts (fraction bars).
_LESSON_SPECS: tuple[LessonSpec, ...] = (
    _spec(
        _KC.EQUIVALENCE,
        error_routes=(
            ErrorRoute(
                _E.OPERATION, _R.AREA_MODEL, "Model the two fractions with bars to compare."
            ),
            ErrorRoute(_E.FORMAT, _R.AREA_MODEL, "Model the two fractions with bars to compare."),
            ErrorRoute(
                _E.MAGNITUDE, _R.AREA_MODEL, "Shade the bars to see they cover the same area."
            ),
        ),
        transfer_probe=TransferProbeSpec(
            has_error_finding=False, probe_representations=(_R.SYMBOLIC, _R.AREA_MODEL)
        ),
    ),
    _spec(
        _KC.COMMON_DENOMINATOR,
        error_routes=(
            ErrorRoute(
                _E.OPERATION, _R.AREA_MODEL, "Line the bars up to find a shared piece size."
            ),
            ErrorRoute(_E.FORMAT, _R.AREA_MODEL, "Line the bars up to find a shared piece size."),
            ErrorRoute(
                _E.MAGNITUDE, _R.NUMBER_LINE, "Place both fractions to see the common spacing."
            ),
        ),
        transfer_probe=TransferProbeSpec(
            has_error_finding=False, probe_representations=(_R.SYMBOLIC, _R.NUMBER_LINE)
        ),
    ),
    _spec(
        _KC.ADDITION_UNLIKE,
        error_routes=(
            ErrorRoute(
                _E.OPERATION, _R.AREA_MODEL, "Add the shaded bars — same-size pieces first."
            ),
            ErrorRoute(_E.FORMAT, _R.AREA_MODEL, "Add the shaded bars — same-size pieces first."),
            ErrorRoute(_E.MAGNITUDE, _R.NUMBER_LINE, "Hop along the number line to size the sum."),
        ),
        transfer_probe=TransferProbeSpec(
            has_error_finding=True, probe_representations=(_R.SYMBOLIC, _R.NUMBER_LINE)
        ),
    ),
    _spec(
        _KC.SUBTRACTION_UNLIKE,
        error_routes=(
            ErrorRoute(
                _E.OPERATION, _R.AREA_MODEL, "Take away shaded bars — same-size pieces first."
            ),
            ErrorRoute(_E.FORMAT, _R.AREA_MODEL, "Take away shaded bars — same-size pieces first."),
            ErrorRoute(
                _E.MAGNITUDE, _R.NUMBER_LINE, "Step back on the number line to size the difference."
            ),
        ),
        transfer_probe=TransferProbeSpec(
            has_error_finding=True, probe_representations=(_R.SYMBOLIC, _R.NUMBER_LINE)
        ),
    ),
    _spec(
        _KC.NUMBER_LINE_PLACEMENT,
        error_routes=(
            ErrorRoute(
                _E.MAGNITUDE, _R.NUMBER_LINE, "Use the tick marks to place it by size, not digits."
            ),
            # This lesson has no fraction-bars surface, so a FORMAT slip routes to its number line
            # (the global §3.6 table sent FORMAT to S3, a surface this lesson never renders — a
            # latent mismatch this per-lesson route fixes; CLAUDE.md §8.4).
            ErrorRoute(
                _E.FORMAT, _R.NUMBER_LINE, "Check the form, then place it on the number line."
            ),
        ),
        transfer_probe=TransferProbeSpec(
            has_error_finding=False, probe_representations=(_R.NUMBER_LINE, _R.SYMBOLIC)
        ),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 1: Ratios & Rates ───
    # Practice-only today (scheduler lives only on SYMBOLIC), so the probe never fires. Errors
    # route back to SYMBOLIC — WORD_PROBLEM has no surface state and NUMBER_LINE/AREA_MODEL don't
    # model a part-whole comparison, so "re-try on the same surface with a labeled hint" is the
    # honest adaptation until a ratio widget lands (T3). The WORD_PROBLEM representation is the
    # story framing (satisfies the ≥2-rep contract); it becomes the masterable surface then.
    _spec(
        _KC.RATIO_LANGUAGE,
        error_routes=(
            ErrorRoute(
                _E.OPERATION,
                _R.SYMBOLIC,
                "Compare the asked colour to ALL the counters — the whole, not the other colour.",
            ),
            ErrorRoute(
                _E.MAGNITUDE,
                _R.SYMBOLIC,
                "A part of the whole is smaller than the whole — re-check what's on the bottom.",
            ),
        ),
        transfer_probe=TransferProbeSpec(
            has_error_finding=False, probe_representations=(_R.SYMBOLIC,)
        ),
    ),
    _spec(
        _KC.UNIT_RATE,
        error_routes=(
            ErrorRoute(
                _E.OPERATION,
                _R.SYMBOLIC,
                "Reread it: which amount is the total, and how many share it?",
            ),
            ErrorRoute(
                _E.MAGNITUDE,
                _R.SYMBOLIC,
                "One share should be smaller than the whole — check the size.",
            ),
        ),
        transfer_probe=TransferProbeSpec(
            has_error_finding=False, probe_representations=(_R.SYMBOLIC,)
        ),
    ),
    _spec(
        _KC.EQUIVALENT_RATIOS,
        error_routes=(
            ErrorRoute(
                _E.OPERATION,
                _R.SYMBOLIC,
                "Multiply BOTH terms by the same number — adding the same amount won't stay equal.",
            ),
            ErrorRoute(
                _E.MAGNITUDE,
                _R.SYMBOLIC,
                "Check the scale factor: how many times bigger did the second term get?",
            ),
        ),
        transfer_probe=TransferProbeSpec(
            has_error_finding=False, probe_representations=(_R.SYMBOLIC,)
        ),
    ),
    _spec(
        _KC.PERCENT,
        error_routes=(
            ErrorRoute(
                _E.OPERATION,
                _R.SYMBOLIC,
                "Find the percent OF the whole — the percent number alone isn't the answer.",
            ),
            ErrorRoute(
                _E.MAGNITUDE,
                _R.SYMBOLIC,
                "A part of the whole is smaller than the whole — re-check the size.",
            ),
        ),
        transfer_probe=TransferProbeSpec(
            has_error_finding=False, probe_representations=(_R.SYMBOLIC,)
        ),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 2: Fractions & Decimals (T2) ───
    # Practice-only today (scheduler lives only on SYMBOLIC), so the probe never fires. Errors
    # route back to SYMBOLIC (the AREA_MODEL multiply widget isn't live yet), so "re-try on the
    # same surface with a labeled hint" is the honest adaptation until that widget lands (T3).
    _spec(
        _KC.MULTIPLY_FRACTIONS,
        error_routes=(
            ErrorRoute(
                _E.OPERATION,
                _R.SYMBOLIC,
                "Multiply the tops and the bottoms — don't add. A common denominator isn't needed.",
            ),
            ErrorRoute(
                _E.MAGNITUDE,
                _R.SYMBOLIC,
                "A part of a part is smaller than either fraction — re-check the size.",
            ),
        ),
        transfer_probe=TransferProbeSpec(
            has_error_finding=False, probe_representations=(_R.SYMBOLIC,)
        ),
    ),
    # Unit 2 (T2): practice-only today (scheduler lives only on SYMBOLIC), so the probe never fires.
    # Errors route back to SYMBOLIC (the AREA_MODEL division widget isn't live yet), so "re-try on
    # the same surface with a labeled hint" is the honest adaptation until that widget lands (T3).
    _spec(
        _KC.DIVIDE_FRACTIONS,
        error_routes=(
            ErrorRoute(
                _E.OPERATION,
                _R.SYMBOLIC,
                "Flip the second fraction and multiply — don't multiply straight across.",
            ),
            ErrorRoute(
                _E.MAGNITUDE,
                _R.SYMBOLIC,
                "Dividing by less than one whole makes the answer bigger — re-check the size.",
            ),
        ),
        transfer_probe=TransferProbeSpec(
            has_error_finding=False, probe_representations=(_R.SYMBOLIC,)
        ),
    ),
    # Unit 1: practice-only today (scheduler lives only on SYMBOLIC), so the probe never fires.
    # Errors route back to SYMBOLIC — there is no richer surface for a conversion yet (WORD_PROBLEM
    # has no surface state, and NUMBER_LINE/AREA_MODEL don't model a unit conversion), so "re-try on
    # the same surface with a labeled hint" is the honest adaptation until a widget lands (T3). The
    # WORD_PROBLEM representation is the conversion-story framing (satisfies the ≥2-rep contract).
    _spec(
        _KC.UNIT_CONVERSION,
        error_routes=(
            ErrorRoute(
                _E.OPERATION,
                _R.SYMBOLIC,
                "Convert to the smaller unit by MULTIPLYING by the factor — dividing flips it.",
            ),
            ErrorRoute(
                _E.MAGNITUDE,
                _R.SYMBOLIC,
                "Smaller units means more of them — your answer should be bigger, not smaller.",
            ),
        ),
        transfer_probe=TransferProbeSpec(
            has_error_finding=False, probe_representations=(_R.SYMBOLIC,)
        ),
    ),
    # GCF & LCM (6.NS.4 / TEKS 6.7A). Practice-only today (scheduler lives only on SYMBOLIC), so
    # the probe never fires. Errors route back to SYMBOLIC (the NUMBER_LINE factor/multiple widget
    # isn't live yet), so "re-try on the same surface with a labeled hint" is the honest adaptation
    # until that widget lands (T3). The OPERATION route names the GCF↔LCM confusion directly.
    _spec(
        _KC.GCF_LCM,
        error_routes=(
            ErrorRoute(
                _E.OPERATION,
                _R.SYMBOLIC,
                "Factors divide INTO both; multiples are what both divide into — which is asked?",
            ),
            ErrorRoute(
                _E.MAGNITUDE,
                _R.SYMBOLIC,
                "A common factor is no bigger than either number; a common multiple is no smaller.",
            ),
        ),
        transfer_probe=TransferProbeSpec(
            has_error_finding=False, probe_representations=(_R.SYMBOLIC,)
        ),
    ),
    # Multi-digit division (6.NS.2). Practice-only today (scheduler lives only on SYMBOLIC), so the
    # probe never fires. Errors route back to SYMBOLIC (the AREA_MODEL equal-groups widget isn't
    # live yet), so "re-try on the same surface with a labeled hint" is the honest adaptation until
    # that widget lands (T3). The MAGNITUDE route names the place-value slip directly.
    _spec(
        _KC.MULTI_DIGIT_DIVISION,
        error_routes=(
            ErrorRoute(
                _E.OPERATION,
                _R.SYMBOLIC,
                "Divide the whole number by the divisor — how many times does it fit, exactly?",
            ),
            ErrorRoute(
                _E.MAGNITUDE,
                _R.SYMBOLIC,
                "Check the place value of each quotient digit — a stray zero is off by ten times.",
            ),
        ),
        transfer_probe=TransferProbeSpec(
            has_error_finding=False, probe_representations=(_R.SYMBOLIC,)
        ),
    ),
    # Decimal operations (6.NS.3 / TEKS 6.3E). Practice-only today (scheduler lives only on
    # SYMBOLIC), so the probe never fires. The modeled error is point-misplacement — the value off
    # by a power of ten — a MAGNITUDE slip; it routes back to SYMBOLIC (the AREA_MODEL decimal-grid
    # widget isn't live yet), so "re-try on the same surface with a labeled hint" is the honest
    # adaptation until that widget lands (T3). AREA_MODEL is the masterable second rep then.
    _spec(
        _KC.DECIMAL_OPERATIONS,
        error_routes=(
            ErrorRoute(
                _E.MAGNITUDE,
                _R.SYMBOLIC,
                "Count the places in BOTH factors and add them — that's where the point goes.",
            ),
            ErrorRoute(
                _E.OPERATION,
                _R.SYMBOLIC,
                "Multiply the digits as whole numbers first, then place the decimal point.",
            ),
        ),
        transfer_probe=TransferProbeSpec(
            has_error_finding=False, probe_representations=(_R.SYMBOLIC,)
        ),
    ),
    # Absolute value (6.NS.7c/d). Practice-only today (scheduler lives only on SYMBOLIC), so the
    # probe never fires. Errors route back to SYMBOLIC (the NUMBER_LINE distance widget isn't live
    # yet), so "re-try on the same surface with a labeled hint" is the honest adaptation until that
    # widget lands (T3). The MAGNITUDE route names the "distance is never negative" idea directly.
    _spec(
        _KC.ABSOLUTE_VALUE,
        error_routes=(
            ErrorRoute(
                _E.OPERATION,
                _R.SYMBOLIC,
                "Absolute value asks HOW FAR from zero — count the distance, ignore the side.",
            ),
            ErrorRoute(
                _E.MAGNITUDE,
                _R.SYMBOLIC,
                "A distance is never negative — drop the sign and report how far from zero it is.",
            ),
        ),
        transfer_probe=TransferProbeSpec(
            has_error_finding=False, probe_representations=(_R.SYMBOLIC,)
        ),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit-INT: Integer Arithmetic (TEKS 6.3C/D) ───
    # Practice-only today (scheduler lives only on SYMBOLIC), so the probe never fires. Errors
    # route back to SYMBOLIC — the NUMBER_LINE rep is advertised (its widget exists) but isn't
    # live yet, so "re-try on the same surface with a labeled hint" is the honest adaptation until
    # NUMBER_LINE is promoted live. The OPERATION route names the sign-handling error directly.
    _spec(
        _KC.INTEGER_ADD_SUBTRACT,
        error_routes=(
            ErrorRoute(
                _E.OPERATION,
                _R.SYMBOLIC,
                "Combine WITH the signs — opposite signs partly cancel; don't add the sizes.",
            ),
            ErrorRoute(
                _E.MAGNITUDE,
                _R.SYMBOLIC,
                "Opposite signs make the result smaller than either size — re-check the amount.",
            ),
        ),
        transfer_probe=TransferProbeSpec(
            has_error_finding=False, probe_representations=(_R.SYMBOLIC,)
        ),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 3: Rational Numbers ───
    # Practice-only today (scheduler lives only on SYMBOLIC), so the probe never fires. Errors
    # route back to SYMBOLIC — the NUMBER_LINE rep is advertised (and its widget exists) but isn't
    # live yet, so "re-try on the same surface with a labeled hint" is the honest adaptation until
    # NUMBER_LINE is promoted live (then it becomes the masterable second surface). The OPERATION
    # route names the sign error directly.
    _spec(
        _KC.SIGNED_NUMBERS,
        error_routes=(
            ErrorRoute(
                _E.OPERATION,
                _R.SYMBOLIC,
                "The opposite flips the sign across zero — don't write the same number back.",
            ),
            ErrorRoute(
                _E.MAGNITUDE,
                _R.SYMBOLIC,
                "The opposite is the same distance from zero, just on the other side — re-check.",
            ),
        ),
        transfer_probe=TransferProbeSpec(
            has_error_finding=False, probe_representations=(_R.SYMBOLIC,)
        ),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 4: Expressions ───
    # Write expressions (6.EE.2a / 6.EE.B.6) — the FIRST expression-answer lesson. Practice-only
    # (scheduler lives only on EXPRESSION), so the probe never fires. Errors route back to
    # EXPRESSION — the live answer surface (WORD_PROBLEM is just the phrase framing, no surface
    # state), so "re-try on the same surface with a labeled hint" is the honest adaptation. The
    # OPERATION route names the reversed-operands / order confusion directly. Probe over EXPRESSION
    # (the only live rep), not SYMBOLIC, which this KC does not offer.
    _spec(
        _KC.WRITE_EXPRESSIONS,
        error_routes=(
            ErrorRoute(
                _E.OPERATION,
                _R.EXPRESSION,
                "Match the words to the operation AND order — 'less than' flips which is first.",
            ),
        ),
        transfer_probe=TransferProbeSpec(
            has_error_finding=False, probe_representations=(_R.EXPRESSION,)
        ),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 4: Expressions ───
    # Evaluate expressions (6.EE.2c) — a MASTERABLE lesson: SYMBOLIC + AREA_MODEL are BOTH live, so
    # errors route to the OTHER live surface (AREA_MODEL — the array/area picture makes order of
    # operations concrete: count the a×x rows, THEN add the b extras), and the probe draws from both
    # reps. The OPERATION route names the precedence (multiply-before-add) slip directly. AREA_MODEL
    # has a real surface state (FRACTION_BARS_PRIMARY), so the route is honest.
    _spec(
        _KC.EVALUATE_EXPRESSIONS,
        error_routes=(
            ErrorRoute(
                _E.OPERATION,
                _R.AREA_MODEL,
                "Count the rows of squares first (that's the multiply), then add the extras.",
            ),
            ErrorRoute(
                _E.MAGNITUDE,
                _R.AREA_MODEL,
                "Lay out the squares to see how big the total should be before you total it.",
            ),
        ),
        transfer_probe=TransferProbeSpec(
            has_error_finding=False, probe_representations=(_R.SYMBOLIC, _R.AREA_MODEL)
        ),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 4: Expressions ───
    # Exponents (6.EE.1) — a MASTERABLE lesson: SYMBOLIC + AREA_MODEL are BOTH live, so errors
    # route to the OTHER live surface (AREA_MODEL — the square's area / cube's volume picture makes
    # a power concrete: a side-base square is base x base, not base x exponent), and the probe
    # draws from both reps. The OPERATION route names the multiply-base-by-exponent slip directly.
    # AREA_MODEL has a real surface state, so the route is honest.
    _spec(
        _KC.EXPONENTS,
        error_routes=(
            ErrorRoute(
                _E.OPERATION,
                _R.AREA_MODEL,
                "Build the square (or cube) — its side repeats, so multiply the base by itself, "
                "not by the little number.",
            ),
            ErrorRoute(
                _E.MAGNITUDE,
                _R.AREA_MODEL,
                "Picture how many unit squares fill the shape — a power grows faster than you "
                "might expect.",
            ),
        ),
        transfer_probe=TransferProbeSpec(
            has_error_finding=False, probe_representations=(_R.SYMBOLIC, _R.AREA_MODEL)
        ),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 5: Equations & Inequalities ───
    # Solve one-step equations (6.EE.7) — MASTERABLE-LIVE: BOTH reps (SYMBOLIC + WORD_PROBLEM) are
    # live, so the probe DOES fire here (unlike the practice-only Grade-6 KCs). Errors route to
    # SYMBOLIC — the equation surface where the inverse operation is visible; WORD_PROBLEM is a
    # framing with no surface state, so a story-posed error still remediates on the symbolic
    # equation. The OPERATION route names the wrong-inverse error directly. The probe draws from
    # both live reps (transfer across the equation and its story form).
    _spec(
        _KC.ONE_STEP_EQUATIONS,
        error_routes=(
            ErrorRoute(
                _E.OPERATION,
                _R.SYMBOLIC,
                "Undo the equation with the INVERSE — subtract to undo adding, divide to undo "
                "multiplying.",
            ),
            ErrorRoute(
                _E.MAGNITUDE,
                _R.SYMBOLIC,
                "Check the size of x against the equation — put your answer back in and see.",
            ),
        ),
        transfer_probe=TransferProbeSpec(
            has_error_finding=False, probe_representations=(_R.SYMBOLIC, _R.WORD_PROBLEM)
        ),
    ),
    # Equivalent expressions (6.EE.3 / 6.EE.4) — the SECOND expression-answer lesson, reusing the
    # contract. Practice-only (scheduler lives only on EXPRESSION; the only widget that accepts a
    # typed algebra answer is the ExpressionInput — WORD_PROBLEM is the ontology framing, no surface
    # state), so the probe never fires. Errors route back to EXPRESSION — the live answer surface —
    # so "re-try on the same surface with a labeled hint" is the honest adaptation. The OPERATION
    # route names the distributive error directly. Probe over EXPRESSION (the only live rep).
    _spec(
        _KC.EQUIVALENT_EXPRESSIONS,
        error_routes=(
            ErrorRoute(
                _E.OPERATION,
                _R.EXPRESSION,
                "Distribute to EVERY term inside the parentheses — the factor reaches them all.",
            ),
        ),
        transfer_probe=TransferProbeSpec(
            has_error_finding=False, probe_representations=(_R.EXPRESSION,)
        ),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 5: Inequalities ───
    # Write inequalities (6.EE.8) — the first inequality-answer lesson. Practice-only (scheduler
    # lives only on INEQUALITY; the only widget that accepts a typed relational is the inequality
    # input — WORD_PROBLEM is the constraint framing, no surface state), so the probe never fires.
    # Errors route back to INEQUALITY — the live answer surface — so "re-try on the same surface
    # with a labeled hint" is the honest adaptation. The OPERATION route names the flipped-direction
    # confusion directly. Probe over INEQUALITY (the only live rep).
    _spec(
        _KC.INEQUALITIES,
        error_routes=(
            ErrorRoute(
                _E.OPERATION,
                _R.INEQUALITY,
                "Check which way the inequality points — 'at least' allows that number and bigger.",
            ),
        ),
        transfer_probe=TransferProbeSpec(
            has_error_finding=False, probe_representations=(_R.INEQUALITY,)
        ),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 3: The coordinate plane ───
    # Coordinate plane (6.NS.8 / TEKS 6.11A) — the FIRST point-set-answer lesson. Practice-only
    # (scheduler lives only on COORDINATE_PLANE — the coordinate-plane widget is the only surface
    # that accepts a plotted point set; WORD_PROBLEM is the phrase framing with no surface state),
    # so the probe never fires. Errors route back to COORDINATE_PLANE — the live answer surface —
    # "re-try on the same surface with a labeled hint" is the honest adaptation. The OPERATION route
    # names the coordinate-swap / axis-order confusion directly. Probe over COORDINATE_PLANE (the
    # only live rep).
    _spec(
        _KC.COORDINATE_PLANE,
        error_routes=(
            ErrorRoute(
                _E.OPERATION,
                _R.COORDINATE_PLANE,
                "Read the FIRST number as across (x), the SECOND as up/down (y) — order matters.",
            ),
        ),
        transfer_probe=TransferProbeSpec(
            has_error_finding=False, probe_representations=(_R.COORDINATE_PLANE,)
        ),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 3: classify number sets (TEKS 6.2A) ───
    # Classify a value into its number sets — the FIRST set-answer lesson. Practice-only (scheduler
    # lives only on NUMBER_SETS; the only widget that accepts a set answer is the ClassifySets
    # widget — WORD_PROBLEM is the ontology framing with no surface state), so the probe never
    # fires. Errors route back to NUMBER_SETS — the live answer surface — so "re-try on the same
    # surface with a labeled hint" is the honest adaptation. The OPERATION route names the
    # integer-not-rational concept gap directly. Probe over NUMBER_SETS (the only live rep).
    _spec(
        _KC.CLASSIFY_NUMBER_SETS,
        error_routes=(
            ErrorRoute(
                _E.OPERATION,
                _R.NUMBER_SETS,
                "Remember the sets nest — every integer (and every whole number) is also rational.",
            ),
        ),
        transfer_probe=TransferProbeSpec(
            has_error_finding=False, probe_representations=(_R.NUMBER_SETS,)
        ),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 4: parts of an expression (6.EE.2b) ───
    # Name the coefficient, the constant, or the term count — a single number in the NUMERIC editor.
    # Practice-only today (scheduler lives only on SYMBOLIC, the only answer surface; there is no
    # second concrete widget for naming a part), so the probe never fires. The one error route is
    # SYMBOLIC — the live answer surface — so "re-try on the same surface with a labeled hint" is
    # the honest adaptation. The OPERATION route names the coefficient↔constant confusion directly.
    _spec(
        _KC.EXPRESSION_PARTS,
        error_routes=(
            ErrorRoute(
                _E.OPERATION,
                _R.SYMBOLIC,
                "The coefficient multiplies the variable; the constant stands alone — name the "
                "part that was asked.",
            ),
        ),
        transfer_probe=TransferProbeSpec(
            has_error_finding=False, probe_representations=(_R.SYMBOLIC,)
        ),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit-INT: Integer multiply & divide (TEKS 6.3C/D) ──
    # Practice-only today (scheduler lives only on SYMBOLIC), so the probe never fires. Errors route
    # back to SYMBOLIC — NUMBER_LINE is advertised (its widget exists) but isn't live yet, so
    # "re-try on the same surface with a labeled hint" is the honest adaptation until NUMBER_LINE is
    # promoted live. The OPERATION route names the sign-rule error directly; the MAGNITUDE route
    # covers a size slip. Probe over SYMBOLIC (the only live rep).
    _spec(
        _KC.INTEGER_MULTIPLY_DIVIDE,
        error_routes=(
            ErrorRoute(
                _E.OPERATION,
                _R.SYMBOLIC,
                "Like signs give a positive result, unlike signs a negative one — check the sign.",
            ),
            ErrorRoute(
                _E.MAGNITUDE,
                _R.SYMBOLIC,
                "Find the size by multiplying or dividing the numbers without their signs first.",
            ),
        ),
        transfer_probe=TransferProbeSpec(
            has_error_finding=False, probe_representations=(_R.SYMBOLIC,)
        ),
    ),
    # ─── Grade-6 content build (2026-05-30) — Unit 6: Geometry (TEKS 6.8A) ───
    # Triangle properties — find a missing angle (angle sum = 180°) or an area (½·b·h), a single
    # number in the NUMERIC editor. Practice-only today (scheduler lives only on SYMBOLIC):
    # AREA_MODEL is advertised (the triangle FIGURE is the geometric/area picture) but isn't a live
    # answer surface yet, so the probe never fires and errors route back to SYMBOLIC — "re-try on
    # the same surface with a labeled hint" is the honest adaptation until a triangle-figure input
    # widget lands and AREA_MODEL is promoted (then it becomes the masterable second surface). The
    # OPERATION route names the formula error (180 not 90 / the missing ½) directly. Probe over
    # SYMBOLIC (the only live rep), NOT WORD_PROBLEM.
    _spec(
        _KC.TRIANGLE_PROPERTIES,
        error_routes=(
            ErrorRoute(
                _E.OPERATION,
                _R.SYMBOLIC,
                "Angles in a triangle add to 180°, and a triangle's area is HALF base × height.",
            ),
            ErrorRoute(
                _E.MAGNITUDE,
                _R.SYMBOLIC,
                "Check the size: a third angle can't exceed 180°, and the area is half the "
                "rectangle.",
            ),
        ),
        transfer_probe=TransferProbeSpec(
            has_error_finding=False, probe_representations=(_R.SYMBOLIC,)
        ),
    ),
)

LESSON_SPEC_REGISTRY = LessonSpecRegistry(_LESSON_SPECS)


def get_lesson_spec(kc: KnowledgeComponentId | str) -> LessonSpec:
    """The lesson spec for a KC — the module-level shortcut (mirrors ``get_kc``)."""
    return LESSON_SPEC_REGISTRY.get(kc)


__all__ = [
    "LESSON_SPEC_REGISTRY",
    "ErrorRoute",
    "LessonSpec",
    "LessonSpecRegistry",
    "TransferProbeSpec",
    "WidgetId",
    "get_lesson_spec",
    "widget_for_representation",
]
