"""Tests for the synthetic HelpNeed-trace generator (Slice 0.1, V2_TODO WAVE 0).

The generator drives the deterministic Layer-3 persona simulator over a problem sequence and
emits ``InteractionEvent``-shaped events in the REAL PL.2 telemetry vocabulary, plus a
ground-truth per-episode unproductive label. These tests pin the four properties the slice's
exit criteria require (V2_TODO Slice 0.1 "Tests"):

  1. The synthetic events parse through the EXISTING v2 pipeline (``events_features``) UNCHANGED
     into the expected number of episodes.
  2. (LOAD-BEARING) The generator's ground-truth label MATCHES ``_is_unproductive_episode`` on the
     ``ProblemSignals`` the pipeline derives from the SAME events — synthetic label == pipeline
     label, no divergence. This proves the synthetic data is self-consistent with the real
     labeling logic and carries no leakage (the label is a function of the emitted events only).
  3. Determinism: same (persona, sequence) ⇒ byte-identical events.
  4. Persona contrast: a help-seeking struggler (Hint-hunter Hugo, hint-dependent on a KC he does
     not hold) yields unproductive episodes; a genuinely-capable learner on KNOWN material
     (Capable Cora, BOTH-mode) does not. The contrast reads the personas' CONFIGURED knowledge
     states through the simulator — outcomes are not hardcoded.

HONEST SCOPE (mirrors ``events_features._is_unproductive_episode``): the event-only label is the
HELP-SEEKING subset of the §3.4 unproductive definition — it catches a learner who LEANS ON HELP
(Hugo), not one who silently submits a wrong answer without asking (Cleo, Sam out-of-format). The
event stream alone carries no SymPy correctness verdict, exactly as the pipeline documents. So the
struggler used for the unproductive-contrast is deliberately a HELP-SEEKER; the silently-wrong
personas are asserted to be label-consistent (whatever the pipeline derives), not to be flagged
unproductive — that would require the Turn-outcome join the pipeline explicitly defers.

Pure-function tests: no DB, no LLM, no SymPy reach-through here (CLAUDE.md §8.1/§8.2). The
generator is deterministic, so every assertion is exact.
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.helpneed.events_features import (
    EV_PROBLEM_PRESENTED,
    EV_SUBMIT,
    _is_unproductive_episode,
    build_episodes,
    derive_problem_signals,
    split_into_problem_episodes,
)
from app.helpneed.synthetic_traces import (
    LabeledEpisode,
    SyntheticEvent,
    generate_persona_trace,
)
from app.personas.registry import get_persona
from app.personas.run import ProblemSpec

_ADD = KnowledgeComponentId.ADDITION_UNLIKE


def _symbolic_sequence(n: int) -> list[ProblemSpec]:
    """``n`` routine symbolic ADDITION_UNLIKE problems, distinct seeds (a plain practice block)."""
    return [
        ProblemSpec(kc=_ADD, seed=i, surface_format=Representation.SYMBOLIC)
        for i in range(1, n + 1)
    ]


# --------------------------------------------------------------------------------------------
# 1. The events round-trip the EXISTING pipeline unchanged.
# --------------------------------------------------------------------------------------------


def test_events_satisfy_event_like_shape() -> None:
    """Each emitted event is a ``SyntheticEvent`` with a string tag and a dict payload."""
    trace = generate_persona_trace(get_persona("capable_cora"), _symbolic_sequence(3))
    assert trace.events
    for event in trace.events:
        assert isinstance(event, SyntheticEvent)
        assert isinstance(event.event_type, str)
        assert isinstance(event.payload, dict)


def test_every_episode_opens_with_problem_presented_and_a_submit() -> None:
    """The vocabulary is faithful: each episode opens with problem_presented and has a submit."""
    trace = generate_persona_trace(get_persona("capable_cora"), _symbolic_sequence(3))
    raw_episodes = split_into_problem_episodes(trace.events)
    assert len(raw_episodes) == 3
    for raw in raw_episodes:
        assert raw[0].event_type == EV_PROBLEM_PRESENTED
        assert any(e.event_type == EV_SUBMIT for e in raw)


def test_events_parse_into_expected_episode_count() -> None:
    """The synthetic events feed ``build_episodes`` UNCHANGED into one episode per problem."""
    sequence = _symbolic_sequence(5)
    trace = generate_persona_trace(get_persona("hint_hunter_hugo"), sequence)
    episodes = build_episodes(trace.events)
    assert len(episodes) == len(sequence)
    assert all(e.kc is _ADD for e in episodes)


def test_problem_presented_carries_the_catalog_kc_string() -> None:
    """The presented event's ``kc`` payload is the catalog string the pipeline resolves on."""
    trace = generate_persona_trace(get_persona("capable_cora"), _symbolic_sequence(1))
    presented = trace.events[0]
    assert presented.event_type == EV_PROBLEM_PRESENTED
    assert presented.payload["kc"] == _ADD.value


# --------------------------------------------------------------------------------------------
# 2. LOAD-BEARING: ground-truth label == the pipeline-derived label (no divergence).
# --------------------------------------------------------------------------------------------


def test_ground_truth_label_matches_pipeline_label_for_every_episode() -> None:
    """The generator's per-episode label equals ``_is_unproductive_episode`` on the pipeline's
    own ``ProblemSignals`` for the SAME episode — across every persona, every turn."""
    sequence = _symbolic_sequence(6)
    for persona_id in (
        "natural_number_nate",
        "procedure_priya",
        "hint_hunter_hugo",
        "surface_sam",
        "click_through_cleo",
        "capable_cora",
    ):
        trace = generate_persona_trace(get_persona(persona_id), sequence)
        raw_episodes = split_into_problem_episodes(trace.events)
        assert len(raw_episodes) == len(trace.episodes)
        for labeled, raw in zip(trace.episodes, raw_episodes, strict=True):
            signals = derive_problem_signals(raw)
            assert labeled.unproductive == _is_unproductive_episode(signals), (
                f"{persona_id}: synthetic label {labeled.unproductive} != pipeline label "
                f"{_is_unproductive_episode(signals)}"
            )


def test_labeled_episode_label_is_a_function_of_its_own_events_only() -> None:
    """A ``LabeledEpisode`` label is reproducible from its own events (no hidden state, no leak)."""
    trace = generate_persona_trace(get_persona("hint_hunter_hugo"), _symbolic_sequence(4))
    for labeled in trace.episodes:
        recomputed = _is_unproductive_episode(derive_problem_signals(labeled.events))
        assert labeled.unproductive == recomputed


# --------------------------------------------------------------------------------------------
# 3. Determinism.
# --------------------------------------------------------------------------------------------


def test_same_inputs_yield_identical_events() -> None:
    """Same (persona, sequence) ⇒ byte-identical event tags AND payloads (reproducibility)."""
    sequence = _symbolic_sequence(5)
    persona = get_persona("hint_hunter_hugo")
    a = generate_persona_trace(persona, sequence)
    b = generate_persona_trace(persona, sequence)
    assert [(e.event_type, e.payload) for e in a.events] == [
        (e.event_type, e.payload) for e in b.events
    ]
    assert [ep.unproductive for ep in a.episodes] == [ep.unproductive for ep in b.episodes]


# --------------------------------------------------------------------------------------------
# 4. Persona contrast (reads CONFIGURED knowledge states, not hardcoded outcomes).
# --------------------------------------------------------------------------------------------


def test_hint_dependent_struggler_yields_unproductive_episodes() -> None:
    """Hint-hunter Hugo (hint-dependent, NEITHER on the KC) leans on help → unproductive episodes.

    Hugo's >0.70 hint-dependence is the §4.2 P3 signature; the simulator makes his correct answer
    mechanical-via-scaffold, which the generator encodes as a help-escalation the event-label reads
    as unproductive. We assert at least one such episode (his help-seeking is the whole point)."""
    trace = generate_persona_trace(get_persona("hint_hunter_hugo"), _symbolic_sequence(5))
    assert any(ep.unproductive for ep in trace.episodes)


def test_capable_learner_on_known_material_is_not_unproductive() -> None:
    """Capable Cora (BOTH on the KC) answers cleanly without leaning on help → no unproductive."""
    trace = generate_persona_trace(get_persona("capable_cora"), _symbolic_sequence(5))
    assert not any(ep.unproductive for ep in trace.episodes)


def test_capable_and_struggler_contrast_on_the_same_sequence() -> None:
    """On the identical block, the struggler has strictly more unproductive episodes than the
    capable learner — the signal the predictor is meant to separate."""
    sequence = _symbolic_sequence(6)
    hugo = generate_persona_trace(get_persona("hint_hunter_hugo"), sequence)
    cora = generate_persona_trace(get_persona("capable_cora"), sequence)
    hugo_unproductive = sum(ep.unproductive for ep in hugo.episodes)
    cora_unproductive = sum(ep.unproductive for ep in cora.episodes)
    assert hugo_unproductive > cora_unproductive


def test_episodes_align_one_to_one_with_the_sequence() -> None:
    """One ``LabeledEpisode`` per ``ProblemSpec`` (a submitted answer per problem)."""
    sequence = _symbolic_sequence(4)
    trace = generate_persona_trace(get_persona("procedure_priya"), sequence)
    assert len(trace.episodes) == len(sequence)
    assert all(isinstance(ep, LabeledEpisode) for ep in trace.episodes)
