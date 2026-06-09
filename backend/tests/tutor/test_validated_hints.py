"""Tests for the validated partial_step / worked_step hint orchestration (Slice 5.6).

``build_validated_hint`` ties the three layers together for the LLM-validated hint levels:
the domain's canonical worked-example text (``tutor/worked_example.py``) → an LLM warm
rephrase (``persona_surface/hint_renderer.py``) → the SymPy numeric gate
(``domain/hint_validation.py``) → ≤2 retries → pre-written fallback. This is locked
decision 0.D.3.

CLAUDE.md §9: we never call the LLM live and never assert on its prose. We use a recording
fake provider and assert the ORCHESTRATION: no provider → canonical fallback; a faithful
rephrase (same numbers, safe) → used; a rephrase with a WRONG number → falls back after
exactly ``1 + max_retries`` calls; unsafe copy → fallback. We also assert PARTIAL_STEP is
the first step only while WORKED_STEP is the longer multi-step walkthrough, that NUDGE is
refused (it comes from ``select_nudge``), and that the result is deterministic. Coverage
spans the add/sub/equivalence/number-line KCs via the problem generators.
"""

from __future__ import annotations

import pytest
from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.problem_generators import generate_problem
from app.llm.provider import Message, Tier
from app.tutor.hints import (
    Hint,
    HintLevel,
    build_validated_hint,
    is_safe_copy,
)
from app.tutor.worked_example import worked_example_for

_KC_ADD = KnowledgeComponentId.ADDITION_UNLIKE
_KC_SUB = KnowledgeComponentId.SUBTRACTION_UNLIKE
_KC_EQ = KnowledgeComponentId.EQUIVALENCE
_KC_NL = KnowledgeComponentId.NUMBER_LINE_PLACEMENT


class _RecordingProvider:
    """A fake provider that returns a fixed reply and records every call (CLAUDE.md §9)."""

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


def _canonical_partial(kc: KnowledgeComponentId, seed: int = 1) -> str:
    """The expected PARTIAL_STEP canonical text for a KC's generated problem (first step)."""
    return worked_example_for(generate_problem(kc, seed=seed)).steps[0].shown


# ─── No provider → canonical fallback (invariant 4) ──────────────────────────


def test_no_provider_returns_canonical_fallback() -> None:
    problem = generate_problem(_KC_ADD, seed=1)
    hint = build_validated_hint(problem, HintLevel.PARTIAL_STEP)
    assert isinstance(hint, Hint)
    assert hint.llm_used is False
    assert hint.level is HintLevel.PARTIAL_STEP
    assert hint.kc is _KC_ADD
    assert hint.template_id == "partial_step_fallback_v1"
    assert hint.natural_language == _canonical_partial(_KC_ADD, seed=1)


def test_no_provider_worked_step_fallback_template() -> None:
    problem = generate_problem(_KC_ADD, seed=1)
    hint = build_validated_hint(problem, HintLevel.WORKED_STEP)
    assert hint.llm_used is False
    assert hint.template_id == "worked_step_fallback_v1"


# ─── Faithful rephrase (same numbers, safe) → used ───────────────────────────


def test_faithful_rephrase_is_used() -> None:
    problem = generate_problem(_KC_ADD, seed=1)
    canonical = _canonical_partial(_KC_ADD, seed=1)
    # A safe rephrase that keeps EXACTLY the canonical numbers passes the SymPy gate.
    provider = _RecordingProvider(reply=f"Here's a friendly start: {canonical}")
    hint = build_validated_hint(problem, HintLevel.PARTIAL_STEP, provider=provider)
    assert hint.llm_used is True
    assert hint.template_id == "partial_step_llm_v1"
    assert hint.natural_language == f"Here's a friendly start: {canonical}"
    assert len(provider.calls) == 1
    assert provider.calls[0]["tier"] == "standard"


def test_es_mx_locale_asks_the_model_for_spanish() -> None:
    """The es-MX help-language threads a Spanish-restatement directive into the rephrase system
    prompt (Slice 3.6), while the digits-as-digits rule keeps the SymPy numeric gate valid. The
    default 'en' path carries no such directive."""
    problem = generate_problem(_KC_ADD, seed=1)
    canonical = _canonical_partial(_KC_ADD, seed=1)

    es_provider = _RecordingProvider(reply=f"Para empezar: {canonical}")
    build_validated_hint(problem, HintLevel.PARTIAL_STEP, provider=es_provider, locale="es-MX")
    es_system = es_provider.calls[0]["system"]
    assert isinstance(es_system, str) and "español de México" in es_system

    en_provider = _RecordingProvider(reply=f"To start: {canonical}")
    build_validated_hint(problem, HintLevel.PARTIAL_STEP, provider=en_provider, locale="en")
    en_system = en_provider.calls[0]["system"]
    assert isinstance(en_system, str) and "español de México" not in en_system


# ─── Wrong number → falls back after exactly 1 + max_retries calls ───────────


def test_wrong_number_falls_back_after_all_attempts() -> None:
    problem = generate_problem(_KC_ADD, seed=1)
    # A rephrase that invents a number not in the canonical text fails the SymPy gate every
    # time, so all attempts are exhausted and we fall back.
    provider = _RecordingProvider(reply="The answer is definitely 99999.")
    hint = build_validated_hint(problem, HintLevel.PARTIAL_STEP, provider=provider, max_retries=2)
    assert hint.llm_used is False
    assert hint.template_id == "partial_step_fallback_v1"
    assert hint.natural_language == _canonical_partial(_KC_ADD, seed=1)
    # 1 initial attempt + 2 retries = 3 provider calls, then fallback.
    assert len(provider.calls) == 3


def test_max_retries_zero_makes_exactly_one_attempt() -> None:
    problem = generate_problem(_KC_ADD, seed=1)
    provider = _RecordingProvider(reply="totally wrong 99999")
    hint = build_validated_hint(problem, HintLevel.PARTIAL_STEP, provider=provider, max_retries=0)
    assert hint.llm_used is False
    assert len(provider.calls) == 1


# ─── Unsafe copy → fallback ──────────────────────────────────────────────────


def test_unsafe_empty_copy_falls_back() -> None:
    problem = generate_problem(_KC_ADD, seed=1)
    # A blank completion is returned verbatim by render_hint_text (its fallback) which would
    # equal the canonical text; to exercise the is_safe_copy gate specifically we make the
    # provider return something that survives render_hint_text but is unsafe: an overly long
    # string. (Empty/whitespace is caught earlier by the renderer's own fallback.)
    provider = _RecordingProvider(reply="x" * 10_000)
    hint = build_validated_hint(problem, HintLevel.PARTIAL_STEP, provider=provider)
    assert hint.llm_used is False
    assert hint.template_id == "partial_step_fallback_v1"


def test_is_safe_copy_rules() -> None:
    assert is_safe_copy("Find a common denominator: the smallest is 12.") is True
    assert is_safe_copy("") is False
    assert is_safe_copy("   ") is False
    assert is_safe_copy("x" * 10_000) is False


# ─── PARTIAL_STEP vs WORKED_STEP differ (worked is longer) ───────────────────


def test_worked_step_is_longer_than_partial_step() -> None:
    problem = generate_problem(_KC_ADD, seed=1)
    partial = build_validated_hint(problem, HintLevel.PARTIAL_STEP)
    worked = build_validated_hint(problem, HintLevel.WORKED_STEP)
    # PARTIAL_STEP is the first step only; WORKED_STEP is the full numbered walkthrough.
    assert len(worked.natural_language) > len(partial.natural_language)
    assert partial.natural_language in worked.natural_language or "1." in worked.natural_language


# ─── NUDGE is refused on this path ───────────────────────────────────────────


def test_nudge_level_is_refused() -> None:
    problem = generate_problem(_KC_ADD, seed=1)
    with pytest.raises(ValueError):
        build_validated_hint(problem, HintLevel.NUDGE)


# ─── Determinism (PROJECT.md §4.1) ───────────────────────────────────────────


def test_deterministic_with_fixed_fake_provider() -> None:
    problem = generate_problem(_KC_ADD, seed=1)
    canonical = _canonical_partial(_KC_ADD, seed=1)
    first = build_validated_hint(
        problem, HintLevel.PARTIAL_STEP, provider=_RecordingProvider(reply=canonical)
    )
    second = build_validated_hint(
        problem, HintLevel.PARTIAL_STEP, provider=_RecordingProvider(reply=canonical)
    )
    assert first == second


# ─── KC coverage: add / sub / equivalence / number-line ──────────────────────


@pytest.mark.parametrize("kc", [_KC_ADD, _KC_SUB, _KC_EQ, _KC_NL])
def test_fallback_carries_canonical_text_for_each_kc(kc: KnowledgeComponentId) -> None:
    problem = generate_problem(kc, seed=2)
    hint = build_validated_hint(problem, HintLevel.PARTIAL_STEP)
    assert hint.kc is kc
    assert hint.natural_language == worked_example_for(problem).steps[0].shown
    assert hint.llm_used is False


@pytest.mark.parametrize("kc", [_KC_ADD, _KC_SUB, _KC_EQ, _KC_NL])
def test_slots_record_canonical_numbers_for_each_kc(kc: KnowledgeComponentId) -> None:
    problem = generate_problem(kc, seed=2)
    hint = build_validated_hint(problem, HintLevel.WORKED_STEP)
    # The slots are the record of the validated symbolic facts: name → string value pairs,
    # one per distinct number in the canonical text. Hashable tuple-of-tuples.
    assert isinstance(hint.slots, tuple)
    for name, value in hint.slots:
        assert name.startswith("slot")
        assert value  # non-empty string value
    # Frozen / hashable like NudgeHint / WorkedStep.
    assert hash(hint) is not None
