"""Live HelpNeed feature adapter (Slice 4.4 — adapter half).

Builds the model's ``HelpNeedFeatures`` from the LIVE tutor's completed-turn
history, so the predictor trained on the EDM Cup clickstream (Slices 3.3–3.5) can
score an in-progress problem in our own tutor. The training-time builder
(``features._features_at``) reads an ``EdmCupTurn`` stream; this reads the tiny live
projection ``LiveTurn`` instead, and produces the identical feature row under one
documented train/serve proxy mapping (the §7.2 cross-tutor gap, calibrated in 4.3
BEFORE the predictor is allowed to drive any intervention).

The proxy mapping (decision 2026-05-28, team-approved — see RESEARCH.md §7.2):

  - **``recent_attempts_mean`` → constant 1.0.** The live loop is one submit per
    turn (``api/service.py`` advances after a single answer), so there is no
    multi-attempt count to average; the neutral training value for "one try" is 1.0.
  - **``recent_request_answer_rate`` → the live hint-request rate.** The live tutor
    has no "show answer / give up" action, so the closest available help-seeking
    signal is the hint request. This is the ONLY non-faithful feature column; it
    intentionally correlates with ``recent_hint_rate``. Whether that double-counts
    the hint signal is exactly what the §7.2 persona calibration measures.

``prior_unproductive_rate`` is computed FAITHFULLY, NOT through the proxy: reusing
the locked §3.4 label (``is_unproductive``) on the live signals, a turn with
``attempt_count==1``, ``hint_count<2`` and no give-up is unproductive iff it was not
correct. Folding the request-answer proxy into the label too would make a single
hint mark a turn as a give-up — harsher than the §3.4 definition deliberately
blesses (one hint is fine). So the proxy is confined to its own feature column.

**Leakage-safety.** The in-progress "current" problem is NOT in ``history`` (it is
not answered yet), so every feature is computed from strictly-earlier turns by
construction — the same leakage invariant the training builder enforces with
``session[:i]`` (features.py module docstring).

No LLM, no SymPy, no DB, no numpy (CLAUDE.md §7, §8.1/§8.2) — pure stdlib +
dataclasses, deterministic (same history ⇒ same vector, PROJECT.md §4.1).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.knowledge_components import KnowledgeComponentId
from app.helpneed.features import RECENT_WINDOW, HelpNeedFeatures


@dataclass(frozen=True)
class LiveTurn:
    """The live-available projection of one completed tutor turn.

    Deliberately tiny and tutor-agnostic so this module does not depend on the
    ``tutor`` package (the live wiring in ``api``/``tutor`` calls the predictor, so a
    reverse import here would be a cycle). The caller projects its own completed turn
    (e.g. a ``tutor.session.Turn``'s mastery ``Observation``) onto these three live
    signals — correctness, whether a hint was used, and the answer latency.
    """

    correct: bool
    hinted: bool
    latency_ms: int


def _mean(values: Sequence[float]) -> float:
    """Arithmetic mean, or 0.0 for an empty sequence (the neutral 'no history' value).

    Matches ``features._mean`` exactly so the live and training feature rows agree on
    empty-history handling (the cold-start row is all-neutral, not undefined).
    """
    return sum(values) / len(values) if values else 0.0


def live_features(
    history: Sequence[LiveTurn], current_kc: KnowledgeComponentId
) -> HelpNeedFeatures:
    """Feature row for the CURRENT (in-progress) problem given the completed history.

    ``history`` is every turn the learner has already answered this session, in
    order; ``current_kc`` is the KC of the problem now in front of them. Mirrors
    ``features._features_at`` with ``prior = history`` (all of it) and ``window`` its
    most recent ``RECENT_WINDOW`` — see the module docstring for the proxy mapping.
    """
    window = history[-RECENT_WINDOW:]

    # turns since the last correct prior turn (1 if the immediately-preceding turn was
    # correct); equal to the session position when no prior turn was correct yet.
    turns_since_last_correct = float(len(history))
    for offset, turn in enumerate(reversed(history), start=1):
        if turn.correct:
            turns_since_last_correct = float(offset)
            break

    hint_rate = _mean([1.0 if t.hinted else 0.0 for t in window])
    return HelpNeedFeatures(
        recent_latency_ms_mean=_mean([float(t.latency_ms) for t in window]),
        recent_attempts_mean=1.0 if window else 0.0,
        recent_hint_rate=hint_rate,
        recent_error_rate=_mean([0.0 if t.correct else 1.0 for t in window]),
        recent_request_answer_rate=hint_rate,  # proxy: no give-up action live
        # Quiet mis-reasoning: wrong WITHOUT a hint. Faithful to the training feature — live's
        # one-submit turn makes ``correct`` the analogue of ``first_attempt_correct`` and
        # ``not hinted`` the analogue of ``hint_count == 0`` (features.py._features_at).
        recent_no_hint_error_rate=_mean(
            [1.0 if (not t.correct and not t.hinted) else 0.0 for t in window]
        ),
        turns_since_last_correct=turns_since_last_correct,
        prior_unproductive_rate=_mean([0.0 if t.correct else 1.0 for t in history]),
        session_position=float(len(history)),
        kc=current_kc,
    )


__all__ = ["LiveTurn", "live_features"]
