"""Tests for the mascot tutor-voice renderer (Slice 5.5.2, "B").

CLAUDE.md §9: we never call the LLM live and never assert on its prose. We assert the
renderer is wired right (cheap tier, mascot system prompt, the base text handed in) and —
the load-bearing part — that it is a SAFE polish: with Layer 4 disabled OR failing, it
returns the pre-written help text unchanged (ARCHITECTURE.md §14 invariant 4).
"""

from __future__ import annotations

from app.llm.provider import Message, Tier
from app.persona_surface.tutor_voice import (
    MASCOT_SYSTEM_PROMPT,
    MASCOT_SYSTEM_PROMPT_ES,
    voice_help,
)
from app.policy.emotion import Emotion, MomentType


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
    out = voice_help(
        "Are the pieces the same size?", moment=MomentType.STUCK_NUDGE, provider=provider
    )
    assert out.text == "Picture the pieces first!"
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
    out = voice_help("Find a common denominator first.", moment=MomentType.STUCK_NUDGE)
    assert out.text == "Find a common denominator first."


def test_provider_failure_falls_back_to_prewritten_text() -> None:
    """A model/network failure costs naturalness, never the help itself (invariant 4)."""
    out = voice_help(
        "Are the pieces the same size?",
        moment=MomentType.STUCK_NUDGE,
        provider=_FailingProvider(),
    )
    assert out.text == "Are the pieces the same size?"


def test_blank_completion_falls_back_to_prewritten_text() -> None:
    """An empty/whitespace completion is a soft failure — keep the dependable text."""
    out = voice_help(
        "Try the number line.",
        moment=MomentType.STUCK_NUDGE,
        provider=_RecordingProvider(reply="   "),
    )
    assert out.text == "Try the number line."


def test_emotion_is_deterministic_and_independent_of_the_llm_text() -> None:
    """The avatar affect comes from the MOMENT, not the model: emotion is identical whether the
    provider rephrases, fails, or is absent (Slice 1.3 — the LLM only influences ``text``)."""
    voiced = voice_help(
        "Find a common denominator first.",
        moment=MomentType.STUCK_NUDGE,
        provider=_RecordingProvider(reply="You've got this — same-size pieces first!"),
    )
    failed = voice_help(
        "Find a common denominator first.",
        moment=MomentType.STUCK_NUDGE,
        provider=_FailingProvider(),
    )
    disabled = voice_help("Find a common denominator first.", moment=MomentType.STUCK_NUDGE)
    assert voiced.emotion == failed.emotion == disabled.emotion == Emotion.ENCOURAGE
    assert voiced.intensity == failed.intensity == disabled.intensity


def test_llm_never_receives_the_moment_or_knowledge_state() -> None:
    """The model sees ONLY the base help text — never the moment type or any state (§8.3).

    The moment drives emotion deterministically, but it must not reach the prompt: a stuck
    moment and a correct-verdict moment hand the SAME content to the model.
    """
    stuck_provider = _RecordingProvider()
    correct_provider = _RecordingProvider()
    voice_help("Same-size pieces?", moment=MomentType.STUCK_NUDGE, provider=stuck_provider)
    voice_help("Same-size pieces?", moment=MomentType.CORRECT_VERDICT, provider=correct_provider)
    stuck_msgs = stuck_provider.calls[0]["messages"]
    correct_msgs = correct_provider.calls[0]["messages"]
    assert isinstance(stuck_msgs, list)
    assert isinstance(correct_msgs, list)
    # Identical prompt content regardless of moment — the moment never leaks into the LLM call.
    assert stuck_msgs[0].content == correct_msgs[0].content
    assert "stuck" not in stuck_msgs[0].content.lower()
    assert "correct" not in stuck_msgs[0].content.lower()


def test_mascot_prompt_forbids_revealing_the_answer() -> None:
    """The prompt instructs the mascot to rephrase only — never solve or reveal (§8.3 analogue)."""
    lowered = MASCOT_SYSTEM_PROMPT.lower()
    assert "do not give the answer" in lowered
    assert "do not solve" in lowered


def test_es_mx_locale_uses_the_spanish_mascot_prompt() -> None:
    """locale="es-MX" → the provider is called with the SPANISH mascot system prompt.

    The caller passes already-translated Spanish ``base_text`` (the banked es string); this
    test only asserts the deterministic system-prompt selection (Slice 3.4). Mirrors
    ``test_voices_help_via_cheap_tier_with_the_mascot_prompt`` for the es-MX path.
    """
    provider = _RecordingProvider(reply="¡Imagina primero las partes!")
    out = voice_help(
        "¿Las partes son del mismo tamaño?",
        moment=MomentType.STUCK_NUDGE,
        provider=provider,
        locale="es-MX",
    )
    assert out.text == "¡Imagina primero las partes!"
    assert len(provider.calls) == 1
    call = provider.calls[0]
    assert call["tier"] == "cheap"
    assert call["system"] == MASCOT_SYSTEM_PROMPT_ES
    assert call["system"] != MASCOT_SYSTEM_PROMPT


def test_default_locale_still_uses_the_english_mascot_prompt() -> None:
    """The default locale ("en") is unchanged: still the English mascot prompt, byte-for-byte."""
    provider = _RecordingProvider()
    voice_help("Are the pieces the same size?", moment=MomentType.STUCK_NUDGE, provider=provider)
    assert provider.calls[0]["system"] == MASCOT_SYSTEM_PROMPT


def test_es_mx_disabled_layer4_returns_prewritten_spanish_text() -> None:
    """No provider on the es-MX path → the banked Spanish base text is returned unchanged."""
    out = voice_help(
        "Encuentra primero un denominador común.",
        moment=MomentType.STUCK_NUDGE,
        locale="es-MX",
    )
    assert out.text == "Encuentra primero un denominador común."


def test_locale_does_not_affect_emotion_or_intensity() -> None:
    """Affect comes from the MOMENT, not the locale: emotion/intensity are identical across
    en and es-MX for the same moment (Slice 1.3 — locale only routes the system prompt)."""
    en = voice_help(
        "Find a common denominator first.",
        moment=MomentType.STUCK_NUDGE,
        provider=_RecordingProvider(),
    )
    es = voice_help(
        "Encuentra primero un denominador común.",
        moment=MomentType.STUCK_NUDGE,
        provider=_RecordingProvider(reply="¡Tú puedes!"),
        locale="es-MX",
    )
    assert en.emotion == es.emotion
    assert en.intensity == es.intensity


def test_spanish_mascot_prompt_forbids_revealing_the_answer() -> None:
    """The Spanish prompt carries the same guardrails: rephrase only, never solve or reveal."""
    lowered = MASCOT_SYSTEM_PROMPT_ES.lower()
    assert "no resuelvas" in lowered
    assert "no des la respuesta" in lowered
