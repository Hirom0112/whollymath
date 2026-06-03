"""Error-specific misconception remediation voice — Layer 4 for the matched error (Slice 1.2).

When the SymPy verifier (``domain/verifier.py``) matches a wrong answer to a NAMED misconception
(``VerificationResult.matched_misconception``), the help moment can do better than a fixed banked
nudge: the mascot can voice a nudge TAILORED to that specific misconception. This module renders
that error-specific line — but only as a Layer-4 polish, behind the same hard invariants the rest
of the surface layer obeys (ARCHITECTURE.md §14, CLAUDE.md §8.1/§8.2/§8.3):

  - **The LLM NEVER decides correctness.** SymPy already decided (the verifier ran first, off the
    sub-100ms turn loop). This function runs AFTER the verdict, on the help path, and produces only
    surface TEXT — it never returns a verdict, never calls the verifier, never sees the answer.
  - **validate-or-fallback (0.D.3, mirrored from ``tutor_voice``/``build_validated_hint``).** The
    LLM rephrase is shown ONLY if it passes BOTH the SymPy numeric gate
    (``domain.hint_validation.numeric_claims_preserved`` — against the canonical nudge as the
    numeric source of truth) AND the pure-string safety filter (``tutor.hints.is_safe_copy``). On
    ANY failure — a changed/added number, blank, runaway, no provider, or a model error — we fall
    back to the CANONICAL banked nudge. The canonical line is always the dependable floor; voicing
    never breaks a help moment (invariant 4).
  - **knowledge-state-blind (§8.3).** The model is handed the misconception's public description
    and the public canonical nudge — never the learner's mastery state, never the correct answer.
    The prompt forbids adding new math or revealing the answer, so the mascot cannot leak what the
    deterministic layer kept server-side.

The matched-misconception description carries no numbers (it is conceptual prose), and the
canonical nudge is digit-free by the §3.8 invariant — so the SymPy gate's numeric source of truth
is "no numbers", and any number the LLM invents (a fabricated worked value, a leaked answer) trips
the gate and falls back. This is exactly the protection we want here.

Short surface text → ``cheap`` tier (Haiku 4.5, 0.D.4), reached only via the ``llm`` provider.
"""

from __future__ import annotations

from app.domain.hint_validation import numeric_claims_preserved
from app.domain.misconceptions import Misconception
from app.llm.provider import AnthropicProvider, LLMProvider, Message, Tier
from app.tts.provider import Locale
from app.tutor.hints import is_safe_copy

# The mascot's character + the hard guardrails for the ERROR-SPECIFIC nudge. It is given the named
# misconception and the canonical nudge, and must restate a SINGLE short corrective prompt that
# orients the learner away from THAT misconception — never the answer, never new math.
MISCONCEPTION_SYSTEM_PROMPT = (
    "You are Pie, the friendly WhollyMath mascot — a cheerful little pie character helping a "
    "6th-7th grade student. The student just made a specific kind of mistake, and the tutor has "
    "already chosen a gentle hint. You will be given a description of the student's misconception "
    "and the tutor's chosen hint. Restate the hint as ONE short, warm, corrective nudge that "
    "gently points the student back toward reconsidering THAT specific misconception. Do NOT give "
    "the answer, do NOT solve the problem, and do NOT add any new numbers or math — only re-voice "
    "the given hint more kindly and on-target for this mistake."
)

# es-MX (Latin-American Spanish) counterpart of MISCONCEPTION_SYSTEM_PROMPT — a faithful
# translation carrying the IDENTICAL guardrails (a single corrective nudge; never solve, never
# reveal the answer, never add new numbers/math). Selected deterministically from the ``locale``
# arg; the LLM never chooses the language. Register matches the es-MX locale (Slice 3.4).
MISCONCEPTION_SYSTEM_PROMPT_ES = (
    "Eres Pie, la simpática mascota de WhollyMath — un alegre pastelito que ayuda a un estudiante "
    "de sexto o séptimo grado. El estudiante acaba de cometer cierto tipo de error, y el tutor ya "
    "eligió una pista amable. Te darán una descripción del error del estudiante y la pista que "
    "eligió el tutor. Reformula la pista como UNA sola sugerencia breve, cálida y correctiva que "
    "invite con suavidad al estudiante a reconsiderar ESE error específico, en español. NO des la "
    "respuesta, NO resuelvas el problema y NO agregues números ni matemáticas nuevas — solo vuelve "
    "a expresar la pista dada de forma más amable y dirigida a ese error."
)


def voice_misconception_nudge(
    misconception: Misconception,
    canonical_nudge: str,
    *,
    provider: LLMProvider | None = None,
    tier: Tier = "cheap",
    locale: Locale = "en",
) -> str:
    """Voice an error-specific corrective nudge for ``misconception``, or fall back to the nudge.

    The LLM is given the misconception's public description and the deterministic canonical nudge,
    and asked to restate a SINGLE corrective prompt targeting that misconception. The rephrase is
    returned ONLY if it passes both the pure-string safety filter (``is_safe_copy``) AND the SymPy
    numeric gate (``numeric_claims_preserved`` against ``canonical_nudge`` as the numeric source of
    truth). On ANY failure — no provider, a model error, a blank/runaway completion, or a numeric
    claim the canonical nudge never made (an added/changed number) — the CANONICAL banked nudge is
    returned verbatim. This never raises on a bad LLM result (invariant 4).

    SURFACE ONLY: this returns text, never a verdict — it does not consult the verifier and never
    decides correctness (§8.2). The model NEVER sees the learner's knowledge state or the answer
    (§8.3); ``locale`` only routes which guardrail prompt voices the line (the caller passes the
    already-translated ``canonical_nudge`` for es-MX — this function does not translate).
    """
    if provider is None:
        return canonical_nudge

    system = MISCONCEPTION_SYSTEM_PROMPT_ES if locale == "es-MX" else MISCONCEPTION_SYSTEM_PROMPT
    user_text = (
        f"The student's misconception: {misconception.description}\n"
        f"The tutor's chosen hint: {canonical_nudge}"
    )
    try:
        candidate = provider.complete([Message("user", user_text)], tier=tier, system=system)
    except Exception:
        # Invariant 4: a model/network failure costs us naturalness, never the help itself.
        return canonical_nudge

    # Gate-or-fallback: the rephrase must be safe copy AND preserve EXACTLY the canonical nudge's
    # numeric claims (the nudge is digit-free, so any number the model invents trips this gate).
    if is_safe_copy(candidate) and numeric_claims_preserved(canonical_nudge, candidate):
        return candidate.strip()
    return canonical_nudge


def default_misconception_voice_provider() -> LLMProvider:
    """The Anthropic-backed voice provider (client created lazily; mirrors ``tutor_voice``)."""
    return AnthropicProvider()


__all__ = [
    "MISCONCEPTION_SYSTEM_PROMPT",
    "MISCONCEPTION_SYSTEM_PROMPT_ES",
    "default_misconception_voice_provider",
    "voice_misconception_nudge",
]
