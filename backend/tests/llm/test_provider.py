"""Tests for the LLM provider abstraction (Slice 5.5.1).

CLAUDE.md §9: we do NOT test the LLM's output (it is non-deterministic). We test that the
provider is CALLED with the right inputs — the tier→model mapping, the cache-controlled
system block (0.D.4), the message conversion — and that no sampling/thinking params are
sent (so the call cannot 400 on Opus 4.7). The SDK client is a recording fake, never a
live call.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import anthropic
import pytest
from anthropic.types import TextBlock
from app.llm import provider as provider_module
from app.llm.provider import AnthropicProvider, LLMProvider, Message, Tier, complete


class _RecordingMessages:
    """Stands in for ``client.messages`` — records the create() kwargs, returns text."""

    def __init__(self, text: str = "rendered surface text") -> None:
        self.last_kwargs: dict[str, Any] | None = None
        self._text = text

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.last_kwargs = kwargs
        return SimpleNamespace(content=[TextBlock(type="text", text=self._text)])


class _RecordingClient:
    def __init__(self, text: str = "rendered surface text") -> None:
        self.messages = _RecordingMessages(text)


def _provider_with(client: _RecordingClient) -> AnthropicProvider:
    # cast: the recording fake structurally stands in for anthropic.Anthropic (§9).
    return AnthropicProvider(client=cast(anthropic.Anthropic, client))


@pytest.mark.parametrize(
    ("tier", "expected_model"),
    [
        ("cheap", "claude-haiku-4-5"),
        ("standard", "claude-sonnet-4-6"),
        ("premium", "claude-opus-4-7"),
    ],
)
def test_tier_maps_to_the_locked_model_id(tier: Tier, expected_model: str) -> None:
    """0.D.4: cheap→Haiku 4.5, standard→Sonnet 4.6, premium→Opus 4.7 (exact IDs)."""
    client = _RecordingClient()
    _provider_with(client).complete([Message("user", "hi")], tier=tier)
    assert client.messages.last_kwargs is not None
    assert client.messages.last_kwargs["model"] == expected_model


def test_system_prompt_is_sent_as_a_cache_controlled_block() -> None:
    """0.D.4 aggressive caching: the system prompt rides in an ephemeral cache_control block."""
    client = _RecordingClient()
    _provider_with(client).complete([Message("user", "hi")], tier="cheap", system="You are Priya.")
    assert client.messages.last_kwargs is not None
    assert client.messages.last_kwargs["system"] == [
        {
            "type": "text",
            "text": "You are Priya.",
            "cache_control": {"type": "ephemeral"},
        }
    ]


def test_absent_system_is_omitted_not_blank() -> None:
    """No system → the field is omitted from the call, not sent as an empty/blank block."""
    client = _RecordingClient()
    _provider_with(client).complete([Message("user", "hi")], tier="cheap")
    assert client.messages.last_kwargs is not None
    assert "system" not in client.messages.last_kwargs


def test_messages_are_converted_to_the_wire_shape() -> None:
    """Our tiny Message dataclasses become the SDK's role/content dicts, in order."""
    client = _RecordingClient()
    turns = [
        Message("user", "1/3 + 1/4?"),
        Message("assistant", "Let's think."),
        Message("user", "7/12"),
    ]
    _provider_with(client).complete(turns, tier="standard")
    assert client.messages.last_kwargs is not None
    assert client.messages.last_kwargs["messages"] == [
        {"role": "user", "content": "1/3 + 1/4?"},
        {"role": "assistant", "content": "Let's think."},
        {"role": "user", "content": "7/12"},
    ]


def test_no_sampling_or_thinking_params_are_sent() -> None:
    """Opus 4.7 rejects temperature/top_p/top_k/thinking — assert we never send them."""
    client = _RecordingClient()
    _provider_with(client).complete([Message("user", "hi")], tier="premium")
    assert client.messages.last_kwargs is not None
    for forbidden in ("temperature", "top_p", "top_k", "thinking"):
        assert forbidden not in client.messages.last_kwargs


def test_max_tokens_defaults_and_overrides() -> None:
    """Short surface text by default (1024); caller can override."""
    client = _RecordingClient()
    p = _provider_with(client)
    p.complete([Message("user", "hi")], tier="cheap")
    assert client.messages.last_kwargs is not None
    assert client.messages.last_kwargs["max_tokens"] == 1024
    p.complete([Message("user", "hi")], tier="cheap", max_tokens=64)
    assert client.messages.last_kwargs["max_tokens"] == 64


def test_returns_joined_text_blocks() -> None:
    """The completion is the text of the response's text blocks."""
    client = _RecordingClient(text="Before you add, find a common denominator.")
    out = _provider_with(client).complete([Message("user", "hi")], tier="cheap")
    assert out == "Before you add, find a common denominator."


def test_unknown_tier_raises() -> None:
    """A non-Literal tier reaching us at runtime fails loud, not silently (§8.5)."""
    client = _RecordingClient()
    with pytest.raises(ValueError, match="unknown tier"):
        _provider_with(client).complete([Message("user", "hi")], tier=cast(Tier, "deluxe"))


def test_module_complete_delegates_to_the_default_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """The 0.D.4 `complete(...)` entrypoint forwards to the swappable default provider.

    Also demonstrates the swap seam: a Protocol-satisfying fake can stand in for Anthropic.
    """
    seen: dict[str, Any] = {}

    class _FakeProvider:  # satisfies LLMProvider structurally
        def complete(
            self,
            messages: list[Message],
            *,
            tier: Tier,
            system: str | None = None,
            max_tokens: int = 1024,
        ) -> str:
            seen.update(messages=messages, tier=tier, system=system, max_tokens=max_tokens)
            return "delegated"

    fake: LLMProvider = _FakeProvider()
    monkeypatch.setattr(provider_module, "_DEFAULT_PROVIDER", fake)

    out = complete([Message("user", "hi")], tier="standard", system="S", max_tokens=42)
    assert out == "delegated"
    assert seen == {
        "messages": [Message("user", "hi")],
        "tier": "standard",
        "system": "S",
        "max_tokens": 42,
    }
