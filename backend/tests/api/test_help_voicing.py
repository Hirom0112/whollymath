"""Tests that the live loop voices help in the mascot's voice on help moments (Slice 5.5.2).

§9: the LLM is never called live — a fake voice provider stands in. We assert that WITH a
voice provider the reactive hint and the proactive intervention carry the voiced text, and
WITHOUT one they carry the pre-written nudge verbatim (invariant 4 — voicing is optional).
"""

from __future__ import annotations

from app.api.schemas import ActionType, SurfaceState, TurnRequest
from app.api.service import SessionStore
from app.helpneed.artifact import load_predictor
from app.llm.provider import Message, Tier
from app.policy.intervention_gate import SustainedHelpNeedGate
from app.tutor.hints import select_nudge

_ROUTE = "combine"
_WRONG = "1/2"

_VOICED = "Pie here — picture the pieces before you add!"


class _FakeVoice:
    """A voice provider that returns a fixed mascot line (so we can assert voicing ran)."""

    def complete(
        self,
        messages: list[Message],
        *,
        tier: Tier,
        system: str | None = None,
        max_tokens: int = 1024,
    ) -> str:
        return _VOICED


def _hint_req(session_id: str, problem_id: str) -> TurnRequest:
    return TurnRequest(
        session_id=session_id,
        problem_id=problem_id,
        action=ActionType.REQUEST_HINT,
        surface_state=SurfaceState.SYMBOLIC_FOCUS,
        latency_ms=1000,
        hint_used=False,
    )


def test_hint_is_voiced_when_a_voice_provider_is_present() -> None:
    """A REQUEST_HINT turn returns the mascot-voiced line when voicing is enabled."""
    store = SessionStore(voice_provider=_FakeVoice())
    started = store.start(_ROUTE)
    resp = store.process_turn(_hint_req(started.session_id, started.problem.problem_id))
    assert resp.hint == _VOICED


def test_hint_is_prewritten_without_a_voice_provider() -> None:
    """With no voice provider, the hint is the pre-written nudge verbatim (invariant 4)."""
    store = SessionStore()  # no voice provider
    started = store.start(_ROUTE)
    resp = store.process_turn(_hint_req(started.session_id, started.problem.problem_id))
    assert resp.hint == select_nudge(started.problem.kc).text
    assert resp.hint != _VOICED


def test_proactive_intervention_text_is_voiced() -> None:
    """When the gate fires, the proactive nudge is delivered in the mascot's voice."""
    store = SessionStore(
        predictor=load_predictor(),
        gate=SustainedHelpNeedGate(k=2, threshold=0.5),
        voice_provider=_FakeVoice(),
    )
    started = store.start(_ROUTE, proactive_enabled=True)
    sid = started.session_id
    pid = started.problem.problem_id
    fired = None
    for _ in range(4):
        resp = store.process_turn(
            TurnRequest(
                session_id=sid,
                problem_id=pid,
                action=ActionType.SUBMIT_ANSWER,
                submitted_answer=_WRONG,
                surface_state=SurfaceState.SYMBOLIC_FOCUS,
                latency_ms=3000,
                hint_used=False,
            )
        )
        assert resp.next_problem is not None
        pid = resp.next_problem.problem_id
        if resp.intervention is not None:
            fired = resp.intervention
            break
    assert fired is not None, "expected the gate to fire within 4 wrong turns"
    assert fired.text == _VOICED
