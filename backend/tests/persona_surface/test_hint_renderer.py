"""Tests for the LLM hint-rephrasing renderer (Slice 5.6).

CLAUDE.md §9: we never call the LLM live and never assert on its prose. We assert the
renderer is wired right (standard tier = Sonnet per 0.D.4, the rephrase system prompt,
the base text handed in) and — the load-bearing part — that it is a SAFE polish: with
Layer 4 disabled OR failing OR blank, it returns the canonical text unchanged
(ARCHITECTURE.md §14 invariant 4). The SymPy numeric gate is NOT here; it lives in
``domain/hint_validation.py`` and is exercised at the orchestration layer
(``tutor/hints.py``). This renderer only produces a candidate.
"""

from __future__ import annotations

from app.llm.provider import Message, Tier
from app.persona_surface.hint_renderer import HINT_SYSTEM_PROMPT, render_hint_text


class _RecordingProvider:
    def __init__(self, reply: str = "Find a common bottom for 1/3 and 1/4 — it's 12!") -> None:
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


_BASE = "Find a common denominator for 1/3 and 1/4: the smallest is 12."


def test_rephrases_via_standard_tier_with_the_hint_prompt() -> None:
    """A wired provider rephrases the base text; call uses the standard tier + hint prompt."""
    provider = _RecordingProvider(reply="The smallest shared bottom for 1/3 and 1/4 is 12!")
    out = render_hint_text(_BASE, provider=provider)
    assert out == "The smallest shared bottom for 1/3 and 1/4 is 12!"
    assert len(provider.calls) == 1
    call = provider.calls[0]
    # 0.D.4: hint slot-fill uses Sonnet = the "standard" tier.
    assert call["tier"] == "standard"
    assert call["system"] == HINT_SYSTEM_PROMPT
    # The base text must be handed to the model so it has something to rephrase.
    messages = call["messages"]
    assert isinstance(messages, list)
    assert _BASE in messages[0].content


def test_disabled_layer4_returns_base_text_verbatim() -> None:
    """No provider → the canonical text is returned unchanged, no call (invariant 4)."""
    assert render_hint_text(_BASE) == _BASE


def test_provider_failure_falls_back_to_base_text() -> None:
    """A model/network failure costs naturalness, never the hint itself (invariant 4)."""
    assert render_hint_text(_BASE, provider=_FailingProvider()) == _BASE


def test_blank_completion_falls_back_to_base_text() -> None:
    """An empty/whitespace completion is a soft failure — keep the dependable canonical text."""
    assert render_hint_text(_BASE, provider=_RecordingProvider(reply="   ")) == _BASE


def test_hint_prompt_forbids_changing_numbers_and_revealing_more() -> None:
    """The prompt pins the hard guardrails: keep numbers exact, add nothing, reveal no more."""
    lowered = HINT_SYSTEM_PROMPT.lower()
    assert "number" in lowered
    assert "do not add" in lowered or "do not change" in lowered
