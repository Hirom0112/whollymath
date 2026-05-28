"""Behavioral tests for Click-through Cleo (PROJECT.md §4.2 Persona 5).

MANDATORY-TDD persona behavioral tests (CLAUDE.md §2). They pin Cleo's §4.2
signature — "submits answers in 1–2 seconds, often before reading; types the
shortest plausible answer; ignores hint screens" — where her failure is
ENGAGEMENT, not knowledge. The key, verifier-independent signal is that her
think time is below the mastery model's ENGAGEMENT_FLOOR_MS, so every turn is
flagged low-engagement and counts as non-evidence (§3.4, §4.2 P5). No LLM, no
DB, deterministic (§8.1, §8.3, §4.1).

Cleo forces the §3.4 engagement-floor rule: a sub-floor answer is flagged and
does not count as mastery evidence; if it counted, a lucky run of fast guesses
would falsely declare mastery (§4.2 P5).
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.domain.problem_generators import Problem, generate_problem
from app.mastery.mastery_model import ENGAGEMENT_FLOOR_MS, Observation
from app.personas.cleo import CLEO
from app.personas.simulator import simulate_action

_SEEDS = tuple(range(20))


def _addition(seed: int) -> Problem:
    return generate_problem(KnowledgeComponentId.ADDITION_UNLIKE, seed, Representation.SYMBOLIC)


def test_cleo_think_time_is_below_the_engagement_floor() -> None:
    """§4.2 P5: 'submits answers in 1–2 seconds.'

    Her think time (from ``response_latency_seconds``) is below the mastery model's
    ENGAGEMENT_FLOOR_MS, so any turn she takes is sub-floor — the engagement signal
    the §3.4 rule reads. Asserted in milliseconds against the model's own floor so
    the two cannot silently drift apart.
    """
    problem = _addition(1)
    action = simulate_action(CLEO, problem)

    think_time_ms = action.think_time_seconds * 1_000
    assert think_time_ms < ENGAGEMENT_FLOOR_MS


def test_cleo_turns_are_flagged_low_engagement_by_the_mastery_model() -> None:
    """The flag the mastery model actually reads: building an Observation from Cleo's
    turn, ``is_low_engagement()`` is True — so her evidence is non-evidence (§3.4,
    §4.2 P5). This is exactly what blocks a lucky-guess false-positive mastery."""
    for seed in _SEEDS:
        problem = _addition(seed)
        action = simulate_action(CLEO, problem)
        obs = Observation(
            kc=problem.kc,
            correct=False,  # correctness is irrelevant; the FLAG is the point
            representation=problem.surface_format,
            hinted=action.requested_hint,
            latency_ms=int(action.think_time_seconds * 1_000),
        )
        assert obs.is_low_engagement() is True


def test_cleo_does_not_genuinely_know_the_answer() -> None:
    """§4.2 P5: her failure is engagement, not knowledge — she cannot justify, and her
    low-effort guess is not a demonstration of understanding (``can_justify=False``)."""
    problem = _addition(1)
    action = simulate_action(CLEO, problem)
    assert action.can_justify is False


def test_cleo_low_hint_use_ignores_hints() -> None:
    """§4.2 P5: 'ignores hint screens.' Her hint-request probability is low, so she
    rarely (deterministically) asks for one — she is optimizing for 'done', not help."""
    assert CLEO.behavior.hint_request_probability <= 0.1


def test_cleo_is_deterministic() -> None:
    """Same persona + problem ⇒ identical action (§4.1; CLAUDE.md §2)."""
    problem = _addition(5)
    assert simulate_action(CLEO, problem) == simulate_action(CLEO, problem)
