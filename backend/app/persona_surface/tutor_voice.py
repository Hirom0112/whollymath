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

from dataclasses import dataclass

from app.llm.provider import AnthropicProvider, LLMProvider, Message, Tier
from app.policy.emotion import Emotion, MomentType, select_emotion

# The mascot's character + the hard guardrails. It rephrases; it never solves or reveals.
MASCOT_SYSTEM_PROMPT = (
    "You are Pie, the friendly WhollyMath mascot — a cheerful little pie character helping a "
    "6th-7th grade student with fractions. You will be given a hint the tutor has already "
    "chosen. Say it to the student in your own warm, encouraging voice, in ONE short "
    "sentence. Do NOT solve the problem, do NOT give the answer, and do NOT add any new math "
    "— only rephrase the given hint more kindly."
)


@dataclass(frozen=True)
class VoicedHelp:
    """A line of tutor help: the (LLM-voiced) ``text`` plus its deterministic avatar affect.

    Slice 1.3: the avatar (Slice 2.2) both SPEAKS ``text`` and plays the ``emotion`` animation
    at ``intensity``. The split is the load-bearing invariant — the LLM produces ONLY ``text``
    (below); ``emotion`` and ``intensity`` come from ``policy.emotion.select_emotion`` keyed to
    the MOMENT TYPE the deterministic caller is in, never from the model and never from the
    learner's knowledge state (§8.3). Frozen/value-only so it is trivially comparable in tests.
    """

    text: str
    emotion: Emotion
    intensity: float


def voice_help(
    base_text: str,
    *,
    moment: MomentType,
    provider: LLMProvider | None = None,
    tier: Tier = "cheap",
) -> VoicedHelp:
    """Voice an already-decided help line and pair it with its deterministic avatar affect.

    Two halves, kept strictly separate (Slice 1.3):

      - ``text`` — the LLM rephrases ``base_text`` (the deterministic §3.8 nudge / proactive
        line) in the mascot's voice. ``base_text`` is the ONLY content the model sees. With no
        ``provider`` the text is returned unchanged (Layer 4 disabled, invariant 4); any
        provider failure or blank completion also falls back to ``base_text`` — voicing is a
        polish that must never break a help moment. The model NEVER sees ``moment`` or any
        knowledge state.
      - ``emotion`` / ``intensity`` — chosen deterministically from ``moment`` by the policy
        layer (``select_emotion``), so the avatar's affect can never contradict the verdict
        (no celebrating a wrong answer) and never leaks knowledge state (§8.3).
    """
    cue = select_emotion(moment)
    return VoicedHelp(
        text=_voice_text(base_text, provider=provider, tier=tier),
        emotion=cue.emotion,
        intensity=cue.intensity,
    )


def _voice_text(
    base_text: str,
    *,
    provider: LLMProvider | None,
    tier: Tier,
) -> str:
    """Rephrase ``base_text`` in the mascot's voice, or return it verbatim (invariant 4).

    The LLM half of ``voice_help`` in isolation: it sees only ``base_text`` — never the moment,
    never the learner's knowledge state. Disabled/failing/blank all fall back to ``base_text``.
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


__all__ = ["MASCOT_SYSTEM_PROMPT", "VoicedHelp", "default_voice_provider", "voice_help"]
