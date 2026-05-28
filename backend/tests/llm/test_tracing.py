"""Tests for the LangSmith tracing wrapper (Slice PL.0).

Tracing is an OBSERVABILITY layer: it must never change the completion returned and must be a
transparent no-op unless LANGSMITH_TRACING is set. We test the gating + passthrough with a
recording fake provider (CLAUDE.md §9 — never call a real LLM or hit LangSmith's network).
"""

from __future__ import annotations

import pytest
from app.llm.provider import DEFAULT_MAX_TOKENS, Message, Tier
from app.llm.tracing import TracedProvider, traced, tracing_enabled


class _RecordingProvider:
    """A fake LLMProvider that records its calls and returns a canned completion."""

    def __init__(self, reply: str = "voiced text") -> None:
        self.reply = reply
        self.calls: list[tuple[list[Message], Tier, str | None, int]] = []

    def complete(
        self,
        messages: list[Message],
        *,
        tier: Tier = "standard",
        system: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> str:
        self.calls.append((messages, tier, system, max_tokens))
        return self.reply


def test_disabled_is_a_transparent_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    """With LANGSMITH_TRACING unset, the wrapper calls the inner provider and returns its text."""
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    inner = _RecordingProvider("hello")
    out = TracedProvider(inner).complete([Message("user", "hi")], tier="cheap", system="S")
    assert out == "hello"
    assert len(inner.calls) == 1
    messages, tier, system, _max = inner.calls[0]
    assert tier == "cheap"
    assert system == "S"


def test_enabled_still_returns_the_inner_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    """With tracing ON, behavior is unchanged — the inner completion is returned verbatim.

    We patch langsmith.traceable with a passthrough so the test never touches LangSmith's
    network (§9 — don't hit external services in tests); the point is only that wrapping a
    call in a trace must not alter the result and must not raise.
    """
    monkeypatch.setenv("LANGSMITH_TRACING", "true")

    import langsmith

    def _passthrough_traceable(*_args: object, **_kwargs: object):  # type: ignore[no-untyped-def]
        def _decorator(fn):  # type: ignore[no-untyped-def]
            return fn

        return _decorator

    monkeypatch.setattr(langsmith, "traceable", _passthrough_traceable)

    inner = _RecordingProvider("traced reply")
    out = TracedProvider(inner).complete([Message("user", "hi")], tier="premium")
    assert out == "traced reply"
    assert len(inner.calls) == 1


def test_tracing_enabled_reads_the_env_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """The gate recognizes the documented truthy values and nothing else."""
    monkeypatch.setenv("LANGSMITH_TRACING", "1")
    assert tracing_enabled()
    monkeypatch.setenv("LANGSMITH_TRACING", "TRUE")
    assert tracing_enabled()
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    assert not tracing_enabled()
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    assert not tracing_enabled()


def test_traced_helper_preserves_none() -> None:
    """traced(None) stays None (no provider wired → nothing to trace)."""
    assert traced(None) is None
    wrapped = traced(_RecordingProvider())
    assert isinstance(wrapped, TracedProvider)
