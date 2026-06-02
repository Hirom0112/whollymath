"""EXPERIMENTAL synthetic v2 HelpNeed training path (Slice 0.1, V2_TODO WAVE 0).

Wires the synthetic labeled-trace source (``synthetic_traces.py``) through the UNCHANGED v2 feature
pipeline (``events_features.derive_v2_features``) and into the SAME XGBoost the production predictor
uses (``predictor.py``), producing a fitted v2 predictor and a small report. The output is saved to
a SEPARATE, clearly-named EXPERIMENTAL artifact path — NEVER the committed v1 production artifact
(``artifact.ARTIFACT_PATH``), which the live loop loads and which this slice must not disturb.

**OBSERVE-ONLY / SYNTHETIC / AWAITS REAL-STUDENT VALIDATION (PROJECT.md §9; ARCHITECTURE.md §14
invariant 9; V2_TODO Slice 0.1).** This is NOT a shippable v2 model. It trains on persona-simulated
traces because ``interaction_event`` is empty (no real WhollyMath students yet), so it cannot be
live-validated; it exists to prove the proxy-free v2 derivation trains end-to-end and to give the
writeup a synthetic SHAP/separation story. The five §4.2 personas stamp a ground-truth help-need
label no real clickstream carries (literature-validated: arXiv 2401.16832; DASKT 2025; AdvKT 2026).
When real telemetry lands, this same path retrains on it and the experimental gate is revisited;
until then nothing here feeds a live decision.

Why a separate predict path from v1: the v1 ``HelpNeedPredictor`` width-guard compares a loaded
artifact against the LIVE one-hot ``FEATURE_NAMES`` (the v1 schema). A v2 row is a DIFFERENT width
(``FEATURE_NAMES_V2``), so we fit the predictor with ``feature_names=None`` — the guard then falls
back to the model's own ``n_features_in_``, which equals the v2 width the model was fit on, so a v2
row scores normally. The experimental predictor is therefore self-consistent on v2 vectors and is
NEVER loaded by the live loop (that loads ``artifact.load_predictor`` → v1 only).

No LLM, no SymPy, no DB here (CLAUDE.md §8.1/§8.2) — pure orchestration over already-tested pieces.
Deterministic (PROJECT.md §4.1): fixed personas, fixed sequence, fixed ``random_state``.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.helpneed.events_features import (
    HelpNeedV2Features,
    build_episodes,
    derive_v2_features,
)
from app.helpneed.predictor import HelpNeedPredictor
from app.helpneed.synthetic_traces import generate_persona_trace
from app.personas.registry import PERSONA_REGISTRY
from app.personas.run import ProblemSpec

# The default training block: the live fraction KCs interleaved across the three live
# representations, plus a couple of EXPLAIN probes. Interleaving across formats is exactly what
# surfaces Surface Sam's format-tied collapse and exercises a range of persona behaviors (PROJECT.md
# §3.4 rule 4) — so the synthetic corpus carries both clean and struggling episodes. Deterministic
# seeds. Kept modest (one block, all personas) so the experimental fit is fast and reproducible.
_BLOCK_KCS: tuple[KnowledgeComponentId, ...] = (
    KnowledgeComponentId.ADDITION_UNLIKE,
    KnowledgeComponentId.SUBTRACTION_UNLIKE,
    KnowledgeComponentId.COMMON_DENOMINATOR,
)
_BLOCK_FORMATS: tuple[Representation, ...] = (
    Representation.SYMBOLIC,
    Representation.AREA_MODEL,
    Representation.SYMBOLIC,
)


def _default_sequence() -> list[ProblemSpec]:
    """A concrete, deterministic problem block: each block KC across the interleaved formats.

    The same sequence is run for every persona, so a persona's CONFIGURED knowledge state (not a
    hardcoded outcome) decides how many of its episodes come out unproductive — the contrast the
    model learns. Built once and frozen into ``DEFAULT_SYNTHETIC_SEQUENCE``.
    """
    sequence: list[ProblemSpec] = []
    seed = 1
    for kc in _BLOCK_KCS:
        for fmt in _BLOCK_FORMATS:
            sequence.append(ProblemSpec(kc=kc, seed=seed, surface_format=fmt))
            seed += 1
    return sequence


DEFAULT_SYNTHETIC_SEQUENCE: tuple[ProblemSpec, ...] = tuple(_default_sequence())

# The canonical EXPERIMENTAL artifact location — deliberately NOT ``artifact.ARTIFACT_PATH``. The
# name says exactly what it is so no one mistakes it for the shipped model.
EXPERIMENTAL_ARTIFACT_PATH = (
    Path(__file__).parent / "artifacts" / "helpneed_v2_synthetic_experimental.joblib"
)


@dataclass(frozen=True)
class V2Example:
    """A (v2-feature row, label) pair — the experimental training unit.

    Mirrors the shape ``predictor.examples_to_matrix`` reads (``.features.to_vector()`` + label)
    but carries the v2 ``HelpNeedV2Features`` instead of v1's ``HelpNeedFeatures``. ``persona_id``
    is kept for traceability into the synthetic provenance (which persona produced this example).
    """

    features: HelpNeedV2Features
    label: bool
    persona_id: str


@dataclass(frozen=True)
class SyntheticTrainingReport:
    """The numbers the experimental run reports — provenance for the synthetic writeup.

    Honest about scope: these are SYNTHETIC metrics (persona-simulated traces), not a real-student
    holdout. ``probe_scores`` is (struggling_row_score, clean_row_score) — a sanity check that the
    fitted model separates a hint-dependent history from a clean one, the direction the predictor
    must learn.
    """

    n_examples: int
    positive_rate: float
    probe_scores: tuple[float, float]


def build_synthetic_v2_examples(
    sequence: Sequence[ProblemSpec] = DEFAULT_SYNTHETIC_SEQUENCE,
) -> list[V2Example]:
    """Generate labeled v2 examples across the whole persona roster (the synthetic corpus).

    For each persona: drive the synthetic-trace generator, parse its events through the UNCHANGED v2
    pipeline (``build_episodes`` → ``derive_v2_features``), and pair each per-episode v2 feature row
    with the generator's ground-truth label for that episode. The label and the feature window are
    both functions of the persona's OWN prior episodes (the leakage discipline the pipeline keeps),
    so an example never sees its own outcome. Deterministic.
    """
    examples: list[V2Example] = []
    for persona in PERSONA_REGISTRY.all():
        trace = generate_persona_trace(persona, sequence)
        episodes = build_episodes(trace.events)
        feature_rows = derive_v2_features(episodes)
        # One feature row and one labeled episode per submitted problem, in the same order.
        for features, labeled in zip(feature_rows, trace.episodes, strict=True):
            examples.append(
                V2Example(
                    features=features, label=labeled.unproductive, persona_id=persona.persona_id
                )
            )
    return examples


def _struggling_and_clean_probe(
    examples: Sequence[V2Example],
) -> tuple[HelpNeedV2Features, HelpNeedV2Features]:
    """Pick the most-struggling and most-clean v2 feature rows from the corpus for a sanity probe.

    "Most struggling" = the row with the highest prior-unproductive history; "most clean" = the
    lowest. Reads the rows the personas actually produced (not hand-built vectors), so the probe is
    grounded in the synthetic corpus. Falls back to the first row if the corpus is single-row.
    """
    by_struggle = sorted(examples, key=lambda ex: ex.features.prior_unproductive_rate)
    return by_struggle[-1].features, by_struggle[0].features


def train_synthetic_v2(
    sequence: Sequence[ProblemSpec] = DEFAULT_SYNTHETIC_SEQUENCE,
    *,
    random_state: int = 0,
    out_path: Path | None = None,
) -> tuple[HelpNeedPredictor, SyntheticTrainingReport]:
    """Fit the SAME XGBoost on synthetic v2 examples and (optionally) save the EXPERIMENTAL model.

    Returns the fitted predictor (scoring v2 rows via its own ``n_features_in_`` width-guard — see
    the module docstring) and a synthetic report. When ``out_path`` is given the experimental
    artifact is written there (never to the committed v1 path). When ``out_path is None`` nothing is
    saved — a pure in-memory fit, the default for tests and the latency probe.
    """
    examples = build_synthetic_v2_examples(sequence)
    predictor = HelpNeedPredictor.fit(examples, kind="xgboost", random_state=random_state)
    # ``fit`` stamped the v1 ``FEATURE_NAMES``; clear it so the width-guard falls back to the
    # model's own (v2-width) ``n_features_in_`` and a v2 row scores, not the v1 neutral path.
    predictor.feature_names = None

    struggling, clean = _struggling_and_clean_probe(examples)
    report = SyntheticTrainingReport(
        n_examples=len(examples),
        positive_rate=sum(ex.label for ex in examples) / len(examples) if examples else 0.0,
        probe_scores=(predictor.predict_proba(struggling), predictor.predict_proba(clean)),
    )

    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        predictor.save(out_path)

    return predictor, report


def main() -> None:
    """Fit the experimental synthetic v2 model and write it to the experimental artifact path.

    Run from ``backend/``::

        uv run python -m app.helpneed.train_synthetic

    Honors ``WHOLLYMATH_HELPNEED_V2_OUT`` to override the destination (defaults to the experimental
    path). This is a SYNTHETIC, OBSERVE-ONLY run — it never touches the committed v1 artifact and
    never claims a validated v2 (PROJECT.md §9).
    """
    out_path = Path(os.environ.get("WHOLLYMATH_HELPNEED_V2_OUT", str(EXPERIMENTAL_ARTIFACT_PATH)))
    _, report = train_synthetic_v2(out_path=out_path)
    struggling, clean = report.probe_scores
    print("EXPERIMENTAL synthetic v2 HelpNeed (observe-only; awaits real-student validation)")
    print(f"  examples={report.n_examples}  positive_rate={report.positive_rate:.3f}")
    print(f"  probe: struggling={struggling:.3f}  clean={clean:.3f}")
    print(f"  saved experimental artifact -> {out_path}")


if __name__ == "__main__":
    main()


__all__ = [
    "DEFAULT_SYNTHETIC_SEQUENCE",
    "EXPERIMENTAL_ARTIFACT_PATH",
    "SyntheticTrainingReport",
    "V2Example",
    "build_synthetic_v2_examples",
    "train_synthetic_v2",
]
