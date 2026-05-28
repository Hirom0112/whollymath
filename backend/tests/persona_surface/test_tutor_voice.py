"""Tests for the mascot tutor-voice renderer (Slice 5.5.2, "B").

CLAUDE.md §9: we never call the LLM live and never assert on its prose. We assert the
renderer is wired right (cheap tier, mascot system prompt, the base text handed in) and —
the load-bearing part — that it is a SAFE polish: with Layer 4 disabled OR failing, it
returns the pre-written help text unchanged (ARCHITECTURE.md §14 invariant 4).
"""

from __future__ import annotations

from app.llm.provider import Message, Tier
from app.persona_surface.tutor_voice import MASCOT_SYSTEM_PROMPT, voice_help


class _RecordingProvider:
    def __init__(self, reply: str = "Let's see how big each piece is!") -> None:
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


class _FailingProvider:
    def complete(self, *args: object, **kwargs: object) -> str:
        raise RuntimeError("model unavailable")


def test_voices_help_via_cheap_tier_with_the_mascot_prompt() -> None:
    """A wired provider rephrases the base text; call uses cheap tier + the mascot prompt."""
    provider = _RecordingProvider(reply="Picture the pieces first!")
    out = voice_help("Are the pieces the same size?", provider=provider)
    assert out == "Picture the pieces first!"
    assert len(provider.calls) == 1
    call = provider.calls[0]
    assert call["tier"] == "cheap"
    assert call["system"] == MASCOT_SYSTEM_PROMPT
    # The base text must be handed to the model so it has something to rephrase.
    messages = call["messages"]
    assert isinstance(messages, list)
    assert "Are the pieces the same size?" in messages[0].content


def test_disabled_layer4_returns_prewritten_text() -> None:
    """No provider → the pre-written help text is returned unchanged, no call (invariant 4)."""
    assert voice_help("Find a common denominator first.") == "Find a common denominator first."


def test_provider_failure_falls_back_to_prewritten_text() -> None:
    """A model/network failure costs naturalness, never the help itself (invariant 4)."""
    out = voice_help("Are the pieces the same size?", provider=_FailingProvider())
    assert out == "Are the pieces the same size?"


def test_blank_completion_falls_back_to_prewritten_text() -> None:
    """An empty/whitespace completion is a soft failure — keep the dependable text."""
    out = voice_help("Try the number line.", provider=_RecordingProvider(reply="   "))
    assert out == "Try the number line."


def test_mascot_prompt_forbids_revealing_the_answer() -> None:
    """The prompt instructs the mascot to rephrase only — never solve or reveal (§8.3 analogue)."""
    lowered = MASCOT_SYSTEM_PROMPT.lower()
    assert "do not give the answer" in lowered
    assert "do not solve" in lowered
