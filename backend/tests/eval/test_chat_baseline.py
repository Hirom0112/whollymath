"""Tests for the chat-baseline arm (Slice 5.1).

CLAUDE.md §9: we never call the LLM live and never assert on its prose. We assert the arm
is WIRED correctly — it drives the persona simulator for the student's answers, sends them
to the provider on the ``premium`` tier with the generic chat system prompt, threads the
running conversation, and assembles the transcript. The provider is a recording fake.

The arm's defining property — that it does NOT verify with SymPy or consult the mastery
model — is enforced structurally (see ``test_chat_baseline_uses_no_sympy_or_mastery``),
because that absence is exactly what makes it the control in the 5.3 comparison.
"""

from __future__ import annotations

from pathlib import Path

from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.problem_generators import Problem, generate_problem
from app.eval.chat_baseline import CHAT_SYSTEM_PROMPT, run_chat_session
from app.llm.provider import Message, Tier
from app.personas.registry import get_persona
from app.personas.simulator import simulate_action


class _RecordingProvider:
    """A fake LLMProvider: records every complete() call, returns a canned reply."""

    def __init__(self, reply: str = "Nice work — that looks right!") -> None:
        self.calls: list[dict[str, object]] = []
        self._reply = reply

    def complete(
        self,
        messages: list[Message],
        *,
        tier: Tier,
        system: str | None = None,
        max_tokens: int = 1024,
    ) -> str:
        self.calls.append({"messages": list(messages), "tier": tier, "system": system})
        return self._reply


def _two_problems() -> list[Problem]:
    return [
        generate_problem(KnowledgeComponentId.ADDITION_UNLIKE, seed=1),
        generate_problem(KnowledgeComponentId.ADDITION_UNLIKE, seed=2),
    ]


def test_one_turn_per_problem_with_the_canned_reply() -> None:
    """The transcript has one turn per problem, each carrying the tutor's reply."""
    provider = _RecordingProvider(reply="Looks right!")
    problems = _two_problems()
    turns = run_chat_session(get_persona("procedure_priya"), problems, provider=provider)
    assert len(turns) == len(problems)
    assert all(t.tutor_reply == "Looks right!" for t in turns)
    assert [t.problem_statement for t in turns] == [p.statement for p in problems]


def test_student_answer_is_the_simulated_persona_action() -> None:
    """The student's typed answer is exactly the Layer-3 simulator's answer (same as any arm).

    Procedure Priya answers addition correctly (PROCEDURE_ONLY → right answer), so the chat
    arm must send her correct answer string — proof it reuses the simulator, not a guess.
    """
    provider = _RecordingProvider()
    problem = generate_problem(KnowledgeComponentId.ADDITION_UNLIKE, seed=7)
    persona = get_persona("procedure_priya")
    expected = str(simulate_action(persona, problem).submitted_answer)

    turns = run_chat_session(persona, [problem], provider=provider)
    assert turns[0].student_answer == expected


def test_calls_use_premium_tier_and_the_chat_system_prompt() -> None:
    """Every tutor turn is a premium-tier (Opus 4.7) call carrying the generic chat prompt."""
    provider = _RecordingProvider()
    run_chat_session(get_persona("surface_sam"), _two_problems(), provider=provider)
    assert provider.calls, "expected the arm to call the provider"
    for call in provider.calls:
        assert call["tier"] == "premium"
        assert call["system"] == CHAT_SYSTEM_PROMPT


def test_conversation_is_threaded_across_turns() -> None:
    """Each turn sends the full running conversation, so the tutor has chat context.

    Turn 2's message list must contain turn 1's student message AND the tutor's turn-1
    reply, then the new student message — the growing transcript a chat box would keep.
    """
    provider = _RecordingProvider(reply="ok")
    turns = run_chat_session(get_persona("natural_number_nate"), _two_problems(), provider=provider)
    assert len(provider.calls) == 2

    first_messages = provider.calls[0]["messages"]
    second_messages = provider.calls[1]["messages"]
    assert isinstance(first_messages, list) and isinstance(second_messages, list)
    # Turn 1 sends exactly one (student) message; turn 2 sends student+tutor+student = 3.
    assert len(first_messages) == 1
    assert len(second_messages) == 3
    assert second_messages[0] == first_messages[0]  # turn-1 student message carried forward
    assert second_messages[1] == Message("assistant", "ok")  # turn-1 tutor reply carried forward
    assert second_messages[2].role == "user"  # the new student message
    _ = turns


def test_no_answer_renders_as_a_plain_chat_message() -> None:
    """A persona that submits no answer sends 'I'm not sure'; a real answer is sent verbatim."""
    from app.eval.chat_baseline import _format_answer

    assert _format_answer(None) == "I'm not sure"
    assert _format_answer("7/12") == "7/12"


def test_chat_baseline_imports_no_verifier_or_mastery_model() -> None:
    """Structural guard: the baseline never imports the SymPy verifier or the mastery model
    — that absence is what makes it the control arm (RESEARCH.md §1.6, §3.11). It grades and
    declares 'mastery' only through the chat model's reply, which 5.3 then measures."""
    source = Path("app/eval/chat_baseline.py").read_text()
    assert "app.domain.verifier" not in source
    assert "app.mastery" not in source
