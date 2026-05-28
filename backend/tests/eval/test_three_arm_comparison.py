"""Tests for the three-arm comparison harness (Slice 5.3.2 / 5.3.3).

CLAUDE.md §9: the chat arm's LLM is a fake here — no live call, no spend, and we never
assert on model prose. We assert the harness is WIRED right: it runs all three arms over the
same problems, the deterministic adaptive arm reproduces 0/5 false positives (the §8 result),
the static arm is N/A (no mastery construct), and the chat arm's self-assessment is parsed
into an over-claim verdict.
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.problem_generators import generate_problem
from app.eval.three_arm_comparison import (
    chat_mastery_claim,
    format_comparison,
    run_three_arm_comparison,
)
from app.llm.provider import Message, Tier


class _FakeProvider:
    """A fake LLMProvider returning a fixed reply and recording calls (no network)."""

    def __init__(self, reply: str) -> None:
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


def test_chat_mastery_claim_parses_the_self_assessment() -> None:
    """MASTERED → over-claim (True); NOT_YET → denied (False)."""
    problems = [generate_problem(KnowledgeComponentId.ADDITION_UNLIKE, seed=1)]

    claimed_yes, _ = chat_mastery_claim(
        problems, persona_id="surface_sam", provider=_FakeProvider("MASTERED")
    )
    claimed_no, _ = chat_mastery_claim(
        problems, persona_id="surface_sam", provider=_FakeProvider("NOT_YET")
    )
    assert claimed_yes is True
    assert claimed_no is False


def test_adaptive_arm_reproduces_zero_false_positives() -> None:
    """The deterministic adaptive arm denies confirmed mastery to all five personas (== §8).

    This holds regardless of the chat arm (a fake is injected), proving the adaptive defense
    is independent of the baseline.
    """
    rows = run_three_arm_comparison(chat_provider=_FakeProvider("MASTERED"))
    assert len(rows) == 5
    assert all(r.adaptive.claimed_mastery is False for r in rows)


def test_static_arm_is_na_and_chat_overclaims_when_it_self_certifies() -> None:
    """Static has no mastery construct (None = N/A); a chat tutor that says MASTERED is a
    false positive for every adversarial persona."""
    rows = run_three_arm_comparison(chat_provider=_FakeProvider("MASTERED"))
    assert all(r.static.claimed_mastery is None for r in rows)
    assert all(r.chat.claimed_mastery is True for r in rows)


def test_no_real_provider_is_constructed_when_injected() -> None:
    """The injected fake handles every chat call — the harness never reaches the network."""
    fake = _FakeProvider("NOT_YET")
    run_three_arm_comparison(chat_provider=fake)
    assert fake.calls, "expected the chat arm to call the injected provider"
    # Chat arm uses the premium tier (0.D.4) and the generic chat system prompt.
    assert all(call["tier"] == "premium" for call in fake.calls)


def test_report_summarizes_false_positives_per_arm() -> None:
    """The report states the headline per-arm false-positive tally."""
    rows = run_three_arm_comparison(chat_provider=_FakeProvider("MASTERED"))
    report = format_comparison(rows)
    assert "adaptive: 0/5" in report
    assert "chat: 5/5" in report
    assert "static: N/A" in report
