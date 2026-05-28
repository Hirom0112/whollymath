"""Behavioral tests for Hint-hunter Hugo (PROJECT.md §4.2 Persona 3).

MANDATORY-TDD persona behavioral tests (CLAUDE.md §2). They pin Hugo's §4.2
signature — "requests hints within seconds, before attempting; executes hints
mechanically without generalizing; hint dependence rate stays >70%; struggles
when hints are unavailable" — and assert correctness through the tutor's own
SymPy verifier (``domain/verifier.py``, ARCHITECTURE.md §9). No LLM, no DB,
deterministic (§8.1, §8.3, §4.1).

Hugo forces the §3.4 rule-3 gate: mastery requires >= 1 UNSCAFFOLDED correct
attempt. Because every correct answer Hugo produces is HINTED (correct only WITH
a hint, wrong without), he can never satisfy that gate — exactly the false
positive the rule blocks (§4.2 P3 "succeed only while the UI is doing the
reasoning for them").
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.domain.problem_generators import Problem, generate_problem
from app.domain.verifier import verify
from app.personas.hugo import HUGO
from app.personas.simulator import simulate_action

# A spread of seeds gives a spread of distinct, deterministic problems, so the
# >70% hint-rate assertion is measured over many items (not one lucky draw).
_SEEDS = tuple(range(60))


def _addition(seed: int) -> Problem:
    return generate_problem(KnowledgeComponentId.ADDITION_UNLIKE, seed, Representation.SYMBOLIC)


def test_hugo_requests_hints_at_a_high_rate() -> None:
    """§4.2 P3: 'hint dependence rate stays >70%.'

    Measured over many distinct problems, the fraction of turns on which Hugo
    requests a hint exceeds 0.70 — his defining over-scaffolding signature, and a
    config-level (>0.70 hint_request_probability) fact, not an LLM emergent one.
    """
    assert HUGO.behavior.hint_request_probability > 0.70

    hint_turns = sum(1 for seed in _SEEDS if simulate_action(HUGO, _addition(seed)).requested_hint)
    assert hint_turns / len(_SEEDS) > 0.70


def test_hugo_is_correct_only_with_a_hint_never_without() -> None:
    """§4.2 P3: 'executes hints mechanically' / 'struggles when hints are unavailable.'

    The load-bearing invariant: across every problem, a CORRECT answer is ALWAYS a
    hinted one, and an UNHINTED turn is ALWAYS wrong. Hugo never produces an
    unscaffolded correct — which is precisely why he can never satisfy the §3.4
    rule-3 (>= 1 unscaffolded correct) mastery gate.
    """
    saw_hinted_correct = False
    saw_unhinted_wrong = False

    for seed in _SEEDS:
        problem = _addition(seed)
        action = simulate_action(HUGO, problem)
        correct = verify(problem, action.submitted_answer).is_correct

        if correct:
            # Every correct answer must have been produced WITH a hint (mechanically).
            assert action.requested_hint is True, "Hugo is never correct without a hint"
            saw_hinted_correct = True
        if not action.requested_hint:
            # Without the scaffold he collapses (the verifier marks it wrong).
            assert correct is False, "Hugo must be wrong on any unscaffolded attempt"
            saw_unhinted_wrong = True

    # Both branches must actually occur in the seed range, or the test proves nothing.
    assert saw_hinted_correct, "expected at least one hinted-correct turn"
    assert saw_unhinted_wrong, "expected at least one unhinted-wrong turn"


def test_hugo_hinted_correct_carries_the_hinted_flag() -> None:
    """A correct Hugo turn is flagged ``requested_hint=True`` so the mastery model
    downweights it (HINTED_CORRECT_WEIGHT) AND excludes it from the unscaffolded-
    correct gate — the evidence shape §3.4 rule 3 reads."""
    # Find the first seed on which Hugo answers correctly; it must be hinted.
    for seed in _SEEDS:
        problem = _addition(seed)
        action = simulate_action(HUGO, problem)
        if verify(problem, action.submitted_answer).is_correct:
            assert action.requested_hint is True
            break
    else:  # pragma: no cover - defensive: the seed range always contains a hinted turn
        raise AssertionError("expected at least one correct (hinted) Hugo turn in the seed range")


def test_hugo_is_deterministic() -> None:
    """Same persona + problem ⇒ identical action (§4.1; CLAUDE.md §2)."""
    problem = _addition(3)
    assert simulate_action(HUGO, problem) == simulate_action(HUGO, problem)
