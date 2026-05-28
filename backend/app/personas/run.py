"""The persona-run driver — drive a persona through the reactive tutor (Slice 2.6).

This is the Week-2 persona integration checkpoint's engine (PROJECT.md §6: "Priya
and Sam can each take a tutor session end-to-end; we can read the logs and see
expected adversarial behavior"). It is the glue that turns a Layer-2 persona config
(``personas/``) plus a problem sequence into a recorded end-to-end tutor run, by
wiring three already-built, already-tested pieces together — and re-implementing
none of them (CLAUDE.md §7 boundaries):

  - the Layer-3 behavioral simulator (``personas/simulator.py``) computes, for each
    presented problem, the persona's deterministic action (answer, hint, think time,
    can_justify);
  - the reactive ``TutorSession`` (``tutor/session.py``) presents each problem,
    verifies the submitted answer via the SymPy domain verifier, updates the mastery
    view, and applies the §3.6 policy between problems;
  - the mastery model (``mastery/mastery_model.py``) is left to the CALLER to query
    on ``run.observations`` (e.g. ``declare_mastery(kc, run.observations)``), so the
    false-positive-mastery defense (PROJECT.md §3.11) is asserted on the exact
    evidence the run produced.

Hard boundaries (the same ones the simulator and tutor already hold): NO LLM, NO DB,
NO SymPy here — correctness is the verifier's job, the wrong-answer values are the
misconception generators' job, and the action is the simulator's job. This module
only sequences turns and records them.

Determinism (PROJECT.md §4.1; ARCHITECTURE.md §5): every input is fixed — the
persona config, the seeded problems, and the per-turn ``SimulationContext`` — and
each underlying piece is deterministic, so the SAME (persona, sequence) yields an
identical ``PersonaRun`` every call. That reproducibility is what makes the persona
suite the mastery model's integration suite (CLAUDE.md §9).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.domain.problem_generators import Problem
from app.mastery.mastery_model import Observation
from app.personas.persona_config import PersonaConfig
from app.personas.simulator import SimulatedAction, SimulationContext, simulate_action
from app.policy.surface_states import SurfaceState
from app.tutor.session import TurnResult, TutorSession


@dataclass(frozen=True)
class ProblemSpec:
    """One step in a persona run: which problem to present, and the turn's intent.

    The driver presents a fresh generated problem for ``kc`` in ``surface_format``
    from ``seed`` (deterministic — same seed ⇒ same problem; problem_generators.py),
    then asks the simulator for the persona's action under ``context``. The context
    carries the turn INTENT (a routine ANSWER, an EXPLAIN, or a FIND_ERROR with a
    claimed answer) — exactly the data the simulator reads to produce the §3.4 / §3.9
    evidence (simulator.py ``SimulationContext``). Frozen because a run's input
    sequence is fixed configuration, not mutable state (reproducibility).

    ``surface_format`` is the representation the SAME KC is presented in — the lever
    that lets a run INTERLEAVE one KC across formats (symbolic, area model, number
    line), which is precisely what surfaces Surface Sam's format-tied collapse
    (PROJECT.md §4.2 P4) and feeds the mastery model's representation-diversity and
    interleaving rules (§3.4 rules 2 and 4).
    """

    kc: KnowledgeComponentId
    seed: int
    surface_format: Representation = Representation.SYMBOLIC
    context: SimulationContext = field(default_factory=SimulationContext)


@dataclass(frozen=True)
class PersonaTurn:
    """One recorded turn of a persona run — the action, the problem, and the verdict.

    Frozen: a completed turn is a fact. Holds everything the Week-2 checkpoint needs
    to "read the log and see expected adversarial behavior" (PROJECT.md §6):

    - ``problem``    the ``Problem`` the tutor presented this turn (carries the KC,
      the format, and the SymPy correct value).
    - ``context``    the turn intent the simulator was asked under (ANSWER / EXPLAIN
      / FIND_ERROR) — so a reader can see WHICH probe a turn was.
    - ``action``     the persona's Layer-3 action (the submitted answer, hint flag,
      think time, and crucially ``can_justify`` — the procedure-without-concept tell
      §4.2 P2, which the SymPy verdict alone cannot show).
    - ``result``     the tutor's ``TurnResult`` (the verifier's verdict, the applied
      §3.6 transition + label, the per-KC mastery snapshot).
    - ``observation`` the mastery ``Observation`` this turn produced (the evidence
      ``declare_mastery`` ranges over). For an EXPLAIN turn with no numeric answer
      there is no tutor turn and hence no observation — see ``PersonaRun``.
    """

    problem: Problem
    context: SimulationContext
    action: SimulatedAction
    result: TurnResult | None
    observation: Observation | None


@dataclass(frozen=True)
class PersonaRun:
    """The recorded result of driving one persona through a problem sequence.

    Frozen view assembled by ``run_persona``. The fields are exactly what the §6
    checkpoint asserts on:

    - ``persona_id``      whose run this is.
    - ``turns``           every recorded ``PersonaTurn``, in order.
    - ``states_visited``  the surface states the run passed through, in order, with
      the starting state first and the state after each turn appended — so a reader
      sees the §3.6 walk the persona drove (e.g. an error moving S1→S3).
    - ``observations``    the flat list of mastery ``Observation`` records the run
      produced (skipping pure-EXPLAIN turns that submit no answer). This is the
      evidence the caller feeds to the mastery model:
      ``declare_mastery(kc, run.observations)`` — the run does NOT call the mastery
      model itself, so the false-positive-mastery defense is asserted by the test on
      this evidence (PROJECT.md §3.11; CLAUDE.md §9).
    - ``final_state``     the surface state the run ended in.
    """

    persona_id: str
    turns: tuple[PersonaTurn, ...]
    states_visited: tuple[SurfaceState, ...]
    observations: list[Observation]
    final_state: SurfaceState

    def mastery_snapshot(self, kc: KnowledgeComponentId) -> float | None:
        """The last reported BKT probability for ``kc`` across the run, or None.

        Convenience for logs/tests: pulls the most recent per-KC probability the
        tutor reported for ``kc`` (the mastery model decided it; this only reads it).
        ``None`` when the run never produced a snapshot for ``kc``.
        """
        for turn in reversed(self.turns):
            if turn.result is None:
                continue
            for snap in turn.result.mastery_snapshot:
                if snap.kc == kc:
                    return snap.probability
        return None


def run_persona(persona: PersonaConfig, sequence: list[ProblemSpec]) -> PersonaRun:
    """Drive ``persona`` through ``sequence`` on a fresh reactive ``TutorSession``.

    For each ``ProblemSpec`` in order:

      1. present a fresh seeded problem for the spec's KC + format (the tutor
         delegates to the Layer-1 generator — deterministic);
      2. ask the Layer-3 simulator for the persona's action under the spec's context;
      3. if the action submitted a numeric answer, drive it into the tutor's reactive
         turn loop (``submit_answer``), which verifies it, updates mastery, and
         applies the §3.6 policy between problems. The persona's think time becomes
         the turn latency (the engagement-floor signal, §3.4) and its hint request
         becomes the ``hint_used`` flag (the unscaffolded-attempt signal, §3.4
         rule 3);
      4. record the turn.

    A pure-EXPLAIN turn (no numeric submission) is recorded with no ``result`` /
    ``observation`` — it is a justification probe whose evidence is the action's
    ``can_justify``/``explanation``, read directly off the recorded turn; it does not
    produce a verifier verdict or a mastery observation.

    The session is constructed WITHOUT a cold-start route (``chosen_kc=None``) so the
    run is driven entirely by the explicit ``sequence`` — the cold-start calibration
    item is a separate concern (Slice 1.7) and would otherwise inject an unrequested
    first problem. The starting surface state is S1 (the tutor default).

    Returns a frozen ``PersonaRun``. Deterministic: same (persona, sequence) ⇒ same
    run (every underlying piece is deterministic; PROJECT.md §4.1).
    """
    session = TutorSession.cold_start(chosen_kc=None)
    starting_state = session.surface_state

    turns: list[PersonaTurn] = []
    states_visited: list[SurfaceState] = [starting_state]
    observations: list[Observation] = []

    for spec in sequence:
        problem = session.present_problem(
            kc=spec.kc, seed=spec.seed, surface_format=spec.surface_format
        )
        action = simulate_action(persona, problem, context=spec.context)

        result: TurnResult | None = None
        observation: Observation | None = None
        if action.submitted_answer is not None:
            result = session.submit_answer(
                action.submitted_answer,
                # think_time is in seconds (a float); the tutor/mastery model work in
                # integer milliseconds (the engagement floor is ENGAGEMENT_FLOOR_MS).
                latency_ms=int(action.think_time_seconds * 1000),
                hint_used=action.requested_hint,
            )
            # The observation the tutor just recorded is the last history entry.
            observation = session.history[-1].observation
            observations.append(observation)
            states_visited.append(session.surface_state)

        turns.append(
            PersonaTurn(
                problem=problem,
                context=spec.context,
                action=action,
                result=result,
                observation=observation,
            )
        )

    return PersonaRun(
        persona_id=persona.persona_id,
        turns=tuple(turns),
        states_visited=tuple(states_visited),
        observations=observations,
        final_state=session.surface_state,
    )


__all__ = [
    "PersonaRun",
    "PersonaTurn",
    "ProblemSpec",
    "run_persona",
]
