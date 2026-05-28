"""The LLM provider abstraction — the ONLY place an LLM is called (Slice 5.5.1).

ARCHITECTURE.md §5/§14 and CLAUDE.md §8.1 confine every LLM call to this package: the
deterministic turn loop (verify → mastery → policy → HelpNeed) never imports `llm/`, and
the LLM is used only for natural-language *surface* rendering AFTER the deterministic
logic has decided what to say (Layer 4, the persona surface; hint slot-fill; worked-example
narration). SymPy owns math correctness (§8.2); XGBoost owns HelpNeed (§8.1); the LLM never
decides either.

Tier mapping (decision 0.D.4, locked 2026-05-28 — see TECH_STACK.md §6):

  - ``cheap``    → Claude Haiku 4.5  — the persona surface (Layer 4)
  - ``standard`` → Claude Sonnet 4.6 — hint slot-fill (Slice 5.6)
  - ``premium``  → Claude Opus 4.7   — worked examples / tutor explanations

Swappability (0.D.4: "Anthropic primary, swappable"): callers depend on the
``LLMProvider`` Protocol and the module-level ``complete`` helper, not on the Anthropic
SDK. A different backend is a new class satisfying the Protocol; nothing else changes.

Prompt caching (0.D.4: "aggressive prompt caching on persona system prompts"): the system
prompt is sent as a cache-controlled block, so a stable persona system prompt is written
to Anthropic's cache once and read cheaply on subsequent turns. Caching only engages above
the model's minimum cacheable prefix (~4096 tokens for Haiku 4.5 / Opus 4.7, ~2048 for
Sonnet 4.6); the breakpoint is harmless below that and starts paying off once the persona
prompt is large enough (shared/prompt-caching.md).

Determinism note (PROJECT.md §4.1, §8.3): the LLM only *renders* an already-decided action
and never sees a persona's knowledge state, so its non-determinism does not affect the
harness's evidence — it affects only chat naturalness (ARCHITECTURE.md §14 invariant 4).
Opus 4.7 rejects ``temperature``/``top_p``/``top_k``/``budget_tokens`` (400), so we send
none of them; surface text is short, so no extended thinking or streaming is used.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

import anthropic
from anthropic.types import MessageParam, TextBlock, TextBlockParam

# The three tiers (0.D.4) and the exact model IDs they map to. IDs are complete as-is —
# no date suffixes (claude-api skill: appending one 404s).
Tier = Literal["cheap", "standard", "premium"]

TIER_MODELS: dict[Tier, str] = {
    "cheap": "claude-haiku-4-5",
    "standard": "claude-sonnet-4-6",
    "premium": "claude-opus-4-7",
}

# Surface text is a sentence or two of natural language, so a small output cap is right
# (a fluent nudge or one worked step, not an essay). Callers may override.
DEFAULT_MAX_TOKENS = 1024


@dataclass(frozen=True)
class Message:
    """One chat turn at our boundary — deliberately tiny so callers never touch SDK types.

    The provider converts these to the backend's wire shape. ``role`` is the speaker;
    ``content`` is plain text (the surface layer sends/receives prose, not tool blocks).
    """

    role: Literal["user", "assistant"]
    content: str


class LLMProvider(Protocol):
    """The one method the surface layer depends on (0.D.4 swap seam).

    A Protocol, not a base class, so any backend that structurally provides ``complete``
    is a drop-in — Anthropic is primary, but nothing in the surface layer names it.
    """

    def complete(
        self,
        messages: list[Message],
        *,
        tier: Tier,
        system: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> str: ...


class AnthropicProvider:
    """The Anthropic-backed ``LLMProvider`` (the primary backend, 0.D.4).

    The SDK client is created lazily on first use so importing this module — and
    constructing the provider — needs no API key (the key is read from the gitignored
    ``.env``/environment only when a call is actually made). A client may be injected for
    tests (CLAUDE.md §9: mock the SDK, never call it live).
    """

    def __init__(self, client: anthropic.Anthropic | None = None) -> None:
        self._client = client

    def _get_client(self) -> anthropic.Anthropic:
        if self._client is None:
            # Reads ANTHROPIC_API_KEY from the environment (TECH_STACK §6; never hardcoded).
            self._client = anthropic.Anthropic()
        return self._client

    def complete(
        self,
        messages: list[Message],
        *,
        tier: Tier,
        system: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> str:
        """Render one surface completion for ``tier``; return the joined text.

        The system prompt (if any) is sent as a single cache-controlled block so a stable
        persona prompt is cached across turns (0.D.4). No sampling params or thinking are
        sent — surface rendering is short and Opus 4.7 rejects those params anyway.
        """
        if tier not in TIER_MODELS:  # defensive: a non-Literal value reached us at runtime
            raise ValueError(f"unknown tier {tier!r} (expected cheap/standard/premium)")

        api_messages: list[MessageParam] = [
            {"role": m.role, "content": m.content} for m in messages
        ]
        client = self._get_client()
        if system is None:
            # Omit the field entirely rather than send an empty/blank system block.
            response = client.messages.create(
                model=TIER_MODELS[tier],
                max_tokens=max_tokens,
                messages=api_messages,
            )
        else:
            # One cache-controlled block so a stable persona prompt is cached (0.D.4).
            system_block: TextBlockParam = {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
            response = client.messages.create(
                model=TIER_MODELS[tier],
                max_tokens=max_tokens,
                system=[system_block],
                messages=api_messages,
            )
        return "".join(block.text for block in response.content if isinstance(block, TextBlock))


# The default backend (Anthropic). Constructed at import — cheap, since the client is not
# created until the first ``complete`` call, so this needs no API key to import.
_DEFAULT_PROVIDER: LLMProvider = AnthropicProvider()


def complete(
    messages: list[Message],
    *,
    tier: Tier,
    system: str | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> str:
    """Module-level surface-completion entrypoint (the 0.D.4 ``llm.complete`` signature).

    Delegates to the default Anthropic provider. The surface layer (Slices 5.5.2/5.6) calls
    this; it must never be reached from the deterministic turn loop (§8.1).
    """
    return _DEFAULT_PROVIDER.complete(messages, tier=tier, system=system, max_tokens=max_tokens)


__all__ = [
    "DEFAULT_MAX_TOKENS",
    "TIER_MODELS",
    "AnthropicProvider",
    "LLMProvider",
    "Message",
    "Tier",
    "complete",
]
