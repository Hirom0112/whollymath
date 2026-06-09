"""Hints on the live hint path: SHORT nudges that NEVER reveal the answer (owner 2026-06-09).

A REQUEST_HINT turn never advances the problem or changes the surface state (§3.8 refuse-rule 3).
Each request returns ONE short line, and the sequence NEVER states the final answer however many
times it is clicked:

  - The Nth hint is the Nth answer-free SETUP step of the worked example
    (``_answer_free_step_lines`` — the leading steps before any that writes the answer; specific to
    this problem's real numbers, but not the result).
  - Once those setup steps are exhausted (or there were none — e.g. number-line placement, whose
    first step IS the answer), it STAYS on the conceptual nudge, which is answer-free by
    construction. So repeated clicks keep nudging and never escalate to the answer.

These run with NO providers wired, so the lines are the deterministic canonical text (es-MX
translation is a separate, provider-only path). SymPy decides every answer; no mocks.
"""

from __future__ import annotations

from app.api.schemas import ActionType, SurfaceState, TurnRequest
from app.api.service import SessionStore, _answer_free_step_lines
from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.problem_generators import generate_problem
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for

# A KC whose generated problems have a multi-step worked example with answer-free setup steps.
_KC = KnowledgeComponentId.ADDITION_UNLIKE


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


def _answer_str(problem_kc: KnowledgeComponentId, problem) -> str:  # type: ignore[no-untyped-def]
    a = problem.correct_value
    return f"{a.p}/{a.q}"


# ─── _answer_free_step_lines: leading setup steps, never the answer ───────────


def test_answer_free_step_lines_are_leading_steps_without_the_answer() -> None:
    """The helper returns the worked example's leading steps, stopping before any that states the
    answer — so no returned line contains the answer fraction, across many generated problems."""
    for seed in range(8):
        problem = generate_problem(_KC, seed=seed)
        lines = _answer_free_step_lines(problem)
        steps = worked_example_for(problem).steps
        answer = f"{problem.correct_value.p}/{problem.correct_value.q}"
        # They are a PREFIX of the worked steps' shown text...
        assert lines == [s.shown for s in steps[: len(lines)]]
        # ...and not one of them writes the answer.
        assert all(answer not in line for line in lines)
        # The NEXT step (the first omitted one) is the one that reveals the answer.
        if len(lines) < len(steps):
            revealing = steps[len(lines)]
            assert revealing.revealed_value == problem.correct_value or answer in revealing.shown


def test_number_line_has_no_answer_free_setup_step() -> None:
    """NUMBER_LINE_PLACEMENT's only worked step IS the answer (it places the target fraction), so it
    has no answer-free setup step — hints fall back to the conceptual nudge."""
    for seed in range(5):
        problem = generate_problem(KnowledgeComponentId.NUMBER_LINE_PLACEMENT, seed=seed)
        assert _answer_free_step_lines(problem) == []


# ─── live hint escalation: setup steps → nudge, never the answer ──────────────


def test_hints_walk_setup_steps_then_stay_on_nudge_never_the_answer() -> None:
    """Each hint is the next answer-free setup step; once exhausted it STAYS on the conceptual
    nudge. No hint ever states the answer, and the surface/problem never change."""
    store = SessionStore()  # no providers → canonical text
    started = store.start_kc(_KC)
    sid, pid = started.session_id, started.problem.problem_id
    problem = store._sessions[sid].tutor.current_problem  # noqa: SLF001 (test introspection)
    setup = _answer_free_step_lines(problem)
    assert setup, "this KC's generated problem should have answer-free setup steps"
    nudge = select_nudge(problem.kc).text
    answer = _answer_str(problem.kc, problem)

    # Walk the setup steps in order — short, specific, never the answer; problem/surface unchanged.
    for expected in setup:
        r = store.process_turn(_hint_req(sid, pid))
        assert r.hint == expected
        assert answer not in (r.hint or "")
        assert r.next_surface_state == started.surface_state
        assert r.next_problem is not None and r.next_problem.problem_id == pid

    # Exhausted → stays on the conceptual nudge however many more times it is asked. Never escalates
    # to the answer (the whole point of the 2026-06-09 change).
    for _ in range(4):
        r = store.process_turn(_hint_req(sid, pid))
        assert r.hint == nudge
        assert answer not in (r.hint or "")
        assert r.next_surface_state == started.surface_state


def test_number_line_hints_are_the_nudge_and_never_the_answer() -> None:
    """A number-line problem (no answer-free setup step) hints the conceptual nudge from the very
    first request, and never the answer fraction."""
    store = SessionStore()
    started = store.start_kc(KnowledgeComponentId.NUMBER_LINE_PLACEMENT)
    sid, pid = started.session_id, started.problem.problem_id
    problem = store._sessions[sid].tutor.current_problem  # noqa: SLF001
    nudge = select_nudge(problem.kc).text
    answer = _answer_str(problem.kc, problem)

    for _ in range(3):
        r = store.process_turn(_hint_req(sid, pid))
        assert r.hint == nudge
        assert answer not in (r.hint or "")


def test_counter_resets_when_an_answer_advances_the_problem() -> None:
    """After a submitted answer serves a fresh problem, the first hint is that problem's first
    answer-free setup step again (counter reset) — not a carried-over deeper line."""
    store = SessionStore()
    started = store.start_kc(_KC)
    sid, pid = started.session_id, started.problem.problem_id

    # Take a couple of hints on the first problem (advance the counter).
    store.process_turn(_hint_req(sid, pid))
    store.process_turn(_hint_req(sid, pid))

    # Submit a (wrong) answer to advance to a fresh problem.
    answered = store.process_turn(_answer_req(sid, pid, "0/1"))
    assert answered.next_problem is not None
    new_pid = answered.next_problem.problem_id
    new_problem = store._sessions[sid].tutor.current_problem  # noqa: SLF001
    new_setup = _answer_free_step_lines(new_problem)
    expected_first = new_setup[0] if new_setup else select_nudge(new_problem.kc).text

    r = store.process_turn(_hint_req(sid, new_pid))
    assert r.hint == expected_first


def test_serving_a_fresh_problem_always_resets_the_hint_counter() -> None:
    """The per-problem hint counter is reset at the single chokepoint that serves a fresh practice
    problem (``_serve_next``), so EVERY re-serve path resets — including the probe-fail and
    probe-pass re-serves, which previously skipped it and let the next problem's first hint jump
    straight past the setup step.
    """
    from app.api.service import _serve_next  # noqa: PLC0415

    store = SessionStore()
    started = store.start_kc(_KC)
    sid, pid = started.session_id, started.problem.problem_id
    store.process_turn(_answer_req(sid, pid, "0/1"))
    live = store._sessions[sid]  # noqa: SLF001 (test introspection)

    live.hints_this_problem = 3  # as if three hints were taken on the current problem
    _serve_next(live)  # the chokepoint the probe-fail/-pass and remediation paths all call
    assert live.hints_this_problem == 0
