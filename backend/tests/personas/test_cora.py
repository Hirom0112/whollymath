"""Tests pinning Capable Cora — the competent positive-control persona.

Cora is the sixth persona: the genuinely-competent learner the other five
deliberately are NOT. The five committed personas (PROJECT.md §4.2) are negative
controls, each deficient in one way (procedure-only, format-tied, nat-number bias,
hint-dependent, click-through) — so NONE of them has ``KnowledgeMode.BOTH`` and none
can pass the S5 transfer probe. Cora is the positive control the harness's §4.1
extensibility anticipates ("adding a sixth persona is editing a config"): she holds
genuine conceptual+procedural understanding of the five fraction-foundation KCs, so
she answers correctly across representations, can justify, catches error-finding
items, and therefore CONFIRMS mastery — which is what gives the demo dashboard a
real "on-track, mastered" student instead of an all-0% class.

Two layers of test, as with the other personas:
  - config (DATA): she is BOTH-mode on every live fraction KC, carries no
    misconception, and is a low-hint / high-engagement worker (CLAUDE.md §2 — the
    config is pinned).
  - behavior (the point of a positive control): driven through the REAL turn loop she
    actually CONFIRMS mastery (lesson_complete), unlike the five negative controls.
"""

from __future__ import annotations

from app.api.schemas import ActionType, TurnRequest
from app.api.service import SessionStore
from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId
from app.domain.misconceptions import MISCONCEPTION_REGISTRY
from app.personas.cora import CORA
from app.personas.persona_config import KnowledgeMode
from app.personas.registry import get_persona
from app.personas.simulator import simulate_action


def test_cora_holds_every_live_fraction_kc_in_both_mode() -> None:
    """The positive control: genuine concept+procedure (BOTH) on all five live KCs."""
    for kc_id in LIVE_KCS:
        assert CORA.mode_for(kc_id) is KnowledgeMode.BOTH


def test_cora_carries_no_misconception() -> None:
    """A competent learner holds no misconception — she is the clean control."""
    assert CORA.misconceptions == ()


def test_cora_is_self_sufficient_and_engaged() -> None:
    """She needs no scaffold, so she rarely hints — which is how she earns UNSCAFFOLDED correct."""
    assert CORA.behavior.hint_request_probability <= 0.1
    assert CORA.behavior.engagement_floor >= 0.7
    assert CORA.behavior.scaffold_dependence_rate <= 0.2


def test_cora_references_only_real_kc_ids() -> None:
    """Cora's config names only real Layer-1 KC ids (the single-source-of-truth invariant)."""
    for kc_id in CORA.knowledge:
        assert isinstance(kc_id, KnowledgeComponentId)
    for misconception_id in CORA.misconceptions:
        assert MISCONCEPTION_REGISTRY.get(misconception_id).id is misconception_id


def test_cora_is_registered() -> None:
    """She is resolvable through the registry (added to the roster, not orphaned)."""
    assert get_persona("capable_cora") is CORA


def test_cora_confirms_mastery_through_the_real_turn_loop() -> None:
    """THE positive control: driven through the live turn loop, Cora CONFIRMS mastery.

    This is what distinguishes her from the five negative controls — every one of them
    fails the S5 transfer probe and never confirms. Cora, holding genuine understanding,
    answers correctly across representations and passes the probe, so a ``lesson_complete``
    turn must occur. We drive her exactly as the data runner does (no persistence needed
    here), reading the live problem and feeding the simulator's action back through
    ``process_turn``.
    """
    store = SessionStore()  # in-memory; we are asserting the behavioral verdict, not rows
    started = store.start("combine", session_id="cora-confirms-mastery")
    surface_state = started.surface_state
    confirmed = False
    for _ in range(40):
        problem = store.current_problem(started.session_id)
        assert problem is not None
        action = simulate_action(CORA, problem)
        answer = "" if action.submitted_answer is None else str(action.submitted_answer)
        response = store.process_turn(
            TurnRequest(
                session_id=started.session_id,
                problem_id=problem.problem_id,
                action=ActionType.SUBMIT_ANSWER,
                submitted_answer=answer,
                surface_state=surface_state,
                latency_ms=int(action.think_time_seconds * 1000),
                hint_used=action.requested_hint,
            )
        )
        if response.lesson_complete:
            confirmed = True
            break
        assert response.next_problem is not None
        surface_state = response.next_surface_state

    assert confirmed, "Capable Cora must CONFIRM mastery — she is the positive control"
