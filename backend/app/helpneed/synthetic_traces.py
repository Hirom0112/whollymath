"""Synthetic HelpNeed labeled-trace generator from the persona simulator (Slice 0.1, V2_TODO W0).

**What this is.** A pure, deterministic source of LABELED behavioral traces for the proxy-free v2
HelpNeed pipeline, built from the existing Layer-3 persona simulator (``personas/run.py`` →
``personas/simulator.py``). Given a persona config and a problem sequence, it drives the simulator
and emits an ordered list of ``InteractionEvent``-shaped events in the REAL PL.2 telemetry
vocabulary (``events_features.py`` / ``frontend/src/telemetry/telemetry.ts``), PLUS a ground-truth
per-episode unproductive label the persona's behavior implies. Those events parse through the
UNCHANGED v2 pipeline (``build_episodes`` → ``derive_v2_features``); the labels pair with the
features to train the experimental v2 model (``train_synthetic.py``).

**Why synthetic, and the honest limitation (PROJECT.md §9; V2_TODO Slice 0.1).** We have NO real
WhollyMath student events — ``interaction_event`` is empty — so the v2 model cannot be trained or
validated on our own learners yet. The deterministic personas are the one source that can stamp a
GROUND-TRUTH help-need label no real clickstream carries (synthetic-for-knowledge-tracing is
literature-validated: arXiv 2401.16832; DASKT 2025; AdvKT 2026). This is an OBSERVE-ONLY /
SYNTHETIC training source that AWAITS real-student validation; it is NOT a shippable model and
NOT wired to any live decision (ARCHITECTURE.md §14 invariant 9 keeps any v2 observe-only).

**The label is the HELP-SEEKING SUBSET of §3.4 — by construction, faithfully.** The generator's
ground-truth label is defined to AGREE EXACTLY with the pipeline's ``_is_unproductive_episode``,
which keys on help-escalation (give-up / hint-dependence) and DELIBERATELY cannot see SymPy
correctness (the event stream carries no verdict; the pipeline documents this as a subset until the
Turn-outcome join lands). So the generator encodes a persona's behavioral struggle as a faithful
HINT-ESCALATION on the help ladder (nudge → partial_step → worked_step), and the label it stamps is
``_is_unproductive_episode`` applied to the emitted events. This makes the synthetic label provably
self-consistent with the real labeling logic (``test_synthetic_traces`` pins the agreement) and
carries no leakage: a label is a function of that episode's own events only. A persona who struggles
SILENTLY (a wrong answer without asking for help — Cleo, Sam out of his tied format) is correctly
NOT flagged by the event-only label, exactly as a real telemetry-only detector could not flag it.

Hard boundaries (CLAUDE.md §7, §8.1/§8.2): NO DB, NO LLM, NO SymPy reach-through here. Correctness
is the simulator's already-verified concern (it wires the SymPy verifier inside ``run_persona``);
this module only TRANSCRIBES the recorded turns into events and a label. Deterministic: same
(persona, sequence) ⇒ identical events and labels, because every underlying piece is deterministic
(PROJECT.md §4.1; ARCHITECTURE.md §5 Layer 3).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from app.domain.knowledge_components import KnowledgeComponentId
from app.helpneed.events_features import (
    EV_ANSWER_EDIT,
    EV_FIRST_INTERACTION,
    EV_HINT_REQUEST,
    EV_IDLE,
    EV_PROBLEM_PRESENTED,
    EV_SUBMIT,
    GIVE_UP_HINT_THRESHOLD,
    _is_unproductive_episode,
    derive_problem_signals,
)
from app.helpneed.labels import HINT_DEPENDENCE_THRESHOLD
from app.personas.persona_config import PersonaConfig
from app.personas.run import PersonaTurn, ProblemSpec, run_persona

# ─── Faithful magnitudes for the synthesized event payloads ──────────────────
# These derive each event's timing from the simulator's per-turn ``think_time_seconds`` so the
# emitted stream looks like real telemetry (a first touch, then a final submit). They are named
# constants, not magic numbers, so a change is a deliberate, reviewed edit (CLAUDE.md §6).

# A learner's first touch lands partway into their think time; the rest is working the answer. A
# simple fixed fraction is enough for a faithful, monotone time-to-first-interaction signal.
_FIRST_INTERACTION_FRACTION = 0.3

# An idle event is emitted when the persona barely engages (think time below this floor) — the
# disengagement tell the surface captures (Cleo's sub-2s floor, §4.2 P5). Below the floor we stamp
# one idle event so the trace carries the low-engagement signal the v2 schema can later read.
_IDLE_THINK_FLOOR_SECONDS = 2.0

# How many answer-revision events (answer_edit) a persona makes before submitting, by behavior.
# A persona who requested a hint is uncertain and revises more; a confident one revises once. This
# only feeds the NEW v2 ``recent_revisions_mean`` column — it never affects the label (which keys on
# hints only), so the exact counts are a faithfulness nicety, not a load-bearing choice.
_REVISIONS_CONFIDENT = 1
_REVISIONS_UNCERTAIN = 2


@dataclass(frozen=True)
class SyntheticEvent:
    """One synthesized behavioral event — a plain (event_type, payload) pair.

    Structurally satisfies the pipeline's ``_EventLike`` Protocol (``events_features._EventLike``),
    so it parses through ``split_into_problem_episodes`` / ``derive_problem_signals`` with NO change
    to the pipeline — the same way a real ``InteractionEvent`` row does. Frozen because a recorded
    event is a fact about the (simulated) turn, not mutable state (mirrors ``SimulatedAction`` /
    ``InteractionEvent``). The payload uses the SAME keys the frontend telemetry emits
    (``problem_id``, ``kc``, ``elapsed_ms``, ``latency_ms``) so the trace is faithful to production.
    """

    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LabeledEpisode:
    """One problem's synthesized events plus the ground-truth unproductive label.

    ``events`` is the ordered slice for a single problem (a ``problem_presented`` followed by the
    touches / revisions / hint escalations / submit). ``unproductive`` is the ground-truth label —
    defined as ``_is_unproductive_episode`` applied to the signals derived from THESE events, so it
    is provably consistent with the pipeline's labeling logic and is a function of this episode's
    own events only (no leakage). ``kc`` is the episode's knowledge component (for grouping /
    per-KC analysis). Frozen: a labeled episode is a recorded fact.
    """

    kc: KnowledgeComponentId
    events: list[SyntheticEvent]
    unproductive: bool


@dataclass(frozen=True)
class SyntheticTrace:
    """The full synthesized trace for one persona over one sequence.

    ``events`` is the FLAT, time-ordered event stream (the concatenation of every episode's events)
    — exactly what ``build_episodes`` / the repository read consume. ``episodes`` is the per-problem
    breakdown with ground-truth labels, one ``LabeledEpisode`` per submitted problem. Frozen.
    """

    persona_id: str
    events: list[SyntheticEvent]
    episodes: list[LabeledEpisode]


def _hint_escalation_count(turn: PersonaTurn) -> int:
    """How many hint_request events this turn emits, by the persona's behavior on the help ladder.

    The event-only label (``_is_unproductive_episode``) keys on help escalation: ``>=
    HINT_DEPENDENCE_THRESHOLD`` (2) hints is leaning-on-help, ``>= GIVE_UP_HINT_THRESHOLD`` (3) is a
    give-up. We map the simulator's per-turn signals onto that ladder FAITHFULLY:

      - No hint requested → 0. A persona who never asked for help leaves no help-seeking trace,
        whatever the answer's correctness (the event-only label cannot, and must not, see that).
      - Hint requested AND the answer was correct AND the persona can justify it → 1. A fluent
        learner who glanced at a single nudge and understood it is NOT hint-dependent.
      - Hint requested but the persona CANNOT justify, yet ended up correct → 2 (hint-dependence).
        This is the Hint-hunter-Hugo signature (§4.2 P3): the scaffold supplied the answer
        mechanically, so they escalated past the first nudge to reproduce it without understanding.
      - Hint requested and the answer was STILL wrong → 3 (give-up). They climbed the whole ladder
        to the worked-step depth and still did not solve it — the faithful give-up signal.

    Reads only the recorded turn (data, not behavior); deterministic.
    """
    action = turn.action
    if not action.requested_hint:
        return 0
    result = turn.result
    correct = result is not None and result.correct
    if not correct:
        return GIVE_UP_HINT_THRESHOLD  # climbed the ladder, still unsolved → give-up depth (3)
    if action.can_justify:
        return 1  # one nudge, genuinely understood → not hint-dependent
    return HINT_DEPENDENCE_THRESHOLD  # correct only via the scaffold, no concept → dependence (2)


def _revision_count(turn: PersonaTurn) -> int:
    """How many answer_edit revisions this turn emits (a faithfulness signal, never the label).

    A persona who reached for a hint was uncertain and revises more; a confident answerer revises
    once. Feeds only the NEW v2 ``recent_revisions_mean`` column — it does not enter the label.
    """
    return _REVISIONS_UNCERTAIN if turn.action.requested_hint else _REVISIONS_CONFIDENT


def _events_for_turn(turn: PersonaTurn) -> list[SyntheticEvent]:
    """Transcribe one recorded ``PersonaTurn`` into its ordered behavioral events.

    Emits the faithful PL.2 vocabulary in plausible order: ``problem_presented`` (carrying the KC
    and problem id), a ``first_interaction`` (time-to-first-touch derived from think time), any
    ``hint_request`` escalations (per ``_hint_escalation_count``), ``answer_edit`` revisions, an
    ``idle`` event when engagement is below the floor, and a final ``submit`` carrying the latency.
    Timings come from the simulator's ``think_time_seconds`` so the stream mirrors real telemetry.
    """
    problem = turn.problem
    action = turn.action
    think_ms = int(action.think_time_seconds * 1000)

    events: list[SyntheticEvent] = [
        SyntheticEvent(
            EV_PROBLEM_PRESENTED,
            {"problem_id": problem.problem_id, "kc": problem.kc.value},
        ),
        SyntheticEvent(
            EV_FIRST_INTERACTION,
            {"elapsed_ms": int(think_ms * _FIRST_INTERACTION_FRACTION)},
        ),
    ]

    # Hint escalations land before the final submit (the learner climbs the ladder, then answers).
    for i in range(_hint_escalation_count(turn)):
        events.append(SyntheticEvent(EV_HINT_REQUEST, {"elapsed_ms": int(think_ms * (i + 1) / 4)}))

    for _ in range(_revision_count(turn)):
        events.append(SyntheticEvent(EV_ANSWER_EDIT, {}))

    # A barely-engaged turn (sub-floor think time) leaves an idle/disengagement trace (Cleo P5).
    if action.think_time_seconds < _IDLE_THINK_FLOOR_SECONDS:
        events.append(SyntheticEvent(EV_IDLE, {"after_ms": think_ms}))

    events.append(
        SyntheticEvent(EV_SUBMIT, {"latency_ms": think_ms, "hint_used": action.requested_hint})
    )
    return events


def generate_persona_trace(
    persona: PersonaConfig,
    sequence: Sequence[ProblemSpec],
) -> SyntheticTrace:
    """Drive ``persona`` through ``sequence`` and emit a labeled synthetic event trace.

    Runs the persona on a fresh tutor session via ``run_persona`` (which wires the already-tested
    simulator + SymPy verifier + mastery update), then TRANSCRIBES each recorded turn that submitted
    an answer into its behavioral events. Each problem becomes one ``LabeledEpisode`` whose label is
    ``_is_unproductive_episode`` applied to the signals derived from that episode's own emitted
    events — so the ground-truth label is provably consistent with the v2 pipeline's labeling logic.

    Pure-EXPLAIN turns (no submitted answer, no verifier verdict) produce no events and no episode —
    they carry no per-problem answering signal. Deterministic: same (persona, sequence) ⇒ identical
    trace (every underlying piece is deterministic; PROJECT.md §4.1).
    """
    run = run_persona(persona, list(sequence))

    events: list[SyntheticEvent] = []
    episodes: list[LabeledEpisode] = []
    for turn in run.turns:
        if turn.action.submitted_answer is None:
            continue  # a pure-explain probe submits nothing → no answering episode
        episode_events = _events_for_turn(turn)
        signals = derive_problem_signals(episode_events)
        episodes.append(
            LabeledEpisode(
                kc=turn.problem.kc,
                events=episode_events,
                unproductive=_is_unproductive_episode(signals),
            )
        )
        events.extend(episode_events)

    return SyntheticTrace(persona_id=run.persona_id, events=events, episodes=episodes)


__all__ = [
    "LabeledEpisode",
    "SyntheticEvent",
    "SyntheticTrace",
    "generate_persona_trace",
]
