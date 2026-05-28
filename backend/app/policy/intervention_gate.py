"""The sustained-signal proactive-intervention gate (Slice 4.5.1).

Turns the per-turn HelpNeed probability stream (Slice 4.4, ``helpneed/``) into a
fire / don't-fire verdict for a proactive intervention. PROJECT.md §3.7 (sustained gate,
added 2026-05-28): the intervention fires only after **K consecutive turns at
P ≥ threshold**, resetting on any dip — never on a single high reading.

Why a sustained window and not a single threshold-crossing: the §7.5 persona calibration
found the model's dominant feature (``turns_since_last_correct``, SHAP rank 1) makes
single per-turn readings noisy — a correct answer right after an error streak can still
read high — so acting on one reading would interrupt a learner who just recovered. And
Razzaq & Heffernan (2010) show proactive over-firing can underperform reactive help. K is
the genuinely new parameter (threshold stays the locked-but-tunable 0.5, §3.7 initial
tunings); **both are swept by the Slice 5.4 A/B, not hand-tuned** — the honest-reporting
posture §3.7's Path-2 commitment requires. The provisional defaults here exist only so the
mechanism is runnable before the sweep.

Pure decision logic (CLAUDE.md §7, §8.1/§8.2): no SymPy, no LLM, no DB, no model — it
consumes probabilities the predictor already produced and never calls back into it.
Deterministic: the same probability history yields the same verdict (PROJECT.md §4.1).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

# Provisional defaults (PROJECT.md §3.7): three sustained turns, the locked 0.5 threshold.
# Swept by the Slice 5.4 A/B — do not treat as validated.
DEFAULT_K = 3
DEFAULT_THRESHOLD = 0.5


@dataclass(frozen=True)
class SustainedHelpNeedGate:
    """Fires when the HelpNeed signal has been high for K consecutive turns.

    ``k`` is the window length (how many recent turns must all clear ``threshold``);
    ``threshold`` is the per-turn P(unproductive) bar (inclusive, ``>=``). Frozen and
    validated at construction so an out-of-range parameter fails loudly rather than
    producing a silently-wrong gate (CLAUDE.md §8.5).
    """

    k: int = DEFAULT_K
    threshold: float = DEFAULT_THRESHOLD

    def __post_init__(self) -> None:
        if self.k < 1:
            raise ValueError(f"k must be >= 1 (a window of at least one turn), got {self.k}")
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError(f"threshold must be a probability in [0, 1], got {self.threshold}")

    def should_intervene(self, recent_probs: Sequence[float]) -> bool:
        """Whether the proactive intervention should fire given the P history so far.

        ``recent_probs`` is every scored turn's P(unproductive) this session, in order.
        Fires iff the most recent ``k`` readings all clear ``threshold`` — so a single
        sub-threshold turn anywhere in the window (e.g. a correct answer mid-recovery)
        blocks the fire, and an older high run that has since dipped does not stand as an
        alarm. Returns ``False`` until at least ``k`` turns have been scored.
        """
        if len(recent_probs) < self.k:
            return False
        window = recent_probs[-self.k :]
        return all(p >= self.threshold for p in window)


__all__ = ["DEFAULT_K", "DEFAULT_THRESHOLD", "SustainedHelpNeedGate"]
