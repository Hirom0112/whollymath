"""Tests for the persona learner-voice renderer (Slice 5.5.2, Layer 4).

This is the sibling of ``tutor_voice`` for the OTHER Layer-4 use: rendering a persona's
own chat turn in the simulated learner's voice. Per CLAUDE.md §9 we test the INPUTS and
the surrounding behavior, never the (non-deterministic) LLM output, using a recording
fake provider. The two invariants that make Layer 4 safe (ARCHITECTURE.md §14):

  - invariant 4 (5.5.3): Layer 4 is optional — no provider / failure / blank → the
    deterministic plain utterance, verbatim. Voicing never breaks anything.
  - knowledge-state-blind / no-reveal (5.5.4, §8.3): the renderer is given ONLY the
    persona's already-decided surface output (the answer it submitted, the short note it
    typed). It never receives the knowledge state, and when the persona wrote no
    explanation the renderer must not invent reasoning — the plain utterance carries none.
"""

from __future__ import annotations

from app.llm.provider import Message, Tier
from app.persona_surface.learner_voice import (
    LEARNER_SYSTEM_PROMPT,
    voice_learner_turn,
)


class _RecordingProvider:
    """A fake LLM provider that records its call and returns a canned line (§9)."""

    def __init__(self, reply: str = "Hmm, I think it's that?") -> None:
        self.reply = reply
        self.calls: list[tuple[list[Message], Tier, str | None]] = []

    def complete(
        self, messages: list[Message], *, tier: Tier = "standard", system: str | None = None
    ) -> str:
        self.calls.append((messages, tier, system))
        return self.reply


class _FailingProvider:
    def complete(
        self, messages: list[Message], *, tier: Tier = "standard", system: str | None = None
    ) -> str:
        raise RuntimeError("model unavailable")


def test_no_provider_returns_plain_utterance() -> None:
    """Invariant 4: with no provider the deterministic plain utterance is returned."""
    out = voice_learner_turn("5/6", provider=None)
    assert "5/6" in out
    assert out == voice_learner_turn("5/6", provider=None)  # deterministic


def test_none_answer_is_an_unsure_utterance() -> None:
    """A persona that submitted nothing reads as 'not sure', never a fabricated answer."""
    out = voice_learner_turn(None, provider=None)
    assert out.strip()
    assert "not sure" in out.lower()


def test_provider_called_with_learner_prompt_and_answer() -> None:
    """The provider sees the answer + the learner system prompt; we test inputs, not output."""
    provider = _RecordingProvider()
    voice_learner_turn("5/6", explanation="I just followed the steps", provider=provider)
    assert len(provider.calls) == 1
    messages, tier, system = provider.calls[0]
    assert system == LEARNER_SYSTEM_PROMPT
    assert tier == "cheap"
    sent = " ".join(m.content for m in messages)
    assert "5/6" in sent
    assert "I just followed the steps" in sent


def test_knowledge_state_never_reaches_the_provider() -> None:
    """No-reveal (§8.3): the prompt carries only surface output, no knowledge-state terms.

    The renderer's signature accepts only the answer / explanation / hint flag, so it is
    structurally blind; this guards that no mode or misconception label leaks into the
    message even via the explanation we pass through.
    """
    provider = _RecordingProvider()
    voice_learner_turn("5/6", explanation="I just followed the steps", provider=provider)
    sent = " ".join(m.content for m in provider.calls[0][0]).lower()
    forbidden_terms = (
        "procedure_only",
        "with_misconception",
        "misconception",
        "can_justify",
        "bkt",
    )
    for forbidden in forbidden_terms:
        assert forbidden not in sent


def test_provider_failure_falls_back_to_plain_utterance() -> None:
    """Invariant 4: a model failure costs naturalness, never the turn."""
    out = voice_learner_turn("5/6", provider=_FailingProvider())
    assert "5/6" in out


def test_blank_completion_falls_back() -> None:
    """A blank/whitespace completion is a soft failure → the plain utterance."""
    out = voice_learner_turn("5/6", provider=_RecordingProvider(reply="   "))
    assert "5/6" in out


def test_plain_utterance_invents_no_reasoning_when_no_explanation() -> None:
    """No-reveal: with no explanation written, the fallback utterance adds no justification."""
    out = voice_learner_turn("5/6", explanation=None, provider=None)
    # the bare answer, optionally with a hedge — but no 'because' reasoning it didn't give.
    assert "because" not in out.lower()


def test_hint_request_is_reflected_in_the_plain_utterance() -> None:
    """A persona that asked for a hint reads as asking for help (Hugo's signature surfaces)."""
    out = voice_learner_turn("5/6", requested_hint=True, provider=None)
    assert "hint" in out.lower() or "help" in out.lower()
