"""Three-arm comparison harness (Slice 5.3.2 / 5.3.3).

PROJECT.md §3.11 / RESEARCH.md §9 (the locked pre-registration): run the same five
adversarial personas through three arms and measure whether each arm can be fooled —

  - **Adaptive** (our tutor): SymPy verification + the §3.4 mastery rules + the S5
    transfer probe. Deterministic. Its false-positive count reproduces the §8 / Slice 4.1
    harness exactly (expected 0/5).
  - **Chat** (Slice 5.1): an LLM in a chat box that grades and certifies itself — no SymPy,
    no mastery model. We measure whether it *over-claims* mastery (RESEARCH.md §1.6). Its
    "mastery declaration" is operationalized as a final self-assessment turn the model
    answers ``MASTERED`` / ``NOT_YET`` (it certifies the way a chat tutor naturally would).
  - **Static** (Slice 5.2): a pre-rendered worked-example walkthrough. It has **no mastery
    construct**, so the mastery-linked metrics are **N/A** (the honest framing — option (a),
    locked 2026-05-28); it certifies nothing.

This module currently computes the **headline metric — false-positive mastery** — across the
three arms, the central §3.11 claim. The remaining five metrics (hint dependence,
procedural-vs-conceptual gap, format-variance robustness, engagement-floor enforcement,
transfer-at-mastery) are layered on top of the same run (follow-on within 5.3.3), and the
side-by-side comparison against the pre-registration is 5.3.4.

Boundaries (CLAUDE.md §7): this orchestrates already-tested pieces — ``measure_case`` (the
4.1 adaptive run), ``run_chat_session`` / ``run_static_session`` (the baseline arms) — and
does not reimplement them. The LLM is reached only through an injected ``app.llm`` provider;
in tests a fake is injected so **no live call is made and no money is spent** (CLAUDE.md §9).
Running the real comparison (live Anthropic calls across every persona × problem) is a
deliberate, cost-aware step, not something this import does.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.problem_generators import Problem, generate_problem
from app.eval.chat_baseline import CHAT_SYSTEM_PROMPT, run_chat_session
from app.eval.false_positive_harness import PersonaCase, harness_cases, measure_case
from app.eval.static_worked_example import run_static_session
from app.llm.provider import AnthropicProvider, LLMProvider, Message, Tier

# The chat tutor's "mastery declaration": after the session we ask it to self-certify in one
# word. A real chat tutor judges mastery itself (no SymPy, no model) — so this IS its mastery
# signal, and whether it over-claims is exactly what RESEARCH.md §1.6 / §3.11 measure.
CHAT_ASSESSMENT_QUESTION = (
    "Based on our whole conversation, has this student MASTERED this skill — could they get "
    "new problems like these right on their own, in any form, and explain why? "
    "Reply with exactly one word: MASTERED or NOT_YET."
)


@dataclass(frozen=True)
class ArmOutcome:
    """One arm's mastery verdict for one persona.

    ``claimed_mastery`` is the false positive the §3.11 defense is about: ``True`` = the arm
    certified a persona who has NOT truly mastered the KC (all five personas are adversaries,
    so any ``True`` is a false positive). ``None`` = the arm has no mastery construct (the
    static arm certifies nothing — reported N/A, not scored)."""

    arm: str  # "adaptive" | "chat" | "static"
    claimed_mastery: bool | None
    note: str


@dataclass(frozen=True)
class ComparisonRow:
    """The three arms' verdicts for one persona, over the same problems."""

    persona_id: str
    persona_name: str
    attacked_dimension: str
    adaptive: ArmOutcome
    chat: ArmOutcome
    static: ArmOutcome


def _problems_for(case: PersonaCase) -> list[Problem]:
    """The shared problem set every arm sees for this persona — the SAME items the adaptive
    arm runs (built from the case's adversarial sequence), so the comparison is apples-to-apples."""
    return [generate_problem(spec.kc, spec.seed, spec.surface_format) for spec in case.sequence]


def chat_mastery_claim(
    problems: Sequence[Problem],
    *,
    persona_id: str,
    provider: LLMProvider,
    tier: Tier = "premium",
) -> tuple[bool, str]:
    """Run the chat-baseline session, then ask the chat tutor to self-certify mastery.

    Returns ``(claimed_mastery, raw_reply)``. The conversation is reconstructed from the
    transcript and a final one-word assessment question is appended; ``MASTERED`` →
    over-claim. The model's prose is non-deterministic — we record what it says, we do not
    assert it (CLAUDE.md §9)."""
    from app.personas.registry import get_persona

    turns = run_chat_session(get_persona(persona_id), problems, provider=provider, tier=tier)
    conversation: list[Message] = []
    for turn in turns:
        conversation.append(
            Message("user", f"Problem: {turn.problem_statement}\nMy answer: {turn.student_answer}")
        )
        conversation.append(Message("assistant", turn.tutor_reply))
    conversation.append(Message("user", CHAT_ASSESSMENT_QUESTION))

    reply = provider.complete(conversation, tier=tier, system=CHAT_SYSTEM_PROMPT)
    claimed = reply.strip().upper().startswith("MASTERED")
    return claimed, reply.strip()


def compare_case(case: PersonaCase, *, chat_provider: LLMProvider) -> ComparisonRow:
    """Run all three arms for one persona over the same problems and record each verdict."""
    problems = _problems_for(case)

    adaptive_result = measure_case(case)
    adaptive = ArmOutcome(
        arm="adaptive",
        claimed_mastery=adaptive_result.confirmed_mastery,
        note=f"blocked at: {adaptive_result.blocked_at}",
    )

    # The static arm certifies nothing — run it to exercise the arm, but mastery is N/A.
    static_turns = run_static_session(case.persona, problems)
    static = ArmOutcome(
        arm="static",
        claimed_mastery=None,
        note=f"no mastery construct (N/A); showed {len(static_turns)} walkthroughs",
    )

    claimed, reply = chat_mastery_claim(
        problems, persona_id=case.persona.persona_id, provider=chat_provider
    )
    chat = ArmOutcome(arm="chat", claimed_mastery=claimed, note=f"self-assessment: {reply!r}")

    return ComparisonRow(
        persona_id=case.persona.persona_id,
        persona_name=case.persona.name,
        attacked_dimension=case.attacked_dimension,
        adaptive=adaptive,
        chat=chat,
        static=static,
    )


# The chat arm's pre-registered prediction (RESEARCH.md §9), used when we show the comparison
# WITHOUT spending money on a live run. claimed_mastery is left None (not measured) and the
# note carries the prediction; the view layer renders it as "predicted / pending".
PREDICTED_CHAT_NOTE = "predicted (pre-reg §9): over-claims mastery; live LLM run pending"


def compare_case_offline(case: PersonaCase) -> ComparisonRow:
    """Like ``compare_case`` but with NO LLM call: the adaptive and static arms are computed
    live/deterministically and the chat arm carries its pre-registered prediction. This is
    what the on-screen dashboard uses so viewing it costs nothing."""
    problems = _problems_for(case)

    adaptive_result = measure_case(case)
    adaptive = ArmOutcome(
        arm="adaptive",
        claimed_mastery=adaptive_result.confirmed_mastery,
        note=f"blocked at: {adaptive_result.blocked_at}",
    )
    static_turns = run_static_session(case.persona, problems)
    static = ArmOutcome(
        arm="static",
        claimed_mastery=None,
        note=f"no mastery construct (N/A); showed {len(static_turns)} walkthroughs",
    )
    chat = ArmOutcome(arm="chat", claimed_mastery=None, note=PREDICTED_CHAT_NOTE)

    return ComparisonRow(
        persona_id=case.persona.persona_id,
        persona_name=case.persona.name,
        attacked_dimension=case.attacked_dimension,
        adaptive=adaptive,
        chat=chat,
        static=static,
    )


def run_comparison_offline() -> list[ComparisonRow]:
    """The five-persona comparison with the real adaptive + static arms and a predicted chat
    arm — no LLM, no cost. Used to render the dashboard before the live run."""
    return [compare_case_offline(case) for case in harness_cases()]


def run_three_arm_comparison(*, chat_provider: LLMProvider | None = None) -> list[ComparisonRow]:
    """Run the five-persona comparison across all three arms.

    ``chat_provider`` defaults to the live Anthropic backend — **this makes real LLM calls
    for every persona × problem and costs money**; inject a fake in tests (CLAUDE.md §9)."""
    backend: LLMProvider = chat_provider if chat_provider is not None else AnthropicProvider()
    return [compare_case(case, chat_provider=backend) for case in harness_cases()]


def _verdict(outcome: ArmOutcome) -> str:
    if outcome.claimed_mastery is None:
        return "N/A"
    return "MASTERED ✗ (false positive)" if outcome.claimed_mastery else "denied ✓"


def format_comparison(rows: list[ComparisonRow]) -> str:
    """A readable side-by-side of the headline false-positive-mastery metric per arm."""
    lines = ["Three-arm comparison — false-positive mastery (PROJECT.md §3.11, pre-reg §9):", ""]
    for row in rows:
        lines.append(f"  {row.persona_name}  (attacks: {row.attacked_dimension})")
        lines.append(f"    adaptive: {_verdict(row.adaptive)}  [{row.adaptive.note}]")
        lines.append(f"    chat:     {_verdict(row.chat)}  [{row.chat.note}]")
        lines.append(f"    static:   {_verdict(row.static)}  [{row.static.note}]")
        lines.append("")

    adaptive_fp = sum(bool(r.adaptive.claimed_mastery) for r in rows)
    chat_fp = sum(bool(r.chat.claimed_mastery) for r in rows)
    lines.append(
        f"False positives — adaptive: {adaptive_fp}/{len(rows)}  |  "
        f"chat: {chat_fp}/{len(rows)}  |  static: N/A (no mastery construct)"
    )
    return "\n".join(lines)


def main() -> None:
    """Run the live comparison and print the report.

    From backend/: ``uv run python -m app.eval.three_arm_comparison``. WARNING: this makes
    live Anthropic calls (the chat arm) for every persona × problem — it costs money. The
    adaptive and static arms are free/deterministic.
    """
    print(format_comparison(run_three_arm_comparison()))


if __name__ == "__main__":
    main()


__all__ = [
    "ArmOutcome",
    "CHAT_ASSESSMENT_QUESTION",
    "ComparisonRow",
    "PREDICTED_CHAT_NOTE",
    "chat_mastery_claim",
    "compare_case",
    "compare_case_offline",
    "format_comparison",
    "run_comparison_offline",
    "run_three_arm_comparison",
]
