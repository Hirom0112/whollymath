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


_WIDGET_FOR_REPRESENTATION: dict[Representation, WidgetId] = {
    Representation.SYMBOLIC: WidgetId.FRACTION_EDITOR,
    Representation.NUMBER_LINE: WidgetId.NUMBER_LINE,
    Representation.AREA_MODEL: WidgetId.FRACTION_BARS,
    Representation.WORD_PROBLEM: WidgetId.WORD_PROBLEM,
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
