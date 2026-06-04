"""The committed HelpNeed model artifact — canonical home + load path (Slice 4.4.1).

The deployed turn loop needs a *fitted* predictor at boot, but the 1.44 GB EDM Cup
training data is gitignored (too large for git; re-downloadable from source). The
trained XGBoost model, by contrast, serializes to ~270 KB — its size is set by the
tree count/depth (``predictor.py``: 200 trees, depth 4), not by the row count it saw.
So we commit the one blessed artifact into the package and load it at boot (decision
2026-05-28, overriding the earlier ``.gitignore`` "models live in S3" note — see the
commit message and README "HelpNeed model artifact"). S3/model-registry hosting is the
clean upgrade path if the model ever grows or needs independent versioning; at 270 KB
on a 6-week build it would be premature infrastructure (CLAUDE.md §8.6).

Provenance is the one cost of committing a binary derived from gitignored data, and
the project's answer is the decision log: the artifact is reproduced by
``python -m app.helpneed.train_pipeline`` with ``WHOLLYMATH_EDMCUP_ROW_LIMIT=5000000``
and ``WHOLLYMATH_HELPNEED_OUT`` set (RESEARCH.md §7.2 — holdout AUC 0.899 on the
cross-topic skill set; the 0.893/fraction-only figure was the predecessor). The
production artifact is fit on ALL examples from that pass (the 25% holdout exists only
to *measure* quality, not to be discarded in production), and carries the stamped
Tier-2 trustworthy set (per-KC AUC ≥ 0.85) the proactive gate reads at boot.

No LLM, no SymPy, no DB here (CLAUDE.md §8.1/§8.2) — this only locates and loads a
joblib file behind ``HelpNeedPredictor.load``.
"""

from __future__ import annotations

from pathlib import Path

from app.helpneed.predictor import HelpNeedPredictor

# The single canonical location of the committed model. Packaged INSIDE app/helpneed/
# so the load path is independent of the process CWD and the artifact ships with the
# code (the deploy image carries it; no network fetch on the boot path).
ARTIFACT_PATH = Path(__file__).parent / "artifacts" / "helpneed_v1.joblib"


def load_predictor(path: Path = ARTIFACT_PATH) -> HelpNeedPredictor:
    """Load the committed HelpNeed predictor for the live loop (raises if absent).

    Fails loudly (``FileNotFoundError`` via joblib) rather than silently degrading:
    a missing artifact is a deployment error, not a runtime state to paper over
    (CLAUDE.md §8.5). The caller (``create_app``) decides how to surface it.
    """
    return HelpNeedPredictor.load(path)


__all__ = ["ARTIFACT_PATH", "load_predictor"]
