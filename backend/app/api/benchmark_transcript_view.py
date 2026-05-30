"""View assembly for the benchmark-theater transcripts (a teaching view of Slice 5.3).

Maps the raw per-turn transcript (``app.eval.benchmark_transcript``) to the display schemas
the surface renders verbatim. This is the api presentation seam: it carries no eval logic —
it prettifies enums into labels and turns each arm's outcome into a verdict + tone, so the
frontend stays presentation-only (CLAUDE.md §7). No SymPy, no LLM, no DB here.
"""

from __future__ import annotations

from app.api.schemas import (
    AdaptiveTurnView,
    BenchmarkPersonaSummaryView,
    BenchmarkTranscriptView,
    ChatTurnView,
    StaticTurnView,
    TransferProbeStepView,
)
from app.eval.benchmark_transcript import (
    AdaptiveTurn,
    PersonaTranscript,
    TransferProbeStep,
    build_persona_transcript,
    persona_summaries,
)
from app.eval.chat_baseline import ChatTurn
from app.eval.static_worked_example import StaticTurn
from app.mastery.mastery_model import ENGAGEMENT_FLOOR_MS

# The standing caveat shown on the chat arm: the per-turn tutor wording is an offline
# placeholder (no live model is called for the on-screen view), so a reader does not mistake
# it for what the model actually said. The arm's REAL signal is its self-certification verdict.
_CHAT_ILLUSTRATIVE_NOTE = (
    "These tutor replies are illustrative placeholders — the live chat arm calls a real LLM "
    "that judges correctness itself. What's real here is the student's answer and the verdict "
    "below (from a recorded live run)."
)

_STATIC_NOTE = (
    "Shows the same worked-example walkthrough every time. It never checks the answer and "
    "never tracks mastery — there is nothing here to pass or fail."
)

# Enum value → kid/reader-friendly label. Kept here (presentation), not in the domain enums.
_FORMAT_LABEL = {
    "symbolic": "Symbolic",
    "area_model": "Area model",
    "number_line": "Number line",
    "word_problem": "Word problem",
}
_ERROR_LABEL = {
    "magnitude": "Magnitude error",
    "operation": "Operation error",
    "format": "Format error",
    "other": "Other error",
}
_STATE_LABEL = {
    "S1_symbolic_focus": "S1 · symbolic focus",
    "S2_number_line_primary": "S2 · number line",
    "S3_fraction_bars_primary": "S3 · fraction bars",
    "S4_worked_example": "S4 · worked example",
    "S5_transfer_probe": "S5 · transfer probe",
}


def _adaptive_turn_view(turn: AdaptiveTurn) -> AdaptiveTurnView:
    result_label = "Correct" if turn.correct else _ERROR_LABEL.get(turn.error_category, "Error")
    return AdaptiveTurnView(
        problem_statement=turn.problem_statement,
        format_label=_FORMAT_LABEL.get(turn.surface_format, turn.surface_format),
        student_answer=turn.student_answer,
        correct=turn.correct,
        result_label=result_label,
        feedback=turn.feedback,
        state_label=_STATE_LABEL.get(turn.surface_state, turn.surface_state),
        hint_used=turn.hint_used,
        below_engagement_floor=turn.latency_ms < ENGAGEMENT_FLOOR_MS,
        latency_label=f"{turn.latency_ms / 1000:.1f}s",
    )


def _chat_turn_view(turn: ChatTurn) -> ChatTurnView:
    return ChatTurnView(
        problem_statement=turn.problem_statement,
        student_answer=turn.student_answer,
        tutor_reply=turn.tutor_reply,
    )


def _static_turn_view(turn: StaticTurn) -> StaticTurnView:
    answer = "—" if turn.student_answer is None else str(turn.student_answer)
    return StaticTurnView(
        problem_statement=turn.problem_statement,
        walkthrough=turn.walkthrough,
        student_answer=answer,
    )


# A failing mastery-rule reason (declare_mastery prefixes them stably) → a plain clause a
# presenter can read aloud. Keyed by the stable prefix the reason string starts with.
_REASON_PLAIN = {
    "engagement floor": "answered too fast to count as real thinking",
    "minimum attempts": "too few real attempts to judge",
    "BKT threshold": "not enough consistent evidence yet",
    "representation diversity": "only got it right in one representation, not across formats",
    "scaffolding": "every correct answer needed a hint",
    "interleaving": "only looked fluent on a blocked run of one problem type",
}


def _plain_reason(reason: str) -> str:
    """Translate one declare_mastery reason to a plain clause (fallback: the raw reason)."""
    for prefix, plain in _REASON_PLAIN.items():
        if reason.startswith(prefix):
            return plain
    return reason


def _probe_step_view(step: TransferProbeStep) -> TransferProbeStepView:
    return TransferProbeStepView(
        item_type=step.item_type,
        prompt=step.prompt,
        surface_format=step.surface_format,
        passed=step.passed,
        detail=step.detail,
    )


def _adaptive_why(t: PersonaTranscript) -> str:
    """A plain-language, demo-ready explanation of why the adaptive tutor ruled as it did."""
    if t.adaptive_blocked_at == "transfer_probe":
        return (
            f"{t.persona_name} got every practice answer right — but on the transfer probe "
            "couldn't explain why a wrong answer was wrong. That's a memorized procedure, not "
            "understanding, so mastery is refused. (This is the case a plain checker misses.)"
        )
    if t.adaptive_blocked_at == "provisional":
        clauses = [_plain_reason(r) for r in t.adaptive_reasons]
        joined = "; ".join(clauses) if clauses else "the evidence didn't hold up"
        return f"{t.persona_name} was denied before the final test: {joined}."
    return f"{t.persona_name} passed every check, including the transfer probe — genuine mastery."


def _chat_why(t: PersonaTranscript) -> str:
    """A plain-language explanation of the chat tutor's verdict."""
    if t.chat_claimed_mastery is None:
        return "No live run is recorded yet — this is the pre-registered prediction."
    if t.chat_claimed_mastery:
        return (
            "The chatbot only sees whether answers look right. The answers were right, so it "
            "declared mastery — it has no way to test understanding. This is the false positive."
        )
    return (
        f"The chatbot denied {t.persona_name} — but only because the answers were visibly wrong. "
        "It catches wrong answers, not right-answers-without-understanding."
    )


def _adaptive_verdict(t: PersonaTranscript) -> tuple[str, str]:
    """The adaptive arm's display verdict + tone. Confirmed mastery is the false positive the
    §3.11 defense must prevent (it never should fire for an adversary); a denial is the win."""
    if t.adaptive_confirmed:
        return "Mastered ✗ (false positive)", "bad"
    return "Denied ✓ — refused mastery", "good"


def _chat_verdict(t: PersonaTranscript) -> tuple[str, str]:
    """The chat arm's display verdict + tone, from the recorded live self-assessment (or the
    §9 prediction when no live run is committed)."""
    if t.chat_claimed_mastery is None:
        return "Predicted: over-claims", "pending"
    if t.chat_claimed_mastery:
        return "Mastered ✗ (false positive)", "bad"
    return "Denied ✓ (self-assessed)", "good"


def list_benchmark_personas() -> list[BenchmarkPersonaSummaryView]:
    """The five adversarial personas, in harness order, for the switcher (PROJECT.md §4.2)."""
    return [
        BenchmarkPersonaSummaryView(
            persona_id=s.persona_id,
            persona_name=s.persona_name,
            attacks=s.attacks,
            kc=s.kc,
        )
        for s in persona_summaries()
    ]


def build_benchmark_transcript_view(persona_id: str) -> BenchmarkTranscriptView | None:
    """Assemble the on-screen three-arm transcript for one persona, or ``None`` if unknown
    (the route maps that to a 404). Free and deterministic — no live LLM call (CLAUDE.md §8.1)."""
    t = build_persona_transcript(persona_id)
    if t is None:
        return None

    adaptive_verdict, adaptive_tone = _adaptive_verdict(t)
    chat_verdict, chat_tone = _chat_verdict(t)

    return BenchmarkTranscriptView(
        persona_id=t.persona_id,
        persona_name=t.persona_name,
        attacks=t.attacks,
        kc=t.kc,
        problems=list(t.problems),
        adaptive_turns=[_adaptive_turn_view(x) for x in t.adaptive_turns],
        adaptive_verdict=adaptive_verdict,
        adaptive_tone=adaptive_tone,
        adaptive_why=_adaptive_why(t),
        adaptive_blocked_at=t.adaptive_blocked_at,
        adaptive_reasons=list(t.adaptive_reasons),
        adaptive_probe_ran=t.adaptive_probe_ran,
        adaptive_probe_steps=[_probe_step_view(s) for s in t.adaptive_probe_steps],
        chat_turns=[_chat_turn_view(x) for x in t.chat_turns],
        chat_verdict=chat_verdict,
        chat_tone=chat_tone,
        chat_why=_chat_why(t),
        chat_self_assessment=t.chat_self_assessment,
        chat_live=t.chat_live,
        chat_illustrative_note=_CHAT_ILLUSTRATIVE_NOTE,
        static_turns=[_static_turn_view(x) for x in t.static_turns],
        static_verdict="N/A — certifies nothing",
        static_tone="neutral",
        static_note=_STATIC_NOTE,
    )


__all__ = ["build_benchmark_transcript_view", "list_benchmark_personas"]
