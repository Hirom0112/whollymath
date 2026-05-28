"""The persona learner's chat voice — Layer 4 for the simulated student (Slice 5.5.2).

The other Layer-4 use, sibling to ``tutor_voice`` (which voices OUR tutor): this renders a
persona's own chat turn in the simulated learner's natural voice. The Layer-3 simulator
(``personas/simulator.py``) decides WHAT the student does — the answer it submits, whether
it asked for a hint, the short note it "typed" if asked to explain. This module only
restates that already-decided surface output as a casual first-person chat message. It is
the natural-language polish ARCHITECTURE.md §10 places AFTER the deterministic path, never
on the sub-100ms turn loop (§8.1).

Two invariants make this safe (ARCHITECTURE.md §14):

  - **invariant 4 — Layer 4 is optional.** With no provider (or on any failure / blank
    completion) the deterministic plain utterance is returned. Voicing never breaks a turn.
  - **knowledge-state-blind / no-reveal (§8.3).** This is the §8.3 anti-pattern guard for
    the learner voice: the renderer is given ONLY the persona's surface output (the answer,
    the hint flag, the short note) — never its ``KnowledgeMode``, misconceptions, or the
    ``can_justify`` tell the mastery model reads. So the LLM cannot betray understanding the
    persona does not have: if the persona wrote no explanation, there is nothing to justify
    and the prompt forbids inventing reasoning. A persona that "types" a non-justifying note
    ("I just followed the steps") has that note rephrased, never upgraded into understanding.

Short surface text, so it uses the ``cheap`` tier (Haiku 4.5, 0.D.4) — same as the mascot
voice — and reaches the model only through the ``llm`` provider (§8.1).
"""

from __future__ import annotations

from app.llm.provider import AnthropicProvider, LLMProvider, Message, Tier

# The student character + the hard guardrails. It rephrases the student's own turn; it never
# adds reasoning or math the student did not write (the §8.3 no-reveal guard for the learner).
LEARNER_SYSTEM_PROMPT = (
    "You are voicing a middle-school student typing a quick message to their math tutor. "
    "You will be given the answer they are submitting and, if any, the short note they wrote. "
    "Restate it as ONE casual, natural first-person chat message. Keep the answer EXACTLY as "
    "given. Do NOT add any reasoning, justification, or math the student did not write — if "
    "they gave no explanation, do not invent one. Sound like a real kid, not a textbook."
)


def _plain_utterance(
    submitted_answer: str | None,
    explanation: str | None,
    requested_hint: bool,
) -> str:
    """The deterministic fallback utterance built only from the surface output.

    This is the dependable text returned whenever Layer 4 is off or fails. It carries the
    answer (or an honest "not sure" when none was submitted), surfaces a hint request when
    the persona asked for one, and appends the persona's own note verbatim — and nothing
    more, so it invents no reasoning the persona did not give (the no-reveal invariant).
    """
    if submitted_answer is None:
        base = "I'm not sure." if not requested_hint else "I'm not sure — can I get a hint?"
    elif requested_hint:
        base = f"Can I get a hint? I think it might be {submitted_answer}."
    else:
        base = f"I think it's {submitted_answer}."
    if explanation:
        base = f"{base} {explanation}"
    return base


def voice_learner_turn(
    submitted_answer: str | None,
    *,
    explanation: str | None = None,
    requested_hint: bool = False,
    provider: LLMProvider | None = None,
    tier: Tier = "cheap",
) -> str:
    """Rephrase a persona's turn in the learner's voice; fall back to the plain utterance.

    Inputs are the persona's SURFACE output only (knowledge-state-blind, §8.3): the answer it
    submitted (as the string it would type, or ``None`` for no submission), whether it asked
    for a hint, and the short note it typed if asked to explain. With no ``provider`` the
    deterministic plain utterance is returned (invariant 4); any provider failure or a
    blank/whitespace completion also returns it — voicing is a polish that must never break a
    turn. Uses the ``cheap`` tier (Haiku 4.5, 0.D.4) — short surface text.
    """
    base = _plain_utterance(submitted_answer, explanation, requested_hint)
    if provider is None:
        return base
    messages = [Message("user", f"Here is the student's turn to voice:\n{base}")]
    try:
        voiced = provider.complete(messages, tier=tier, system=LEARNER_SYSTEM_PROMPT)
    except Exception:
        # Invariant 4: a model/network failure costs us naturalness, never the turn.
        return base
    return voiced.strip() or base


def default_learner_voice_provider() -> LLMProvider:
    """The Anthropic-backed learner-voice provider (client created lazily)."""
    return AnthropicProvider()


__all__ = [
    "LEARNER_SYSTEM_PROMPT",
    "default_learner_voice_provider",
    "voice_learner_turn",
]
