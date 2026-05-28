"""LangSmith tracing for the LLM provider — confined to ``llm/`` (Slice PL.0).

Wraps any ``LLMProvider`` so that, WHEN tracing is enabled, each ``complete`` call is recorded
as a LangSmith run (latency, tier, success/error) for observability of the Layer-4 surface
calls. It is the only place LangSmith is touched, mirroring the rule that the LLM itself is
reached only through ``llm/`` (CLAUDE.md §8.1; ARCHITECTURE.md §5).

Strictly opt-in and safe by default (TODO PL.0.1):

  - **env-gated** by ``LANGSMITH_TRACING`` (``1``/``true``/``yes``). Unset → the wrapper is a
    transparent passthrough: it calls the inner provider and records nothing. So tests and any
    run without the flag are completely unaffected (no LangSmith import, no network).
  - **langsmith is an optional import**, done lazily inside the enabled branch. If the package
    is missing the wrapper still passes through — tracing degrades to nothing, never an error.
  - tracing only OBSERVES; it never changes the completion returned (invariant 4 spirit — an
    observability layer must not alter behavior).

Key handling: the LangSmith API key + project come from the environment
(``LANGSMITH_API_KEY`` / ``LANGSMITH_PROJECT``), never hardcoded (CLAUDE.md §10). PL.0.0
(rotate the key that was exposed in a transcript) is an operational step done out-of-band.
"""

from __future__ import annotations

import os

from app.llm.provider import DEFAULT_MAX_TOKENS, LLMProvider, Message, Tier

_TRUTHY = {"1", "true", "yes", "on"}


def tracing_enabled() -> bool:
    """Whether LangSmith tracing is switched on for this process (``LANGSMITH_TRACING``)."""
    return os.environ.get("LANGSMITH_TRACING", "").strip().lower() in _TRUTHY


class TracedProvider:
    """An ``LLMProvider`` decorator that records each ``complete`` call to LangSmith.

    Satisfies the same Protocol as the wrapped provider, so it is a drop-in (the surface
    layer never knows it is traced). When tracing is disabled — or langsmith is not installed
    — it is a transparent passthrough that adds nothing and can fail in no new way.
    """

    def __init__(self, inner: LLMProvider) -> None:
        self._inner = inner

    def complete(
        self,
        messages: list[Message],
        *,
        tier: Tier,
        system: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> str:
        if not tracing_enabled():
            return self._inner.complete(messages, tier=tier, system=system, max_tokens=max_tokens)
        try:
            from langsmith import traceable
        except ImportError:
            # Flag is on but the package isn't here — degrade to a plain passthrough.
            return self._inner.complete(messages, tier=tier, system=system, max_tokens=max_tokens)

        @traceable(name="llm.complete", run_type="llm", metadata={"tier": tier})
        def _run() -> str:
            return self._inner.complete(messages, tier=tier, system=system, max_tokens=max_tokens)

        return _run()


def traced(provider: LLMProvider | None) -> LLMProvider | None:
    """Wrap ``provider`` in tracing if one is given; ``None`` stays ``None`` (no provider)."""
    return None if provider is None else TracedProvider(provider)


__all__ = ["TracedProvider", "traced", "tracing_enabled"]
