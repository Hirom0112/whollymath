"""Tests for the error-specific misconception remediation voice (Slice 1.2).

CLAUDE.md §9: we never call the LLM live and never assert on its prose. We assert the
gate-or-fallback discipline (the load-bearing part): an LLM line that ADDS or CHANGES a
number is rejected by the SymPy numeric gate and the canonical banked nudge is returned;
a clean, on-topic line passes; no provider returns the canonical nudge verbatim. And —
the §8.2/§8.3 invariant — the function never produces a correctness verdict and never sees
the learner's mastery state; it only renders surface text AFTER the verifier has decided.
"""

from __future__ import annotations

from app.domain.misconceptions import MisconceptionId, get_misconception
from app.llm.provider import Message, Tier
from app.persona_surface.misconception_voice import (
    MISCONCEPTION_SYSTEM_PROMPT,
    MISCONCEPTION_SYSTEM_PROMPT_ES,
    voice_misconception_nudge,
)

# A canonical banked nudge for KC_addition_unlike (digit-free, the §3.8 invariant). The
# add-across misconception is the matched error these tests pin to.
_CANONICAL_NUDGE = (
    "Before you add, are the pieces the same size? You can only count pieces that match."
)
_ADD_ACROSS = get_misconception(MisconceptionId.ADD_ACROSS_ERROR)


class _RecordingProvider:
    def __init__(
        self, reply: str = "Take another look — do the bottoms really change when you add?"
    ) -> None:
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


def test_clean_on_topic_line_passes_the_gate() -> None:
    """A digit-free, non-empty rephrase that introduces no number passes → the LLM line is used."""
    reply = "Look again — should the bottom numbers change when you add?"
    provider = _RecordingProvider(reply=reply)
    out = voice_misconception_nudge(_ADD_ACROSS, _CANONICAL_NUDGE, provider=provider)
    assert out == reply
    assert len(provider.calls) == 1


def test_line_with_extra_number_is_rejected_and_falls_back() -> None:
    """An LLM line that INVENTS a number the canonical nudge never made fails the SymPy gate →
    the canonical banked nudge is returned verbatim (invariant: validate-or-fallback)."""
    reply = "Remember, 1/2 plus 1/4 is not 2/6 — match the pieces first."
    provider = _RecordingProvider(reply=reply)
    out = voice_misconception_nudge(_ADD_ACROSS, _CANONICAL_NUDGE, provider=provider)
    assert out == _CANONICAL_NUDGE


def test_no_provider_returns_canonical_nudge_verbatim() -> None:
    """No provider wired → the canonical banked nudge is returned unchanged, no exception."""
    out = voice_misconception_nudge(_ADD_ACROSS, _CANONICAL_NUDGE, provider=None)
    assert out == _CANONICAL_NUDGE


def test_provider_failure_falls_back_to_canonical_nudge() -> None:
    """A model/network failure costs naturalness, never the help itself (invariant 4)."""
    out = voice_misconception_nudge(_ADD_ACROSS, _CANONICAL_NUDGE, provider=_FailingProvider())
    assert out == _CANONICAL_NUDGE


def test_blank_completion_falls_back_to_canonical_nudge() -> None:
    """An empty/whitespace completion is a soft failure — keep the dependable banked text."""
    out = voice_misconception_nudge(
        _ADD_ACROSS, _CANONICAL_NUDGE, provider=_RecordingProvider(reply="   ")
    )
    assert out == _CANONICAL_NUDGE


def test_unsafe_runaway_completion_falls_back() -> None:
    """A runaway (absurdly long) completion is rejected by is_safe_copy → canonical fallback."""
    out = voice_misconception_nudge(
        _ADD_ACROSS, _CANONICAL_NUDGE, provider=_RecordingProvider(reply="blah " * 1000)
    )
    assert out == _CANONICAL_NUDGE


def test_call_uses_cheap_tier_and_misconception_prompt() -> None:
    """The voice call uses the cheap tier and the English misconception system prompt."""
    provider = _RecordingProvider()
    voice_misconception_nudge(_ADD_ACROSS, _CANONICAL_NUDGE, provider=provider)
    call = provider.calls[0]
    assert call["tier"] == "cheap"
    assert call["system"] == MISCONCEPTION_SYSTEM_PROMPT


def test_llm_receives_the_misconception_description_to_target() -> None:
    """The model is handed the misconception description + the canonical nudge so it can target
    the specific error — but NEVER the learner's mastery state or the correct answer."""
    provider = _RecordingProvider()
    voice_misconception_nudge(_ADD_ACROSS, _CANONICAL_NUDGE, provider=provider)
    messages = provider.calls[0]["messages"]
    assert isinstance(messages, list)
    prompt = messages[0].content
    assert _ADD_ACROSS.description in prompt
    assert _CANONICAL_NUDGE in prompt
    # §8.3: no knowledge-state / verdict words leak into the prompt.
    lowered = prompt.lower()
    assert "mastery" not in lowered
    assert "probability" not in lowered


def test_function_never_returns_a_correctness_verdict() -> None:
    """§8.2: this is SURFACE only — it returns text (a str), never a bool/verdict, and never
    consults the verifier. The return type is a plain string in every path."""
    passing = voice_misconception_nudge(
        _ADD_ACROSS,
        _CANONICAL_NUDGE,
        provider=_RecordingProvider(reply="Look again at the bottoms."),
    )
    fallback = voice_misconception_nudge(_ADD_ACROSS, _CANONICAL_NUDGE, provider=None)
    assert isinstance(passing, str)
    assert isinstance(fallback, str)
    assert not isinstance(passing, bool)


def test_es_mx_locale_uses_the_spanish_misconception_prompt() -> None:
    """locale="es-MX" → the Spanish misconception system prompt is selected deterministically.

    The caller passes the already-Spanish canonical nudge; this only asserts prompt selection."""
    provider = _RecordingProvider(reply="Mira de nuevo — ¿cambian los de abajo al sumar?")
    out = voice_misconception_nudge(
        _ADD_ACROSS,
        "Antes de sumar, ¿son del mismo tamaño las partes?",
        provider=provider,
        locale="es-MX",
    )
    assert out == "Mira de nuevo — ¿cambian los de abajo al sumar?"
    call = provider.calls[0]
    assert call["system"] == MISCONCEPTION_SYSTEM_PROMPT_ES
    assert call["system"] != MISCONCEPTION_SYSTEM_PROMPT


def test_misconception_prompt_forbids_revealing_the_answer() -> None:
    """The prompt instructs a single corrective nudge — never solve, never reveal the answer."""
    lowered = MISCONCEPTION_SYSTEM_PROMPT.lower()
    assert "do not give the answer" in lowered
    assert "do not solve" in lowered


def test_spanish_misconception_prompt_forbids_revealing_the_answer() -> None:
    """The Spanish prompt carries the same guardrails: a single nudge, never solve or reveal."""
    lowered = MISCONCEPTION_SYSTEM_PROMPT_ES.lower()
    assert "no resuelvas" in lowered
    assert "no des la respuesta" in lowered
