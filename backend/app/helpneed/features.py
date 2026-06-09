"""HelpNeed feature extraction (Slice 3.3).

Turns the per-attempt ``EdmCupTurn`` stream (Slice 3.2) into the real-time feature
vectors the HelpNeed predictor trains on (PROJECT.md §3.7, ARCHITECTURE.md §8). The
§3.7 feature list — "response latency on current and recent problems, error pattern,
hint requests in the last N problems, time since last correct, BKT probabilities,
recent state transitions" — splits into two groups:

  - **Data-derivable now (this module):** recent-latency / attempts / hint-rate /
    error-rate / give-up-rate over a sliding window of the learner's RECENT turns,
    turns-since-last-correct, the running unproductive rate, session position, and
    the current KC (one-hot).
  - **Tutor-only (not in the training data):** BKT mastery probabilities and recent
    surface-state transitions are signals OUR tutor produces, not the EDM Cup
    clickstream. They are added at live-inference integration (Slice 4.4) where the
    tutor supplies them, and absorbed by the §7.2 calibration step. The v1 model
    (Slice 3.5) trains on the data-derivable set above; this is the documented
    cross-tutor gap, not an omission.

**Leakage-safety (the load-bearing invariant).** The label (Slice 3.4) is derived
from a turn's OWN outcome. So every feature here is computed from the learner's
turns STRICTLY BEFORE the current one (``session[:i]``) — never the current turn's
attempts/hints/correctness. A predictor that saw the current outcome would just
memorize the label; one that sees only the trajectory-so-far is the genuine
proactive signal (fire help based on how the session is going). ``test_features``
pins this with a leakage guard.

No LLM, no SymPy, no DB, no numpy here (CLAUDE.md §7, §8.1/§8.2) — pure stdlib +
dataclasses, deterministic (same turns ⇒ same vectors, PROJECT.md §4.1). The
predictor module (Slice 3.5) converts ``to_vector()`` tuples into the numeric matrix.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.domain.knowledge_components import KnowledgeComponentId
from app.helpneed.labels import is_unproductive
from app.helpneed.parse_edmcup import EdmCupTurn

# The recent-history window: "hint requests in the last N problems", etc. (§3.7).
# Five is a small, sensible default; tunable in week 4-5 (0.D.5 style) — named so a
# change is a deliberate, reviewed edit.
RECENT_WINDOW = 5

# A fixed KC ordering for the one-hot encoding, so the feature columns are stable
# across runs (SHAP/feature-importance read by column index). Enum definition order.
KC_ORDER: tuple[KnowledgeComponentId, ...] = tuple(KnowledgeComponentId)

# The numeric (non-KC) feature columns, in to_vector() order. FEATURE_NAMES appends
# the one-hot KC columns; together they label every column for SHAP.
_NUMERIC_FEATURE_NAMES: tuple[str, ...] = (
    "recent_latency_ms_mean",
    "recent_attempts_mean",
    "recent_hint_rate",
    "recent_error_rate",
    "recent_request_answer_rate",
    "recent_no_hint_error_rate",
    "turns_since_last_correct",
    "prior_unproductive_rate",
    "session_position",
)
FEATURE_NAMES: tuple[str, ...] = _NUMERIC_FEATURE_NAMES + tuple(f"kc_{kc.value}" for kc in KC_ORDER)


@dataclass(frozen=True)
class HelpNeedFeatures:
    """One turn's real-time feature vector (the §3.7 data-derivable subset).

    Frozen — a computed feature row is a fact about the trajectory, not mutable
    state. ``to_vector`` flattens it (KC expanded to a one-hot) into the numeric
    tuple the model consumes, in ``FEATURE_NAMES`` order.

    All history features are computed over the learner's turns BEFORE this one (see
    the module docstring's leakage note). ``turns_since_last_correct`` is a
    turn-count proxy for the §3.7 "time since last correct" (the parsed turns carry
    no reliable cross-turn wall-clock, so we count turns).
    """

    recent_latency_ms_mean: float
    recent_attempts_mean: float
    recent_hint_rate: float
    recent_error_rate: float
    recent_request_answer_rate: float
    recent_no_hint_error_rate: float
    turns_since_last_correct: float
    prior_unproductive_rate: float
    session_position: float
    kc: KnowledgeComponentId

    def to_vector(self) -> tuple[float, ...]:
        """Flatten to the numeric model input (KC one-hot appended), in column order."""
        numeric = (
            self.recent_latency_ms_mean,
            self.recent_attempts_mean,
            self.recent_hint_rate,
            self.recent_error_rate,
            self.recent_request_answer_rate,
            self.recent_no_hint_error_rate,
            self.turns_since_last_correct,
            self.prior_unproductive_rate,
            self.session_position,
        )
        one_hot = tuple(1.0 if self.kc is kc else 0.0 for kc in KC_ORDER)
        return numeric + one_hot


@dataclass(frozen=True)
class TrainingExample:
    """A (features, label) row plus join keys for traceability into the decision log.

    ``label`` is the §3.4 unproductive verdict for the turn the features predict.
    ``assignment_log_id`` / ``problem_id`` let a reviewer trace a row back to the
    raw trace ("why did the model see this example?").
    """

    features: HelpNeedFeatures
    label: bool
    assignment_log_id: str
    problem_id: str


def _mean(values: Sequence[float]) -> float:
    """Arithmetic mean, or 0.0 for an empty sequence (a neutral 'no history' value)."""
    return sum(values) / len(values) if values else 0.0


def _features_at(session: Sequence[EdmCupTurn], index: int) -> HelpNeedFeatures:
    """Build the feature row for ``session[index]`` from the turns before it.

    ``prior`` is everything earlier in the session; ``window`` is the most recent
    ``RECENT_WINDOW`` of those. Empty history (index 0) yields all-neutral features.
    """
    current = session[index]
    prior = session[:index]
    window = prior[-RECENT_WINDOW:]

    latencies = [
        float(t.latency_ms_to_first_response)
        for t in window
        if t.latency_ms_to_first_response is not None
    ]

    # turns since the last correct prior turn (1 if the immediately-preceding turn was
    # correct); equal to the session position when no prior turn was correct yet.
    turns_since_last_correct = float(index)
    for offset, turn in enumerate(reversed(prior), start=1):
        if turn.correct:
            turns_since_last_correct = float(offset)
            break

    return HelpNeedFeatures(
        recent_latency_ms_mean=_mean(latencies),
        recent_attempts_mean=_mean([float(t.attempt_count) for t in window]),
        # BINARY hinted-rate (did the turn use ANY hint), NOT a hint COUNT. The live path can only
        # observe a boolean `hinted` per turn (live_features.py treats `not hinted` as the analogue
        # of `hint_count == 0`), so a count-scaled training feature (mean of 0..9) was a train/serve
        # skew: the model learned thresholds the live 0..1 signal could never reach. Aligned to the
        # boolean both sides can compute (the model is re-fit on this corrected feature).
        recent_hint_rate=_mean([1.0 if t.hint_count > 0 else 0.0 for t in window]),
        recent_error_rate=_mean([0.0 if t.first_attempt_correct else 1.0 for t in window]),
        recent_request_answer_rate=_mean([1.0 if t.requested_answer else 0.0 for t in window]),
        # "Quiet mis-reasoning": a first-attempt error WITHOUT seeking a hint — the confident
        # wrong answer that the weak RP/expression KCs produce (the help-seeking features stay
        # silent there). Computable identically live from (correct, hinted) — see live_features.py.
        recent_no_hint_error_rate=_mean(
            [1.0 if (not t.first_attempt_correct and t.hint_count == 0) else 0.0 for t in window]
        ),
        turns_since_last_correct=turns_since_last_correct,
        prior_unproductive_rate=_mean([1.0 if is_unproductive(t) else 0.0 for t in prior]),
        session_position=float(index),
        kc=current.kc,
    )


def session_examples(session: Sequence[EdmCupTurn]) -> list[TrainingExample]:
    """Build one ``TrainingExample`` per turn in one learner session, in order."""
    return [
        TrainingExample(
            features=_features_at(session, i),
            label=is_unproductive(turn),
            assignment_log_id=turn.assignment_log_id,
            problem_id=turn.problem_id,
        )
        for i, turn in enumerate(session)
    ]


def group_sessions(turns: Iterable[EdmCupTurn]) -> dict[str, list[EdmCupTurn]]:
    """Group a turn stream into per-session lists, preserving arrival order.

    The session key is ``assignment_log_id`` (the ASSISTments per-learner-assignment
    proxy, parse_edmcup docstring). Insertion order is preserved (dict ≥3.7) so the
    output is deterministic (PROJECT.md §4.1).
    """
    sessions: dict[str, list[EdmCupTurn]] = {}
    for turn in turns:
        sessions.setdefault(turn.assignment_log_id, []).append(turn)
    return sessions


def build_examples(turns: Iterable[EdmCupTurn]) -> list[TrainingExample]:
    """Build training examples for every turn, grouped into sessions first.

    Windowing is per-session: a turn's history is its OWN session's earlier turns,
    never another learner's — so the first turn of each session has neutral history.
    """
    examples: list[TrainingExample] = []
    for session in group_sessions(turns).values():
        examples.extend(session_examples(session))
    return examples


__all__ = [
    "FEATURE_NAMES",
    "KC_ORDER",
    "RECENT_WINDOW",
    "HelpNeedFeatures",
    "TrainingExample",
    "build_examples",
    "group_sessions",
    "session_examples",
]
