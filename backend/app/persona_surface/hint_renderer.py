"""LLM rephrasing of an already-decided worked-example hint (Slice 5.6, Layer 4).

The deterministic domain decides WHAT the hint says: ``tutor/worked_example.py`` produces
the verified-correct canonical step text. This module only rephrases that text in a warm
voice for a 6th-7th grader. It is the natural-language polish ARCHITECTURE.md §10 places
AFTER the deterministic path — never on the sub-100ms turn loop (§8.1), only on help
moments. It mirrors ``tutor_voice.py`` (the precedent Layer-4 renderer) in structure.

Two invariants make this safe (ARCHITECTURE.md §14):

  - **invariant 4 — Layer 4 is optional.** With no provider wired (or on any failure /
    blank completion) the canonical text is returned unchanged. The hint loses only
    chat-naturalness; its content and every numeric fact are intact. Rephrasing NEVER
    breaks a help moment.
  - **knowledge-state-blind (§8.3).** The renderer sees ONLY ``base_text`` — never the
    learner's mastery state, never the operands beyond what the canonical text already
    shows. The prompt forbids adding or changing numbers and forbids revealing more than
    the given text, so the rephrase cannot leak anything held server-side.

This is the LLM half of locked decision 0.D.3 ("LLM slot-fill → SymPy-validated → ≤2
retries → pre-written fallback"). The SymPy validation is a SEPARATE module
(``domain/hint_validation.py``) and the retry/fallback orchestration is in
``tutor/hints.py``; this module is purely "produce one warm candidate from this text."

Hint slot-fill uses the ``standard`` tier = Claude Sonnet 4.6 (decision 0.D.4) — a step of
real math copy warrants more capability than the mascot's one-liner (which uses ``cheap``).
"""

from __future__ import annotations

from app.llm.provider import AnthropicProvider, LLMProvider, Message, Tier

# The rephrase character + the HARD guardrails. It rewords warmly; it never alters the math
# and never reveals more than the canonical text already shows. The numeric guardrails are
# what let the downstream SymPy gate (domain/hint_validation.py) usually pass on the first try.
HINT_SYSTEM_PROMPT = (
    "You are a warm, encouraging math tutor helping a 6th-7th grade student with fractions. "
    "You will be given ONE hint the tutor has already worked out. Restate it in a friendly, "
    "plain voice using one to a few short sentences. HARD RULES you must never break: keep "
    "every number and fraction EXACTLY as written, as digits (for example '1/3' stays '1/3' "
    "and '12' stays '12') — do NOT spell numbers out in words. Do NOT add any new number and "
    "do NOT change any number. Do NOT reveal anything beyond what the given hint shows, and "
    "do NOT solve any further. Only reword the hint you were given more kindly."
)


def render_hint_text(
    base_text: str,
    *,
    provider: LLMProvider | None = None,
    tier: Tier = "standard",
) -> str:
    """Rephrase the canonical hint text warmly; fall back to it verbatim on any trouble.

    ``base_text`` is the deterministic, verified-correct canonical step text — the ONLY
    content the model sees (knowledge-state-blind, §8.3). With no ``provider`` the text is
    returned unchanged (Layer 4 disabled, invariant 4). Any provider failure or a
    blank/whitespace completion also returns ``base_text`` — rephrasing is a polish that
    must never break a help moment. The returned candidate is NOT yet trusted: the caller
    (``tutor/hints.py``) runs it through the SymPy numeric gate before showing it.

    Hint slot-fill uses the ``standard`` tier (Sonnet 4.6, decision 0.D.4).
    """
    if provider is None:
        return base_text
    messages = [Message("user", f"Here is the hint to restate in your voice:\n{base_text}")]
    try:
        rephrased = provider.complete(messages, tier=tier, system=HINT_SYSTEM_PROMPT)
    except Exception:
        # Invariant 4: a model/network failure costs us naturalness, never the hint itself.
        return base_text
    # A blank/empty completion is also a soft failure — keep the dependable canonical text.
    return rephrased.strip() or base_text


def default_hint_provider() -> LLMProvider:
    """The Anthropic-backed provider for ``create_app`` to wire in (client created lazily)."""
    return AnthropicProvider()


__all__ = ["HINT_SYSTEM_PROMPT", "default_hint_provider", "render_hint_text"]
