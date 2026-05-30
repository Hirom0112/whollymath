"""Self-healing skip for tests that assert the committed HelpNeed artifact's LIVE scoring.

During the KC-expansion → re-fit window (T1_T2_COORDINATION.md §2) the committed
``helpneed_v1.joblib`` is stale-width: ``KnowledgeComponentId`` (and thus the one-hot
``KC_ORDER``) widened ahead of T2's re-fit, so the width-guard makes ``predict_proba``
return its neutral fallback and the artifact can no longer produce a real P(unproductive).
Tests that assert real scoring / a proactive intervention firing therefore can't hold until
the re-fit lands.

This marker checks the actual committed artifact against the live ``FEATURE_NAMES`` and skips
those tests ONLY while the widths disagree — so when T2 commits a re-fit at the new width, the
condition flips to False and the tests run again automatically, with no manual un-skip.
"""

from __future__ import annotations

import pytest
from app.helpneed.artifact import load_predictor

_artifact_scores_live = load_predictor().is_compatible_with_live_features()

stale_artifact = pytest.mark.skipif(
    not _artifact_scores_live,
    reason=(
        "HelpNeed artifact is stale-width during the KC-expansion → re-fit window "
        "(T1_T2_COORDINATION.md §2); the width-guard returns a neutral score, so live-scoring "
        "assertions can't hold. Auto-re-enables when T2's re-fit at the new width lands."
    ),
)
