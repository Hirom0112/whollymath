"""P0.6 red-team persona — the fluent-procedure / missing-a-foundation learner (§11.6 item 3).

CURRICULUM_STANDARD.md §11.6 item 3 and CLAUDE.md §9 call for a red-team persona to verify the
reactive-remediation feature end-to-end: a learner who LOOKS fluent at a grade-level procedure but
is missing the foundation it rests on must (a) trip the §11.2 gate on the grade-level lesson, (b)
route to the CORRECT prerequisite (§11.1/§11.3), (c) be HARD-GATED out of the parent until the
prerequisite is mastered (§11.4), and (d) RESUME the parent where they paused. This is the
integration test for the whole router — the analogue of the Sam/Priya persona suite (CLAUDE.md §9).

"Foundation Fiona" is that learner, expressed behaviorally against the REAL live loop
(``SessionStore``, the same path production runs): she struggles on KC_divide_fractions (the missing
foundation surfaces as wrong answers), the router drops her to the foundation prerequisite, she then
works the foundation correctly (the focused practice the foundation needs), masters it, and is
returned to divide-fractions where she paused. SymPy decides every answer; the HelpNeed stream is
driven by a deterministic stub (P = recent error rate) because the committed artifact is stale-
width during the T2 re-fit window (``_artifact_skip``) and the router reads the gate, not the model
(§8.1). No LLM, no mocks of the loop.
"""

from __future__ import annotations

from app.api.schemas import ActionType, ProblemView, SurfaceState, TurnRequest, TurnResponse
from app.api.service import SessionStore
from app.domain.knowledge_components import KnowledgeComponentId

from tests.api.test_remediation_router_live import make_remediation_store
from tests.api.test_transfer_probe_live import _correct_answer

# Fiona attempts the grade-6 divide-fractions lesson; its foundations are add/subtract + equivalence
# (§11.1). An OPERATION slip (the arithmetic procedure breaking) biases the §11.3 drop toward the
# operation-flavored foundation — add/subtract — and ties break to addition (the listing order).
_PARENT_KC = KnowledgeComponentId.DIVIDE_FRACTIONS
_EXPECTED_PREREQ = KnowledgeComponentId.ADDITION_UNLIKE

_WRONG = "1/9"


def _answer(session_id: str, problem_id: str, answer: str) -> TurnRequest:
    return TurnRequest(
        session_id=session_id,
        problem_id=problem_id,
        action=ActionType.SUBMIT_ANSWER,
        submitted_answer=answer,
        surface_state=SurfaceState.SYMBOLIC_FOCUS,
        latency_ms=3000,
        hint_used=False,
    )


def _struggle_until_dropped(store: SessionStore, sid: str, pid: str) -> TurnResponse:
    """Fiona answers the grade-level lesson WRONG until the router drops her; returns the drop."""
    for _ in range(10):
        resp = store.process_turn(_answer(sid, pid, _WRONG))
        if resp.remediation is not None:
            return resp
        assert resp.next_problem is not None
        pid = resp.next_problem.problem_id
    raise AssertionError("the gate never dropped Fiona into remediation")


def _master_prereq_and_resume(
    store: SessionStore, sid: str, first_prereq_problem: ProblemView
) -> TurnResponse:
    """Fiona works the PREREQUISITE correctly through its lesson + probe; returns the resume turn.

    Asserts the hard gate the whole way: until the prereq confirms, the parent is never served.
    """
    problem = first_prereq_problem
    for _ in range(60):
        answer = _correct_answer(problem.model_dump(mode="json"))
        resp = store.process_turn(_answer(sid, problem.problem_id, answer))
        if resp.remediation is None:
            return resp  # gate cleared — Fiona resumed the parent
        assert resp.next_problem is not None
        # HARD GATE (§11.4): she cannot get back to divide-fractions until the foundation masters.
        assert resp.next_problem.kc is _EXPECTED_PREREQ
        problem = resp.next_problem
    raise AssertionError("the prerequisite never cleared — Fiona never resumed the parent")


def test_fiona_is_routed_hardgated_and_resumed() -> None:
    """The full §11 red-team story for Foundation Fiona, end-to-end through the real live loop.

    (a) sustained struggle on divide-fractions trips the §11.2 gate and drops her; (b) to the
    CORRECT one-level-down prereq (§11.1/§11.3 — the operation-flavored foundation); (c) she is
    hard-gated in the prerequisite until she masters it (§11.4, asserted inside the driver); (d) she
    resumes the divide-fractions lesson at the index it paused on (§11.4 pauses, never resets).
    """
    store = make_remediation_store()
    started = store.start_kc(_PARENT_KC)
    sid = started.session_id

    # (a) + (b): struggle → drop to the correct prerequisite, one level down.
    drop = _struggle_until_dropped(store, sid, started.problem.problem_id)
    assert drop.remediation is not None
    assert drop.remediation.parent_kc == _PARENT_KC.value
    assert drop.remediation.prerequisite_kc == _EXPECTED_PREREQ.value
    paused_index = drop.remediation.parent_progress_done
    assert paused_index > 0, "the parent must pause with progress, not reset (§11.4)"
    assert drop.next_problem is not None and drop.next_problem.kc is _EXPECTED_PREREQ

    # (c) + (d): master the foundation (hard gate asserted in the driver), then resume the parent.
    resumed = _master_prereq_and_resume(store, sid, drop.next_problem)
    assert resumed.remediation is None, "the panel must clear once the foundation is mastered"
    assert resumed.next_problem is not None
    assert resumed.next_problem.kc is _PARENT_KC, "Fiona must resume the divide-fractions lesson"


def test_fiona_does_not_rabbit_hole_below_the_foundation() -> None:
    """§11.1 (no nested drop): even if Fiona keeps failing INSIDE the foundation, she stays there.

    A struggling learner inside the prereq works it — she is never dropped a second level to a
    prereq-of-the-prereq (foundations are terminal). The panel stays pinned to the same prereq.
    """
    store = make_remediation_store()
    started = store.start_kc(_PARENT_KC)
    sid = started.session_id
    drop = _struggle_until_dropped(store, sid, started.problem.problem_id)
    assert drop.remediation is not None and drop.next_problem is not None

    pid = drop.next_problem.problem_id
    for _ in range(6):  # keep failing inside the foundation
        resp = store.process_turn(_answer(sid, pid, _WRONG))
        assert resp.remediation is not None, "must stay in remediation (no silent exit)"
        assert resp.remediation.prerequisite_kc == _EXPECTED_PREREQ.value, "one level only (§11.1)"
        assert resp.next_problem is not None and resp.next_problem.kc is _EXPECTED_PREREQ
        pid = resp.next_problem.problem_id
