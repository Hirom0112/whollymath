"""The chat-baseline arm — an LLM-in-a-chat-box tutor (Slice 5.1).

One of the three arms in the §3.11 comparison (Slice 5.3), the deliberate CONTROL: a
generic conversational LLM tutor with **none** of our machinery — no SymPy verification,
no mastery model, no §3.4 anti-gaming rules, no adaptive surface, no HelpNeed. It is
modeled on Varsity Tutors' "AI Tutor" (RESEARCH.md §2.1): the student types a problem and
an answer, the model replies in natural language, and the model itself judges correctness
and decides what to say. That last point is the whole scientific value of the arm —
RESEARCH.md §1.6 documents that step-level math verification by LLMs is unreliable, so a
chat tutor that grades with the model (not SymPy) is exactly the baseline our SymPy-gated,
mastery-defended tutor is meant to beat in the measured comparison.

What this module does NOT do (by design): it never imports the verifier and never consults
the mastery model. The persona's ANSWER is still produced by the already-tested Layer-3
simulator (so the SAME personas drive every arm in 5.3), but whether that answer is
"right", and whether the student has "mastered" anything, is left entirely to the chat
model's reply. The metric extraction and three-arm comparison are Slice 5.3; this module
only conducts the chat session and returns the transcript.

Boundaries: the LLM is reached only through the ``app.llm`` provider (§8.1 — no raw SDK
here; the provider is the one swap seam). No DB. The persona simulator and problem
generators are reused, not reimplemented (CLAUDE.md §7). Determinism: the persona action
and the problem are deterministic; the only non-determinism is the model's prose, which is
the point of the arm (it is what we measure, not assert — CLAUDE.md §9).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.problem_generators import Problem
from app.llm.provider import AnthropicProvider, LLMProvider, Message, Tier
from app.personas.persona_config import PersonaConfig
from app.personas.simulator import simulate_action

# The baseline's persona: a plain, friendly chat tutor. Deliberately generic — it carries
# NONE of our pedagogy (no representation diversity, no interleaving, no engagement floor),
# because the arm's job is to represent "just an LLM in a chat box" (RESEARCH.md §2.1).
CHAT_SYSTEM_PROMPT = (
    "You are a friendly, encouraging math tutor helping a 6th-7th grade student with "
    "fractions in a chat window. The student shares a problem and the answer they gave. "
    "Reply conversationally and briefly: say whether their answer looks right, give a "
    "short explanation or hint, and encourage them. You judge correctness yourself."
)


@dataclass(frozen=True)
class ChatTurn:
    """One exchange in a chat-baseline session: the problem, the student's typed answer,
    and the model tutor's natural-language reply."""

    problem_statement: str
    student_answer: str
    tutor_reply: str


def _format_answer(answer: object | None) -> str:
    """Render the persona's submitted answer as the student would type it into chat.

    ``None`` is the persona giving no answer (e.g. a pure give-up); we send a plain
    "I'm not sure" so the chat tutor has something to respond to, mirroring a real
    chat where a stuck student says as much.
    """
    return "I'm not sure" if answer is None else str(answer)


def run_chat_session(
    persona: PersonaConfig,
    problems: Sequence[Problem],
    *,
    provider: LLMProvider | None = None,
    tier: Tier = "premium",
) -> list[ChatTurn]:
    """Conduct a chat-baseline tutoring session and return its transcript.

    For each problem in order, the Layer-3 simulator produces the persona's deterministic
    answer (the same answer that persona would give in any arm), the answer is sent to the
    chat tutor as the student's message, and the model's reply is recorded. The full
    conversation is threaded back on each turn (prior problems, answers, and tutor replies)
    so the chat tutor has the running context a real chat box would — including, crucially,
    the chance to over-claim mastery off a short correct streak (what 5.3 measures).

    ``provider`` defaults to the Anthropic backend (0.D.4 ``premium`` tier = Opus 4.7 for
    tutor explanations); inject a fake in tests so no live call is made (CLAUDE.md §9).
    """
    backend: LLMProvider = provider if provider is not None else AnthropicProvider()
    history: list[Message] = []
    turns: list[ChatTurn] = []

    for problem in problems:
        action = simulate_action(persona, problem)
        student_answer = _format_answer(action.submitted_answer)
        student_message = f"Problem: {problem.statement}\nMy answer: {student_answer}"

        conversation = [*history, Message("user", student_message)]
        reply = backend.complete(conversation, tier=tier, system=CHAT_SYSTEM_PROMPT)

        turns.append(
            ChatTurn(
                problem_statement=problem.statement,
                student_answer=student_answer,
                tutor_reply=reply,
            )
        )
        history = [*conversation, Message("assistant", reply)]

    return turns


__all__ = ["CHAT_SYSTEM_PROMPT", "ChatTurn", "run_chat_session"]
