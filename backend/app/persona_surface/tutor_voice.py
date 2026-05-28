"""The tutor's mascot voice — Layer 4 for OUR tutor's help text (Slice 5.5.2, "B").

The deterministic logic decides WHAT help to give (the §3.8 nudge bank, the §3.6 policy);
this module only rephrases that already-decided text in the WhollyMath mascot's warm,
in-character voice. It is the natural-language polish ARCHITECTURE.md §10 places in the
``opt`` block AFTER the deterministic path — never on the sub-100ms decision path (§8.1),
and used only on help moments (the reactive hint and the proactive nudge), per the locked
2026-05-28 scope decision.

Two invariants make this safe (ARCHITECTURE.md §14):

  - **invariant 4 — Layer 4 is optional.** If no provider is wired (or the call fails), we
    return the pre-written text unchanged. The tutor loses only chat-naturalness; the help
    content and all evidence are intact. Voicing NEVER breaks a turn.
  - **knowledge-state-blind (§8.3).** The renderer is given only the public, already-shown
    help text — never the learner's mastery state, never the correct answer. The prompt
    forbids adding new math or revealing the answer, so the mascot cannot leak what the
    deterministic layer kept server-side (the analogue of §8.3 for the tutor's own voice).

The mascot voice is short surface text, so it uses the ``cheap`` tier (Haiku 4.5, 0.D.4)
and the ``llm`` provider — the only place an LLM is reached (§8.1).
"""

from __future__ import annotations

from app.llm.provider import AnthropicProvider, LLMProvider, Message, Tier

# The mascot's character + the hard guardrails. It rephrases; it never solves or reveals.
MASCOT_SYSTEM_PROMPT = (
    "You are Pie, the friendly WhollyMath mascot — a cheerful little pie character helping a "
    "6th-7th grade student with fractions. You will be given a hint the tutor has already "
    "chosen. Say it to the student in your own warm, encouraging voice, in ONE short "
    "sentence. Do NOT solve the problem, do NOT give the answer, and do NOT add any new math "
    "— only rephrase the given hint more kindly."
)


def voice_help(
    base_text: str,
    *,
    provider: LLMProvider | None = None,
    tier: Tier = "cheap",
) -> str:
    """Rephrase an already-decided help line in the mascot's voice; fall back to it verbatim.

    ``base_text`` is the deterministic help text (a §3.8 nudge / the proactive intervention
    line) — the only content the model sees. With no ``provider`` the text is returned
    unchanged (Layer 4 disabled, invariant 4); ``create_app`` injects the Anthropic provider
    to enable voicing live. Any provider failure also returns ``base_text`` — voicing is a
    polish that must never break a help moment.
    """
    if provider is None:
        return base_text
    messages = [Message("user", f"Here is the hint to say in your voice:\n{base_text}")]
    try:
        voiced = provider.complete(messages, tier=tier, system=MASCOT_SYSTEM_PROMPT)
    except Exception:
        # Invariant 4: a model/network failure costs us naturalness, never the help itself.
        return base_text
    # A blank/empty completion is also a soft failure — keep the dependable pre-written text.
    return voiced.strip() or base_text


def default_voice_provider() -> LLMProvider:
    """The Anthropic-backed voice provider for ``create_app`` (client created lazily)."""
    return AnthropicProvider()


__all__ = ["MASCOT_SYSTEM_PROMPT", "default_voice_provider", "voice_help"]
