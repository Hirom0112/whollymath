"""Tests for the three-arm comparison harness (Slice 5.3.2 / 5.3.3).

CLAUDE.md §9: the chat arm's LLM is a fake here — no live call, no spend, and we never
assert on model prose. We assert the harness is WIRED right: it runs all three arms over the
same problems, the deterministic adaptive arm reproduces 0/5 false positives (the §8 result),
the static arm is N/A (no mastery construct), and the chat arm's self-assessment is parsed
into an over-claim verdict.
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId
from app.domain.problem_generators import generate_problem
from app.eval.three_arm_comparison import (
    MetricComparison,
    adaptive_defense_coverage,
    chat_mastery_claim,
    format_comparison,
    format_defense_coverage,
    format_metric_comparison,
    per_metric_comparison,
    run_three_arm_comparison,
)
from app.llm.provider import Message, Tier

# The recorded live chat run (artifacts/chat_baseline_run.json): Hugo + Priya over-claimed,
# the other three were denied. The per-metric tests use this shape so they don't depend on
# the on-disk file (the eval_view layer reads the real artifact; here we pin the contract).
_RECORDED_CHAT_RUN = {
    "results": {
        "surface_sam": {"claimed_mastery": False, "self_assessment": "NOT_YET"},
        "natural_number_nate": {"claimed_mastery": False, "self_assessment": "NOT_YET"},
        "hint_hunter_hugo": {"claimed_mastery": True, "self_assessment": "MASTERED"},
        "click_through_cleo": {"claimed_mastery": False, "self_assessment": "NOT_YET"},
        "procedure_priya": {"claimed_mastery": True, "self_assessment": "MASTERED"},
    }
}


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


# ───────────────── Per-metric comparison (Slice 5.3.3 — the other 5 metrics) ─────────────────


def _metrics_by_key() -> dict[str, MetricComparison]:
    metrics = per_metric_comparison(recorded_chat_run=_RECORDED_CHAT_RUN)
    return {m.key: m for m in metrics}


def test_per_metric_covers_the_five_remaining_metrics() -> None:
    """The headline (false-positive mastery) is its own section; this layer adds the other
    five pre-registered metrics (RESEARCH.md §9), in order."""
    metrics = per_metric_comparison(recorded_chat_run=_RECORDED_CHAT_RUN)
    assert [m.key for m in metrics] == [
        "hint_dependence",
        "procedural_conceptual",
        "format_variance",
        "engagement_floor",
        "transfer_at_mastery",
    ]


def test_adaptive_metric_verdicts_are_derived_from_the_real_run() -> None:
    """Each adversary-targeted defense is shown as ENFORCED only because the actual
    deterministic run blocked that persona by that rule — not hardcoded. tone='good' means
    the §3.4 rule (or the transfer probe) fired for its adversary."""
    m = _metrics_by_key()
    # Hugo blocked by the unscaffolded-correct rule; Sam by representation diversity; Cleo by
    # the engagement floor; Priya demoted by the S5 transfer probe.
    assert m["hint_dependence"].adaptive.tone == "good"
    assert m["format_variance"].adaptive.tone == "good"
    assert m["engagement_floor"].adaptive.tone == "good"
    assert m["procedural_conceptual"].adaptive.tone == "good"
    assert m["transfer_at_mastery"].adaptive.tone == "good"


def test_chat_misses_the_understanding_metrics_but_lacks_the_mechanism_elsewhere() -> None:
    """From the recorded live run: chat over-claimed Hugo (hint dependence) and Priya
    (procedural-vs-conceptual) → 'Missed' (bad). It denied Sam/Cleo, but on visibly wrong
    answers, not via a format/engagement mechanism it doesn't have → 'No mechanism' (neutral),
    the honest framing from RESEARCH.md §9.1."""
    m = _metrics_by_key()
    assert m["hint_dependence"].chat.tone == "bad"
    assert m["procedural_conceptual"].chat.tone == "bad"
    assert m["format_variance"].chat.tone == "neutral"
    assert m["engagement_floor"].chat.tone == "neutral"
    assert m["transfer_at_mastery"].chat.tone == "bad"


def test_static_arm_metric_verdicts_are_architectural() -> None:
    """The static walkthrough has no mastery construct: the four behavioral metrics are bad
    (always shows the full solution, one format, no engagement gate); transfer is N/A."""
    m = _metrics_by_key()
    assert m["hint_dependence"].static.tone == "bad"
    assert m["format_variance"].static.tone == "bad"
    assert m["engagement_floor"].static.tone == "bad"
    assert m["procedural_conceptual"].static.tone == "bad"
    assert m["transfer_at_mastery"].static.tone == "neutral"


def test_per_metric_works_with_no_recorded_chat_run() -> None:
    """Before a live run, the chat column carries the §9 prediction (tone='pending'), exactly
    like the headline does — and never crashes for lack of an artifact."""
    metrics = per_metric_comparison(recorded_chat_run=None)
    assert all(m.chat.tone == "pending" for m in metrics)


def test_metric_report_renders_all_three_arms() -> None:
    """The text report (for the decision-log / writeup) names each metric and all three arms."""
    report = format_metric_comparison(per_metric_comparison(recorded_chat_run=_RECORDED_CHAT_RUN))
    assert "Hint dependence" in report
    assert "Transfer" in report
    assert "adaptive" in report.lower()
    assert "chat" in report.lower()
    assert "static" in report.lower()


# ── LIVE_KCS defense coverage (the adaptive arm's mechanisms exist for EVERY live KC) ──
# The headline false-positive metric is measured on the five fraction adversaries. This
# structural check ranges over the WHOLE LIVE_KCS space and asserts the adaptive arm's
# defense scaffolding (a lesson spec with a transfer probe + at least one routed error) is
# present for every live KC — the mechanisms the chat/static arms lack by construction. It
# is honest about scope: it certifies the DEFENSE EXISTS per KC, not that a persona attacked
# each KC (only the five fraction KCs are persona-tested).


def test_defense_coverage_spans_every_live_kc() -> None:
    rows = adaptive_defense_coverage()
    assert {row.kc for row in rows} == {kc.value for kc in LIVE_KCS}


def test_every_live_kc_has_a_transfer_probe_and_error_route() -> None:
    """The adaptive arm's confirm-gate (transfer probe) + error routing exist for every live KC."""
    rows = adaptive_defense_coverage()
    assert all(row.has_transfer_probe for row in rows)
    assert all(row.has_error_route for row in rows)


def test_defense_coverage_report_renders() -> None:
    report = format_defense_coverage(adaptive_defense_coverage())
    assert "defense coverage" in report.lower()
    # honest scope note: persona attacks cover only the fraction KCs.
    assert "persona" in report.lower()
