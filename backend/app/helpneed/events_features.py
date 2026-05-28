"""HelpNeed v2 — offline feature derivation from the behavioral event stream (Slice PL.4).

**What this delivers, and what it deliberately does NOT.** v1 (``features.py`` +
``live_features.py``) trains on the EDM Cup clickstream and, in the LIVE loop, fakes two
feature columns it cannot observe from a single-submit turn (documented at
``live_features.py`` and RESEARCH.md §7.5 finding 3):

  - ``recent_attempts_mean`` → the constant ``1.0`` (no multi-attempt count to average), and
  - ``recent_request_answer_rate`` → the live hint-request rate (no give-up action live).

PL.4 RETIRES those two proxies by deriving the SAME signals FAITHFULLY from the Slice-PL.2
``InteractionEvent`` stream — the raw behavioral capture of HOW a learner works each problem
(every answer edit, number-line drag, hint request, submit, first touch, idle). Attempts
become a real count of ``submit`` events; the give-up signal becomes a real escalation
threshold on ``hint_request`` events; and two NEW columns become possible that v1 could not
express at all (answer revisions, time-to-first-interaction).

**THE HONEST LIMITATION (PROJECT.md §9).** This module is the OFFLINE DERIVATION PIPELINE and
the v2 FEATURE SCHEMA only. It is NOT a trained or validated v2 model, and it does NOT claim
any v2 accuracy. We have NO real-learner event data yet (no real students — a §9 limitation),
so there is nothing to train on or to 5.4-style re-validate against. This pipeline is what the
captured demo/real events will FEED once we have them; training + re-validation await that
data. Do not read "v2" here as "a better model shipped" — read it as "the proxy-free feature
derivation the better model will use is built and tested".

**OBSERVE-ONLY / gated (ARCHITECTURE.md §14 invariant 9).** This module does NOT touch the
live turn loop, does NOT replace the v1 predictor, and is NOT wired to any live decision. Even
once a v2 model is trained on real events, invariant 9 keeps it observe-only: it would feed the
SUSTAINED gate as one more conservative signal, never a direct live intervention. There is no
seam here that fires anything.

**Leakage-safety (the load-bearing invariant, mirrored from v1).** Each episode's feature row
is computed from the learner's PRIOR episodes only — never the current episode's own outcome.
``derive_v2_features`` builds the window over ``episodes[:i]`` exactly as ``features._features_at``
builds it over ``session[:i]``. ``test_events_features`` pins this with a leakage guard.

No LLM, no SymPy, no DB, no numpy, no network (CLAUDE.md §7, §8.1/§8.2) — pure stdlib +
dataclasses, deterministic (same events ⇒ same vectors, PROJECT.md §4.1). The repository read
that loads the raw events lives in ``db/repositories.py`` (queries-only); this module takes the
already-loaded rows. Defensive about missing/garbled payload keys: real telemetry payloads are
open JSON (``models.py``), so every payload read tolerates a missing or wrong-typed key with a
sane default rather than crashing the pipeline.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from app.domain.knowledge_components import KnowledgeComponentId
from app.helpneed.features import KC_ORDER, RECENT_WINDOW
from app.helpneed.labels import HINT_DEPENDENCE_THRESHOLD

# A learner reaching the DEEPEST help on one problem ≈ the v1 "requested the answer / gave up"
# signal. v1's loop has no give-up button, and the EDM Cup label keyed on an explicit
# requested-answer event; here we reconstruct that faithfully from the help-escalation the live
# tutor DOES have. Our hint ladder escalates (nudge → partial_step → worked_step); reaching the
# worked-step depth — its proxy here being the 3rd hint request on one problem — is the learner
# effectively asking to be shown the answer. So ``>= GIVE_UP_HINT_THRESHOLD`` hint requests on a
# single problem retires the live request-answer proxy faithfully. Tunable + named so a change
# is a deliberate, reviewed edit (decision 2026-05-28; aligns with the §3.4 escalation ladder).
GIVE_UP_HINT_THRESHOLD = 3

# The event tags this derivation reads (the PL.2 frontend vocabulary, ``frontend/src/telemetry``).
# Named constants so a vocabulary change is one edit, and so a typo can't silently drop a signal.
EV_PROBLEM_PRESENTED = "problem_presented"
EV_FIRST_INTERACTION = "first_interaction"
EV_ANSWER_EDIT = "answer_edit"
EV_NUMBERLINE_MOVE = "numberline_move"
EV_HINT_REQUEST = "hint_request"
EV_SUBMIT = "submit"
EV_IDLE = "idle"

# The v2 numeric (non-KC) feature columns, in to_vector() order. The first five MIRROR v1's
# window-based shape (``features._NUMERIC_FEATURE_NAMES``) so a v2 model is a drop-in on those
# columns; the difference is HOW two of them are computed (see the per-column note in
# HelpNeedV2Features). The last two are NEW columns v1 could not express. FEATURE_NAMES_V2
# appends the same one-hot KC columns v1 uses, by the same KC_ORDER, for SHAP-by-column-index.
_NUMERIC_FEATURE_NAMES_V2: tuple[str, ...] = (
    "recent_latency_ms_mean",
    "recent_attempts_mean",  # RETIRES the attempts≡1.0 proxy: real count of submit events
    "recent_hint_rate",
    "recent_error_rate",
    "recent_request_answer_rate",  # RETIRES the hint-rate proxy: real give-up escalation rate
    "turns_since_last_correct",
    "prior_unproductive_rate",
    "session_position",
    "recent_revisions_mean",  # NEW: mean answer edits + number-line moves per recent problem
    "recent_time_to_first_interaction_ms_mean",  # NEW: mean time-to-first-touch per recent problem
)
# Reuse v1's exact KC ordering (KC_ORDER) so the one-hot columns line up between v1 and v2.
FEATURE_NAMES_V2: tuple[str, ...] = _NUMERIC_FEATURE_NAMES_V2 + tuple(
    f"kc_{kc.value}" for kc in KC_ORDER
)


class _EventLike(Protocol):
    """The minimal shape ``derive`` reads off an event row — an ``InteractionEvent`` satisfies it.

    Declared structurally (not as the ORM class) so this module stays free of any DB import: the
    derivation is pure and testable with plain stand-in objects, and the repository (the only
    place that touches the ORM) hands it real ``InteractionEvent`` rows that match this shape.
    """

    @property
    def event_type(self) -> str: ...

    @property
    def payload(self) -> dict[str, Any]: ...


def _payload_int(payload: dict[str, Any], key: str) -> int | None:
    """Read an int-valued payload field defensively, or ``None`` if missing/garbled.

    Telemetry payloads are open JSON (``models.py``), so a key may be absent, ``None``, or the
    wrong type (a string, a float-as-text). We accept real ints and floats and integer-ish
    strings; anything else yields ``None`` (treated as "not reported"), never an exception — the
    pipeline must survive a malformed event rather than abort a learner's whole derivation.
    """
    value = payload.get(key)
    if isinstance(value, bool):  # bool is an int subclass; a flag is not a millisecond count
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


@dataclass(frozen=True)
class ProblemSignals:
    """The tutor-native signals one PROBLEM episode makes real (Slice PL.4).

    Derived from the slice of events between one ``problem_presented`` and the next. Frozen — a
    derived signal set is a fact about how the problem was worked, not mutable state. These are
    the per-episode primitives ``derive_v2_features`` aggregates into a windowed feature row.

    Fields and what each retires / adds versus v1:

      - ``attempts`` — count of ``submit`` events on the problem. RETIRES the live
        attempts≡1.0 proxy: in today's one-submit loop this is usually 1, but it is now a REAL
        count, not an assumed constant, so a future multi-submit flow is captured for free.
      - ``hint_requests`` — count of ``hint_request`` events on the problem.
      - ``requested_answer`` — whether the deepest help was reached: ``hint_requests >=
        GIVE_UP_HINT_THRESHOLD`` (≈ escalated to the worked-step "show me the answer" depth).
        RETIRES the live request-answer proxy faithfully — a real escalation signal, not the raw
        hint rate. Tunable via ``GIVE_UP_HINT_THRESHOLD``.
      - ``answer_revisions`` — count of ``answer_edit`` + ``numberline_move`` events. NEW: an
        effort/uncertainty signal v1 could not observe (the clickstream had no edit granularity).
      - ``time_to_first_interaction_ms`` — from ``first_interaction.elapsed_ms``; ``None`` if the
        learner never touched the problem or the payload omitted it.
      - ``idle_events`` — count of ``idle`` events during the problem (a disengagement signal).
      - ``submit_latency_ms`` — from the LAST ``submit`` event's ``latency_ms``; ``None`` if no
        submit or the payload omitted it (mirrors v1's latency-to-first-response feature source).
    """

    attempts: int
    hint_requests: int
    requested_answer: bool
    answer_revisions: int
    time_to_first_interaction_ms: int | None
    idle_events: int
    submit_latency_ms: int | None


def split_into_problem_episodes(events: Iterable[_EventLike]) -> list[list[_EventLike]]:
    """Segment a time-ordered event stream into per-PROBLEM episodes (split on problem_presented).

    Each ``problem_presented`` opens a new episode; every following event belongs to it until the
    next ``problem_presented``. Events that arrive BEFORE the first ``problem_presented`` (stray
    ambient ``focus``/``blur``/``idle`` before any problem mounted) are dropped — they belong to
    no problem and carry no per-problem signal. The ``problem_presented`` event itself is kept as
    the first element of its episode (it carries the ``kc`` the episode is about). Order within an
    episode is the input order, so the caller must pass events already chronologically ordered
    (the repository's ``load_events_for_*`` does exactly this).
    """
    episodes: list[list[_EventLike]] = []
    current: list[_EventLike] | None = None
    for event in events:
        if event.event_type == EV_PROBLEM_PRESENTED:
            current = [event]
            episodes.append(current)
        elif current is not None:
            current.append(event)
    return episodes


def _episode_kc(episode: Sequence[_EventLike]) -> KnowledgeComponentId | None:
    """The KC this episode is about, from the opening ``problem_presented`` payload, or ``None``.

    Defensive: returns ``None`` if the episode does not open with a ``problem_presented``, if the
    payload omits ``kc``, or if ``kc`` is not a recognized catalog string — a feature row cannot
    be built for an episode whose KC is unknown (the one-hot has nothing to set), so the caller
    skips such episodes rather than guessing.
    """
    if not episode or episode[0].event_type != EV_PROBLEM_PRESENTED:
        return None
    raw = episode[0].payload.get("kc")
    if not isinstance(raw, str):
        return None
    try:
        return KnowledgeComponentId(raw)
    except ValueError:
        return None


def derive_problem_signals(events_for_one_problem: Sequence[_EventLike]) -> ProblemSignals:
    """Derive the ``ProblemSignals`` for one problem episode (the per-episode primitive).

    ``events_for_one_problem`` is the slice for a single problem (typically a
    ``problem_presented`` followed by the touches/edits/hints/submit on it, as produced by
    ``split_into_problem_episodes``). Every payload read is defensive (see ``_payload_int``): a
    missing or garbled key yields a sane default, never a crash, because telemetry payloads are
    open JSON the surface may evolve.
    """
    attempts = 0
    hint_requests = 0
    answer_revisions = 0
    idle_events = 0
    time_to_first_interaction_ms: int | None = None
    submit_latency_ms: int | None = None

    for event in events_for_one_problem:
        etype = event.event_type
        if etype == EV_SUBMIT:
            attempts += 1
            # Take the latest submit's latency as THE submit latency for the problem (the final
            # answering attempt's timing); defensive if the payload omits it.
            latency = _payload_int(event.payload, "latency_ms")
            if latency is not None:
                submit_latency_ms = latency
        elif etype == EV_HINT_REQUEST:
            hint_requests += 1
        elif etype in (EV_ANSWER_EDIT, EV_NUMBERLINE_MOVE):
            answer_revisions += 1
        elif etype == EV_IDLE:
            idle_events += 1
        elif etype == EV_FIRST_INTERACTION and time_to_first_interaction_ms is None:
            # First-touch is a single edge per problem; keep the first one we see.
            time_to_first_interaction_ms = _payload_int(event.payload, "elapsed_ms")

    return ProblemSignals(
        attempts=attempts,
        hint_requests=hint_requests,
        requested_answer=hint_requests >= GIVE_UP_HINT_THRESHOLD,
        answer_revisions=answer_revisions,
        time_to_first_interaction_ms=time_to_first_interaction_ms,
        idle_events=idle_events,
        submit_latency_ms=submit_latency_ms,
    )


@dataclass(frozen=True)
class ProblemEpisode:
    """One problem's derived signals plus the KC it concerned — what windowed features range over.

    Pairs ``ProblemSignals`` (the per-problem primitives) with the episode's ``kc`` (from the
    ``problem_presented`` payload). ``derive_v2_features`` builds one feature row per episode from
    the PRIOR episodes' signals plus this episode's KC (the KC is a property of the CURRENT
    problem, known at presentation time, so it is not a leak — mirrors v1 using ``current.kc``).
    """

    kc: KnowledgeComponentId
    signals: ProblemSignals


def build_episodes(events: Iterable[_EventLike]) -> list[ProblemEpisode]:
    """Build ordered ``ProblemEpisode``s from a learner/session event stream.

    Splits the stream into per-problem episodes, derives each one's signals, and attaches its KC.
    Episodes whose KC cannot be resolved (no/garbled ``problem_presented`` payload) are dropped —
    a feature row needs a KC for its one-hot, and a guessed KC would corrupt the column. The
    input must be chronologically ordered (the repository read guarantees this).
    """
    episodes: list[ProblemEpisode] = []
    for raw_episode in split_into_problem_episodes(events):
        kc = _episode_kc(raw_episode)
        if kc is None:
            continue
        episodes.append(ProblemEpisode(kc=kc, signals=derive_problem_signals(raw_episode)))
    return episodes


def _is_unproductive_episode(signals: ProblemSignals) -> bool:
    """Whether an episode was UNPRODUCTIVE, by the §3.4 label applied to REAL event signals.

    Mirrors ``labels.is_unproductive`` faithfully on the v2 primitives (decision 2026-05-27 label
    definition, reused here rather than re-derived): a give-up (``requested_answer``), or leaning
    on help (``hint_requests >= HINT_DEPENDENCE_THRESHOLD``). The event stream alone does NOT carry
    SymPy's correctness verdict (that is the turn loop's, recorded on the ``Turn`` row, not in the
    behavioral capture), so the "never solved it / floundered on wrong tries" arms of the label
    are intentionally NOT reconstructed from events here — they require joining the verified Turn
    outcome, which is a follow-up once real data lands. This is stated plainly so the decision log
    is honest: the v2 prior-unproductive feature is a HELP-SEEKING-based subset of the §3.4 label
    until the Turn join is added. The threshold is imported from ``labels`` so the two stay locked.
    """
    return signals.requested_answer or signals.hint_requests >= HINT_DEPENDENCE_THRESHOLD


@dataclass(frozen=True)
class HelpNeedV2Features:
    """One episode's v2 feature row, derived from the behavioral event stream (Slice PL.4).

    Frozen, and mirroring v1's ``HelpNeedFeatures`` shape on the first eight numeric columns so a
    v2 model is a drop-in on them — EXCEPT two columns are now computed FAITHFULLY from real
    per-problem signals instead of the v1 live proxies:

      - ``recent_attempts_mean`` — mean of REAL ``submit`` counts over the recent window (retires
        the live attempts≡1.0 proxy).
      - ``recent_request_answer_rate`` — mean of the REAL give-up signal (``requested_answer``,
        the ``>= GIVE_UP_HINT_THRESHOLD`` hint escalation) over the recent window (retires the
        live hint-rate proxy; it no longer just mirrors ``recent_hint_rate``).

    Plus two NEW columns v1 could not express:

      - ``recent_revisions_mean`` — mean answer edits + number-line moves per recent problem.
      - ``recent_time_to_first_interaction_ms_mean`` — mean time-to-first-touch per recent problem
        (over the episodes that reported one).

    All history features are computed over the learner's episodes BEFORE this one (the leakage
    invariant). ``to_vector`` flattens to the numeric input (KC one-hot appended) in
    ``FEATURE_NAMES_V2`` order.
    """

    recent_latency_ms_mean: float
    recent_attempts_mean: float
    recent_hint_rate: float
    recent_error_rate: float
    recent_request_answer_rate: float
    turns_since_last_correct: float
    prior_unproductive_rate: float
    session_position: float
    recent_revisions_mean: float
    recent_time_to_first_interaction_ms_mean: float
    kc: KnowledgeComponentId

    def to_vector(self) -> tuple[float, ...]:
        """Flatten to the numeric model input (KC one-hot appended), in FEATURE_NAMES_V2 order."""
        numeric = (
            self.recent_latency_ms_mean,
            self.recent_attempts_mean,
            self.recent_hint_rate,
            self.recent_error_rate,
            self.recent_request_answer_rate,
            self.turns_since_last_correct,
            self.prior_unproductive_rate,
            self.session_position,
            self.recent_revisions_mean,
            self.recent_time_to_first_interaction_ms_mean,
        )
        one_hot = tuple(1.0 if self.kc is kc else 0.0 for kc in KC_ORDER)
        return numeric + one_hot


def _mean(values: Sequence[float]) -> float:
    """Arithmetic mean, or 0.0 for an empty sequence (the neutral 'no history' value).

    Matches ``features._mean`` / ``live_features._mean`` exactly so the v2 cold-start row is
    all-neutral on the same empty-history handling the v1 builders use.
    """
    return sum(values) / len(values) if values else 0.0


def _v2_features_at(episodes: Sequence[ProblemEpisode], index: int) -> HelpNeedV2Features:
    """Build the v2 feature row for ``episodes[index]`` from the episodes BEFORE it.

    ``prior`` is everything earlier; ``window`` is the most recent ``RECENT_WINDOW`` of those.
    Empty history (index 0) yields all-neutral features. This is the v2 analogue of
    ``features._features_at`` and enforces the SAME leakage discipline: nothing from
    ``episodes[index]``'s own signals enters its row — only the CURRENT episode's KC (a
    presentation-time property, not an outcome) is read from it.
    """
    current = episodes[index]
    prior = episodes[:index]
    window = prior[-RECENT_WINDOW:]

    # Error rate from the help-seeking-based unproductive subset (see _is_unproductive_episode):
    # the event stream alone has no SymPy correctness verdict, so "error" here is the
    # give-up/hint-dependence signal, not a wrong-answer count. Documented as a subset, not a
    # silent equivalence.
    window_unproductive = [1.0 if _is_unproductive_episode(e.signals) else 0.0 for e in window]

    # turns since the last PRODUCTIVE prior episode (1 if the immediately-preceding one was
    # productive); equal to the session position when no prior episode was productive yet. The
    # v1 "last correct" anchor is unavailable from events (no correctness verdict), so we anchor
    # on the last productive episode — the faithful event-only analogue.
    turns_since_last_productive = float(index)
    for offset, episode in enumerate(reversed(prior), start=1):
        if not _is_unproductive_episode(episode.signals):
            turns_since_last_productive = float(offset)
            break

    ttfi = [
        float(e.signals.time_to_first_interaction_ms)
        for e in window
        if e.signals.time_to_first_interaction_ms is not None
    ]
    latencies = [
        float(e.signals.submit_latency_ms)
        for e in window
        if e.signals.submit_latency_ms is not None
    ]

    return HelpNeedV2Features(
        recent_latency_ms_mean=_mean(latencies),
        # RETIRES the attempts≡1.0 proxy: the REAL mean submit count over the window.
        recent_attempts_mean=_mean([float(e.signals.attempts) for e in window]),
        recent_hint_rate=_mean([1.0 if e.signals.hint_requests > 0 else 0.0 for e in window]),
        recent_error_rate=_mean(window_unproductive),
        # RETIRES the hint-rate proxy: the REAL give-up escalation rate over the window.
        recent_request_answer_rate=_mean(
            [1.0 if e.signals.requested_answer else 0.0 for e in window]
        ),
        turns_since_last_correct=turns_since_last_productive,
        prior_unproductive_rate=_mean(
            [1.0 if _is_unproductive_episode(e.signals) else 0.0 for e in prior]
        ),
        session_position=float(index),
        recent_revisions_mean=_mean([float(e.signals.answer_revisions) for e in window]),
        recent_time_to_first_interaction_ms_mean=_mean(ttfi),
        kc=current.kc,
    )


def derive_v2_features(episodes: Sequence[ProblemEpisode]) -> list[HelpNeedV2Features]:
    """Build one ``HelpNeedV2Features`` row per episode, in order (the offline pipeline output).

    Each row's history is the episodes strictly before it (windowing per the learner's own
    earlier episodes), so the first episode has neutral history — the same per-stream discipline
    v1 enforces with ``session_examples``. The caller pairs these with labels once real,
    SymPy-verified outcomes are joined in (PROJECT.md §9 — no such data yet, so this ships the
    features only, never a trained model).
    """
    return [_v2_features_at(episodes, i) for i in range(len(episodes))]


__all__ = [
    "EV_ANSWER_EDIT",
    "EV_FIRST_INTERACTION",
    "EV_HINT_REQUEST",
    "EV_IDLE",
    "EV_NUMBERLINE_MOVE",
    "EV_PROBLEM_PRESENTED",
    "EV_SUBMIT",
    "FEATURE_NAMES_V2",
    "GIVE_UP_HINT_THRESHOLD",
    "HelpNeedV2Features",
    "ProblemEpisode",
    "ProblemSignals",
    "build_episodes",
    "derive_problem_signals",
    "derive_v2_features",
    "split_into_problem_episodes",
]
