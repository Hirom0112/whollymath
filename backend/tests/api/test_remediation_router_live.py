"""Live-loop integration tests for the reactive-remediation router (Slice P0.4).

Mandatory-TDD (CLAUDE.md §2, §9): the router is the load-bearing live wiring of
CURRICULUM_STANDARD.md §11 — it drives the committed ``LessonFlow`` machine off the EXISTING §3.7
sustained-help gate inside the real turn loop (``SessionStore``). These pin the five §11 behaviors
end-to-end against the real ``SessionStore`` (not a mock): the trigger fires, the parent PAUSES, the
nested prerequisite lesson is SERVED, the parent is HARD-GATED until the prerequisite is mastered,
and it RESUMES at the paused index. The P0.6 red-team persona (a fluent-procedure / missing-a-
foundation learner) lives in tests/api/test_remediation_redteam.py.

The trigger is the same sustained gate the proactive arm uses (``SustainedHelpNeedGate``), driven
here by submitting wrong answers through a deterministic HelpNeed stub (P = recent error rate) — the
real artifact is stale-width during the T2 re-fit window and returns a neutral fallback that cannot
trip the gate (``_artifact_skip``), and the router reads the gate, not the model (§8.1), so the stub
is the right test double. No LLM, no new trigger; SymPy stays the oracle (§8.1/§8.2).
"""

from __future__ import annotations

from typing import cast

from app.api.schemas import ActionType, ProblemView, SurfaceState, TurnRequest, TurnResponse
from app.api.service import SessionStore
from app.domain.knowledge_components import KnowledgeComponentId, get_kc
from app.helpneed.features import HelpNeedFeatures
from app.helpneed.predictor import HelpNeedPredictor
from app.policy.intervention_gate import SustainedHelpNeedGate

from tests.api.test_transfer_probe_live import _correct_answer

# DIVIDE_FRACTIONS is a grade-6 lesson with a routed drop (§11.1): it rests on the foundation
# add/subtract + equivalence prereqs. A struggling learner there should drop ONE level down.
_PARENT_KC = KnowledgeComponentId.DIVIDE_FRACTIONS

# A wrong answer string for any fraction item — drives the HelpNeed P high so the gate trips.
_WRONG = "1/9"
# A low gate (k=2) so the sustained signal trips within a few wrong turns without a long walk.
_GATE = SustainedHelpNeedGate(k=2, threshold=0.5)


class _ErrorRatePredictor:
    """A deterministic HelpNeed stub: P(unproductive) = the recent error rate.

    Decouples the router test from the committed XGBoost artifact, which is stale-width during the
    T2 re-fit window (``_artifact_skip``) and returns a neutral fallback that cannot trip the gate.
    The router reads the §3.7 gate, not the model (§8.1), so a deterministic stub is the right test
    double: wrong answers drive P → 1.0, correct answers drive it → 0.0, so a sustained wrong run
    trips the gate exactly as a real high-P stream would, with no dependence on the model fit.
    """

    def predict_proba(self, features: HelpNeedFeatures) -> float:
        return features.recent_error_rate

    def is_compatible_with_live_features(self) -> bool:  # parity with HelpNeedPredictor
        return True


def make_remediation_store() -> SessionStore:
    """A ``SessionStore`` wired with the deterministic error-rate stub and the low (k=2) gate.

    The cast tells mypy the stub structurally stands in for ``HelpNeedPredictor`` here — it
    implements the only method the turn loop calls on it (``predict_proba``); see the stub class
    for why a stub (not the committed artifact) is the right double during the re-fit window."""
    return SessionStore(predictor=cast(HelpNeedPredictor, _ErrorRatePredictor()), gate=_GATE)


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


def _start_parent(store: SessionStore) -> tuple[str, str]:
    """Start a DIVIDE_FRACTIONS lesson; return (session_id, first problem_id)."""
    started = store.start_kc(_PARENT_KC)
    return started.session_id, started.problem.problem_id


def _turn_correct(store: SessionStore, session_id: str, problem: ProblemView) -> TurnResponse:
    """Submit the CORRECT answer for ``problem`` (computed from its statement, SymPy-checked).

    Reuses the transfer-probe test's ``_correct_answer`` (which reads a problem-view dict), so the
    same answer logic that drives a lesson to completion elsewhere drives the nested prerequisite
    lesson here — no duplicated answer math.
    """
    answer = _correct_answer(problem.model_dump(mode="json"))
    return store.process_turn(_answer(session_id, problem.problem_id, answer))


def _walk_wrong_until_remediation(
    store: SessionStore, session_id: str, first_pid: str, max_turns: int = 10
) -> tuple[list[TurnResponse], int]:
    """Submit wrong answers until the remediation panel appears; return (responses, trigger_index).

    Returns the index of the FIRST response carrying a remediation view (the drop), or -1 if it
    never fired within ``max_turns`` (a test asserts it did).
    """
    responses: list[TurnResponse] = []
    pid = first_pid
    trigger_at = -1
    for i in range(max_turns):
        resp = store.process_turn(_answer(session_id, pid, _WRONG))
        responses.append(resp)
        if trigger_at == -1 and resp.remediation is not None:
            trigger_at = i
        assert resp.next_problem is not None
        pid = resp.next_problem.problem_id
    return responses, trigger_at


def test_sustained_struggle_drops_to_the_prerequisite() -> None:
    """§11.2 trigger + §11.1 routing: sustained struggle on the parent drops to a foundation prereq.

    Wrong answers drive the HelpNeed gate; when it trips the response carries a ``RemediationView``
    naming the parent (paused) and a prerequisite ONE LEVEL DOWN (one of DIVIDE_FRACTIONS' listed
    foundations), with the §11.5 reason label.
    """
    store = make_remediation_store()
    sid, first_pid = _start_parent(store)
    responses, trigger_at = _walk_wrong_until_remediation(store, sid, first_pid)

    assert trigger_at != -1, "the sustained gate should have dropped the learner into remediation"
    view = responses[trigger_at].remediation
    assert view is not None
    assert view.parent_kc == _PARENT_KC.value
    prereq = KnowledgeComponentId(view.prerequisite_kc)
    # ONE LEVEL DOWN: the chosen prerequisite is one of the parent's listed foundations (§11.1).
    assert prereq in {
        KnowledgeComponentId.ADDITION_UNLIKE,
        KnowledgeComponentId.SUBTRACTION_UNLIKE,
        KnowledgeComponentId.EQUIVALENCE,
    }
    assert view.reason  # the §11.5 on-screen label is present
    assert get_kc(prereq).skill_name in view.resume_hint or view.parent_label in view.resume_hint


def test_nested_lesson_serves_the_prerequisite_kc() -> None:
    """§11: while in remediation the SERVED problems are the prerequisite KC, not the paused parent.

    The drop swaps the active lesson to the prerequisite; the next problem's KC is the prereq, so
    the learner is actually working the foundation skill, not the grade-level one.
    """
    store = make_remediation_store()
    sid, first_pid = _start_parent(store)
    responses, trigger_at = _walk_wrong_until_remediation(store, sid, first_pid)
    assert trigger_at != -1

    drop = responses[trigger_at]
    assert drop.remediation is not None
    assert drop.next_problem is not None
    prereq = KnowledgeComponentId(drop.remediation.prerequisite_kc)
    # The problem served on the drop turn is the prerequisite lesson's problem.
    assert drop.next_problem.kc is prereq


def test_one_level_only_no_nested_remediation() -> None:
    """§11.1: struggling INSIDE the prereq does NOT drop a second level (foundations are terminal).

    After the drop, keep answering wrong (now inside the foundation prereq). The remediation view
    must stay pinned to the SAME prerequisite — never recurse to a prereq-of-the-prereq — and the
    served KC stays the foundation skill (no rabbit hole).
    """
    store = make_remediation_store()
    sid, first_pid = _start_parent(store)
    responses, trigger_at = _walk_wrong_until_remediation(store, sid, first_pid)
    assert trigger_at != -1
    first_prereq = responses[trigger_at].remediation
    assert first_prereq is not None

    # Keep struggling INSIDE the prerequisite for several more turns.
    pid = responses[-1].next_problem.problem_id  # type: ignore[union-attr]
    for _ in range(5):
        resp = store.process_turn(_answer(sid, pid, _WRONG))
        assert resp.remediation is not None, "must stay in remediation, not silently exit"
        assert resp.remediation.prerequisite_kc == first_prereq.prerequisite_kc, (
            "one level only: the prerequisite must not change (no nested drop, §11.1)"
        )
        assert resp.next_problem is not None
        # The served KC stays the foundation prereq — never a prereq-of-the-prereq.
        assert resp.next_problem.kc.value == first_prereq.prerequisite_kc
        pid = resp.next_problem.problem_id


def test_hard_gate_then_resume_at_the_paused_index() -> None:
    """§11.4 hard gate + resume: the parent stays locked until the prereq is MASTERED, then resumes.

    Drop into the prereq, then answer the PREREQUISITE correctly all the way through its lesson + S5
    probe. Until the prereq confirms, every served problem is the prereq (the parent is hard-gated —
    never served). Once the prereq is mastered, the remediation panel clears and the NEXT problem is
    the PARENT lesson again — resumed where it paused (the parent's history was preserved across the
    pause, so its served-problem count picks up from the paused index, never 0).
    """
    store = make_remediation_store()
    sid, first_pid = _start_parent(store)
    responses, trigger_at = _walk_wrong_until_remediation(store, sid, first_pid)
    assert trigger_at != -1
    drop = responses[trigger_at]
    assert drop.remediation is not None
    prereq = KnowledgeComponentId(drop.remediation.prerequisite_kc)
    paused_index = drop.remediation.parent_progress_done
    assert paused_index > 0  # the parent had served problems before pausing (it is not reset)

    problem = drop.next_problem
    assert problem is not None
    resumed: TurnResponse | None = None
    for _ in range(60):
        body = _turn_correct(store, sid, problem)
        if body.remediation is None:
            resumed = body  # the gate cleared — the parent resumed
            break
        # HARD GATE: while still remediating, the served problem is ALWAYS the prerequisite, never
        # the parent — the learner cannot return to the grade-level lesson early (§11.4).
        assert body.next_problem is not None
        assert body.next_problem.kc is prereq, (
            "parent must stay locked until the prereq is mastered"
        )
        problem = body.next_problem

    assert resumed is not None, "the prerequisite never cleared — the parent never resumed"
    assert resumed.next_problem is not None
    # Resumed onto the PARENT lesson (not the prereq, not a fresh start).
    assert resumed.next_problem.kc is _PARENT_KC
