"""Escalating hints on the live hint path (Feature B, Slice 5.6 → API).

A REQUEST_HINT turn escalates on REPEATED requests on the SAME problem. Since the owner change of
2026-06-09 ("a hint, not the answer choice") the FIRST hint is SPECIFIC to this problem but never
its answer — the worked example's opening SETUP step (``_first_problem_specific_hint``), or the
conceptual nudge as a fallback (a KC whose first step would BE the answer, e.g. number-line
placement, or a problem with no worked example). The 2nd+ request gives the full WORKED_STEP
walkthrough (its closing step states the answer). A hint turn never changes the surface state or
advances the problem (§3.8 refuse-rule 3). The counter resets when a submitted answer advances the
problem, so the first hint on a fresh problem is the problem-specific first hint again.

These run with NO providers wired, so they also prove the no-LLM fallback path: with
``hint_provider=None`` ``build_validated_hint`` returns the deterministic canonical text, so
escalation is real (just not LLM-warmed) in tests. SymPy decides every answer; no mocks.
"""

from __future__ import annotations

import re

from app.api.schemas import ActionType, SurfaceState, TurnRequest
from app.api.service import SessionStore, _first_problem_specific_hint
from app.domain.knowledge_components import KnowledgeComponentId
from app.tutor.hints import HintLevel, build_validated_hint, select_nudge
from app.tutor.worked_example import worked_example_for

_ROUTE = "combine"


def _hint_req(session_id: str, problem_id: str) -> TurnRequest:
    return TurnRequest(
        session_id=session_id,
        problem_id=problem_id,
        action=ActionType.REQUEST_HINT,
        surface_state=SurfaceState.SYMBOLIC_FOCUS,
        latency_ms=1000,
        hint_used=False,
    )


def _answer_req(session_id: str, problem_id: str, answer: str) -> TurnRequest:
    return TurnRequest(
        session_id=session_id,
        problem_id=problem_id,
        action=ActionType.SUBMIT_ANSWER,
        submitted_answer=answer,
        surface_state=SurfaceState.SYMBOLIC_FOCUS,
        latency_ms=3000,
        hint_used=False,
    )


def _has_digit(text: str) -> bool:
    return any(ch.isdigit() for ch in text)


def test_first_hint_is_problem_specific_then_worked_on_same_problem() -> None:
    """1st hint = the problem-specific FIRST hint (the worked example's opening SETUP step, which
    carries this problem's digits but NOT its answer), 2nd+ = the full WORKED_STEP walkthrough.
    Surface + problem stay put each time (a hint never advances, refuse-rule 3)."""
    store = SessionStore()  # no providers — proves the deterministic fallback
    started = store.start(_ROUTE)
    sid, pid = started.session_id, started.problem.problem_id
    problem = store._sessions[sid].tutor.current_problem  # noqa: SLF001 (test introspection)

    # 1st request → the problem-specific first hint (setup step). It is NOT the full worked
    # walkthrough, and it does not state the answer; surface/problem are unchanged.
    expected_first = _first_problem_specific_hint(problem, "en", None, None)
    expected_worked = build_validated_hint(problem, HintLevel.WORKED_STEP).natural_language
    r1 = store.process_turn(_hint_req(sid, pid))
    assert r1.hint == expected_first
    assert r1.hint != expected_worked  # the first hint is NOT the full (answer-stating) walkthrough
    answer = f"{problem.correct_value.p}/{problem.correct_value.q}"
    assert answer not in (r1.hint or "")  # a hint, not the answer
    assert r1.next_surface_state == started.surface_state
    assert r1.next_problem is not None and r1.next_problem.problem_id == pid

    # 2nd request → WORKED_STEP: the full numbered walkthrough, longer than the first hint.
    r2 = store.process_turn(_hint_req(sid, pid))
    assert r2.hint == expected_worked
    assert _has_digit(r2.hint or "")
    assert len(r2.hint or "") > len(r1.hint or "")
    assert r2.next_surface_state == started.surface_state
    assert r2.next_problem is not None and r2.next_problem.problem_id == pid

    # 3rd request → still WORKED_STEP (2+ stays at the full walkthrough).
    r3 = store.process_turn(_hint_req(sid, pid))
    assert r3.hint == expected_worked
    assert r3.next_surface_state == started.surface_state


def test_fourth_and_later_requests_stay_at_worked_step() -> None:
    """2+ ⇒ WORKED_STEP: a 4th request on the same problem still returns the full walkthrough."""
    store = SessionStore()
    started = store.start(_ROUTE)
    sid, pid = started.session_id, started.problem.problem_id
    problem = store._sessions[sid].tutor.current_problem  # noqa: SLF001
    expected_worked = build_validated_hint(problem, HintLevel.WORKED_STEP).natural_language
    for _ in range(3):
        store.process_turn(_hint_req(sid, pid))
    r4 = store.process_turn(_hint_req(sid, pid))
    assert r4.hint == expected_worked


def test_counter_resets_when_an_answer_advances_the_problem() -> None:
    """After a submitted answer serves a fresh problem, the first hint is the problem-specific
    first hint again (counter reset) — NOT the escalated worked walkthrough carried over."""
    store = SessionStore()
    started = store.start(_ROUTE)
    sid, pid = started.session_id, started.problem.problem_id

    # Escalate twice on the calibration problem (so the counter is at 2).
    store.process_turn(_hint_req(sid, pid))
    store.process_turn(_hint_req(sid, pid))

    # Submit a (wrong) answer to advance to a fresh practice problem.
    answered = store.process_turn(_answer_req(sid, pid, "0/1"))
    assert answered.next_problem is not None
    new_pid = answered.next_problem.problem_id
    new_problem = store._sessions[sid].tutor.current_problem  # noqa: SLF001 (test introspection)

    # First hint on the fresh problem is the problem-specific first hint again (counter reset),
    # not the full worked walkthrough that the previous problem had escalated to.
    r = store.process_turn(_hint_req(sid, new_pid))
    assert r.hint == _first_problem_specific_hint(new_problem, "en", None, None)
    assert r.hint != build_validated_hint(new_problem, HintLevel.WORKED_STEP).natural_language


def test_serving_a_fresh_problem_always_resets_the_hint_counter() -> None:
    """The per-problem hint counter is reset at the single chokepoint that serves a fresh
    practice problem (``_serve_next``), so EVERY re-serve path resets — including the
    probe-fail and probe-pass re-serves, which previously skipped it and let the next
    problem's FIRST hint jump straight to a worked step instead of a nudge.
    """
    from app.api.service import _serve_next  # noqa: PLC0415

    store = SessionStore()
    started = store.start(_ROUTE)
    sid, pid = started.session_id, started.problem.problem_id
    # Advance one turn so history has an answered turn for the scheduler to read.
    store.process_turn(_answer_req(sid, pid, "0/1"))
    live = store._sessions[sid]  # noqa: SLF001 (test introspection)

    live.hints_this_problem = 3  # as if three hints were taken on the current problem
    _serve_next(live)  # the chokepoint the probe-fail/-pass and remediation paths all call
    assert live.hints_this_problem == 0


def test_first_and_worked_use_deterministic_canonical_text_without_a_provider() -> None:
    """With no providers wired, the hints ARE the deterministic canonical worked text.

    Proves the no-LLM fallback path is what backs the live escalation in tests: the FIRST hint
    equals the first canonical step's ``shown`` (the setup step, for this combine problem which has
    a worked example), and the 2nd hint equals the full numbered walkthrough — both straight from
    ``worked_example_for`` (the domain authority)."""
    store = SessionStore()
    started = store.start(_ROUTE)
    sid, pid = started.session_id, started.problem.problem_id
    problem = store._sessions[sid].tutor.current_problem  # noqa: SLF001
    steps = worked_example_for(problem).steps

    r_first = store.process_turn(_hint_req(sid, pid))
    assert r_first.hint == steps[0].shown  # the opening SETUP step, not the answer

    r_worked = store.process_turn(_hint_req(sid, pid))
    expected = "\n".join(f"{i}. {step.shown}" for i, step in enumerate(steps, start=1))
    assert r_worked.hint == expected
    # The numbered worked walkthrough has at least as many lines as canonical steps.
    assert len(re.findall(r"^\d+\.", r_worked.hint or "", flags=re.MULTILINE)) == len(steps)


def test_number_line_first_hint_is_the_nudge_not_the_answer_revealing_step() -> None:
    """NUMBER_LINE_PLACEMENT is the one KC whose worked example's FIRST step IS the answer (it
    places the target fraction on the line). Its first hint must therefore stay the conceptual
    nudge, never that answer-revealing step — the guard that keeps "specific first hint" honest."""
    from app.domain.problem_generators import generate_problem  # noqa: PLC0415

    for seed in range(6):  # a few distinct targets, not one lucky problem
        problem = generate_problem(KnowledgeComponentId.NUMBER_LINE_PLACEMENT, seed=seed)
        first = _first_problem_specific_hint(problem, "en", None, None)
        # The first hint is the conceptual nudge, NOT the answer-stating first worked step.
        assert first == select_nudge(problem.kc).text
        answer = f"{problem.correct_value.p}/{problem.correct_value.q}"
        assert answer not in first
        assert first != worked_example_for(problem).steps[0].shown
