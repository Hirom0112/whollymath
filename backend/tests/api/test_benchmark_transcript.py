"""Contract tests for the benchmark-theater endpoints (a teaching view of Slice 5.3).

CLAUDE.md §9: thin HTTP-level contract tests — the shapes the frontend consumes, and the
few guarantees that matter (the switcher lists the five personas; one persona's run carries
per-turn rows for all three arms; the verdicts reproduce the §3.11 defense — adaptive denies
all five, chat is fooled by exactly the right-answer-without-understanding pair; an unknown
persona is a 404). The eval logic has its own suite (tests/eval/); here we assert the API
exposes it, free and deterministic (no LLM call).
"""

from __future__ import annotations

from app.api.app import create_app
from app.api.schemas import BenchmarkPersonaSummaryView, BenchmarkTranscriptView

from tests.api.asgi_client import get

_PERSONA_IDS = {
    "surface_sam",
    "natural_number_nate",
    "hint_hunter_hugo",
    "click_through_cleo",
    "procedure_priya",
}
# The two arms the chat baseline over-claims for: right answers without understanding
# (RESEARCH.md §9; reproduced by the recorded live run).
_CHAT_FALSE_POSITIVES = {"hint_hunter_hugo", "procedure_priya"}


def test_benchmark_personas_lists_the_five_adversaries() -> None:
    app = create_app()
    status_code, body = get(app, "/eval/benchmark-personas")
    assert status_code == 200, body

    personas = [BenchmarkPersonaSummaryView.model_validate(p) for p in body]
    assert {p.persona_id for p in personas} == _PERSONA_IDS
    assert all(p.persona_name and p.attacks and p.kc for p in personas)


def test_transcript_carries_per_turn_rows_for_all_three_arms() -> None:
    """Priya's run: every arm sees the same problems, recorded turn by turn."""
    app = create_app()
    status_code, body = get(app, "/eval/benchmark-transcript/procedure_priya")
    assert status_code == 200, body

    t = BenchmarkTranscriptView.model_validate(body)
    assert t.persona_name == "Procedure Priya"
    assert t.problems, "the shared problem set should be listed"
    # Same item count fed to each arm.
    assert len(t.adaptive_turns) == len(t.chat_turns) == len(t.static_turns) == len(t.problems)
    # Adaptive turns carry the verified verdict; static turns are recorded unchecked.
    assert all(turn.result_label for turn in t.adaptive_turns)
    assert all(turn.walkthrough for turn in t.static_turns)
    # The chat replies are flagged as offline placeholders, never passed off as a live model.
    assert t.chat_illustrative_note
    assert all(turn.tutor_reply for turn in t.chat_turns)


def test_verdicts_reproduce_the_false_positive_defense() -> None:
    """The §3.11 headline, per persona: adaptive denies every adversary (good); chat is fooled
    only by Hugo and Priya (bad); static certifies nothing (neutral)."""
    app = create_app()
    for persona_id in _PERSONA_IDS:
        _, body = get(app, f"/eval/benchmark-transcript/{persona_id}")
        t = BenchmarkTranscriptView.model_validate(body)

        assert t.adaptive_tone == "good", f"{persona_id}: adaptive must deny the adversary"
        assert t.static_tone == "neutral"
        expected_chat = "bad" if persona_id in _CHAT_FALSE_POSITIVES else "good"
        assert t.chat_tone == expected_chat, f"{persona_id}: chat tone"


def test_priya_is_the_one_caught_by_the_transfer_probe() -> None:
    """Priya reaches provisional mastery (fluent procedure) and is denied only at the S5
    transfer probe — the stage that distinguishes her from the others (PROJECT.md §3.9)."""
    app = create_app()
    _, body = get(app, "/eval/benchmark-transcript/procedure_priya")
    t = BenchmarkTranscriptView.model_validate(body)
    assert t.adaptive_blocked_at == "transfer_probe"
    assert t.adaptive_reasons, "the denial should carry its reason"


def test_priya_transcript_makes_the_denial_explainable() -> None:
    """The teaching payload: when the probe runs, the two transfer items are shown (so a demo
    can point at them), and the error-finding item presents the UNREDUCED add-across mistake
    (2/8, not the SymPy-reduced 1/4). Plus a plain-language 'why' for narration."""
    app = create_app()
    _, body = get(app, "/eval/benchmark-transcript/procedure_priya")
    t = BenchmarkTranscriptView.model_validate(body)

    assert t.adaptive_probe_ran is True
    steps = t.adaptive_probe_steps
    assert {s.item_type for s in steps} == {"representation", "error_finding"}

    error_finding = next(s for s in steps if s.item_type == "error_finding")
    assert "2/8" in error_finding.prompt  # the relatable add-across mistake, not reduced 1/4
    assert error_finding.passed is False  # Priya can't catch/explain it

    assert t.adaptive_why and "understanding" in t.adaptive_why.lower()
    assert t.chat_why  # the chat verdict is narratable too


def test_provisional_blocked_persona_has_no_probe_but_still_explains() -> None:
    """Surface Sam is blocked at provisional, so the transfer probe never runs — but the
    plain-language 'why' still explains the denial for a demo."""
    app = create_app()
    _, body = get(app, "/eval/benchmark-transcript/surface_sam")
    t = BenchmarkTranscriptView.model_validate(body)
    assert t.adaptive_probe_ran is False
    assert not t.adaptive_probe_steps
    assert t.adaptive_why


def test_unknown_persona_is_404() -> None:
    app = create_app()
    status_code, _ = get(app, "/eval/benchmark-transcript/not_a_persona")
    assert status_code == 404
