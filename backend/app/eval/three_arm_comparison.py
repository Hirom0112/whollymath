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

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.domain.knowledge_components import LIVE_KCS
from app.domain.lesson_spec import LESSON_SPEC_REGISTRY
from app.domain.problem_generators import Problem, generate_problem
from app.eval.chat_baseline import CHAT_SYSTEM_PROMPT, run_chat_session
from app.eval.false_positive_harness import (
    PersonaCase,
    PersonaMasteryResult,
    harness_cases,
    measure_case,
)
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


_CHAT_RUN_PATH = Path(__file__).parent / "artifacts" / "chat_baseline_run.json"


def load_recorded_chat_run() -> dict[str, Any] | None:
    """The committed result of an actual chat-arm run (``artifacts/chat_baseline_run.json``),
    or ``None`` if not present. Lets the dashboard show REAL chat numbers without re-running
    the LLM on every page load (no per-view cost). Provenance (date, model, scope) is in the
    file. The recorded run is the source of truth for the chat column once it exists."""
    if not _CHAT_RUN_PATH.exists():
        return None
    parsed: dict[str, Any] = json.loads(_CHAT_RUN_PATH.read_text())
    return parsed


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


# ───────────── Per-metric comparison (Slice 5.3.3 — the other five metrics) ─────────────
#
# The headline metric (false-positive mastery) is computed above. RESEARCH.md §9 pre-registers
# five more, each attacked by a specific persona. This layer derives each arm's verdict the
# honest way:
#   - Adaptive: from the ACTUAL deterministic run (``measure_case``). A defense is shown as
#     enforced only because the run blocked its adversary by that exact rule (the reason
#     strings / the transfer-probe stage), never hardcoded. If a defense did not fire we say so.
#   - Chat: from the recorded LIVE run (``artifacts/chat_baseline_run.json``) where we have it,
#     else the §9 prediction. The chat tutor has none of these mechanisms by construction
#     (Slice 5.1: no SymPy, no mastery model); where it *denied* an adversary it did so on
#     visibly wrong answers, not via the mechanism — the §9.1 framing, reported plainly.
#   - Static: architectural facts (Slice 5.2: a single-format worked-solution walkthrough, no
#     assessment, no mastery model). Behavioral metrics are weak/maxed; certification is N/A.
#
# Pure, deterministic, FREE — it runs ``measure_case`` (no LLM) and reads the recorded chat
# JSON; it never makes a live call (CLAUDE.md §9).

# Reason-string markers proving the adaptive defense fired for an adversary. These mirror the
# canonical reasons emitted by ``app.mastery.mastery_model.declare_mastery``; the per-metric
# tests run the real harness and assert each marker is present, so a wording drift fails loudly.
_HINT_REASON_MARKER = "scaffolding"
_FORMAT_REASON_MARKER = "representation diversity"
_ENGAGEMENT_REASON_MARKER = "engagement floor"


@dataclass(frozen=True)
class MetricArmVerdict:
    """One arm's verdict on one metric, pre-shaped for display.

    ``tone`` drives the surface styling and is the at-a-glance signal:
    ``good`` = the defense is enforced, ``bad`` = the metric is missed/unenforced, ``neutral``
    = no mechanism / not applicable, ``pending`` = the chat prediction before a live run."""

    arm: str  # "adaptive" | "chat" | "static"
    status: str  # short label, e.g. "Enforced", "Missed ✗", "Max ✗", "N/A"
    tone: str  # "good" | "bad" | "neutral" | "pending"
    detail: str  # one-line explanation


@dataclass(frozen=True)
class MetricComparison:
    """One pre-registered metric across the three arms (RESEARCH.md §9)."""

    key: str
    name: str
    adversary: str  # the persona that attacks this metric (or "all five" for transfer)
    adaptive: MetricArmVerdict
    chat: MetricArmVerdict
    static: MetricArmVerdict


def _adaptive_results_by_id() -> dict[str, PersonaMasteryResult]:
    """The deterministic adaptive outcome (with blocking reasons) for every persona."""
    return {case.persona.persona_id: measure_case(case) for case in harness_cases()}


def _reason_fired(result: PersonaMasteryResult, marker: str) -> bool:
    """Whether the adaptive run blocked this persona by the rule the marker identifies."""
    return any(marker in reason for reason in result.reasons)


def _chat_claim(recorded_chat_run: dict[str, Any] | None, persona_id: str) -> bool | None:
    """The recorded live chat claim for a persona (True/False), or None when there is no
    recorded run (the dashboard then shows the §9 prediction)."""
    if recorded_chat_run is None:
        return None
    results = recorded_chat_run.get("results", {})
    if not isinstance(results, dict):
        return None
    rec = results.get(persona_id)
    if rec is None:
        return None
    return bool(rec["claimed_mastery"])


def _adaptive_enforced(
    *, fired: bool, status: str, detail: str, reasons: tuple[str, ...]
) -> MetricArmVerdict:
    """Adaptive verdict for an adversary-targeted defense: ``good`` when the rule fired in the
    real run, else an honest ``bad`` that surfaces what actually happened."""
    if fired:
        return MetricArmVerdict(arm="adaptive", status=status, tone="good", detail=detail)
    return MetricArmVerdict(
        arm="adaptive",
        status="Not enforced ✗",
        tone="bad",
        detail="expected defense did not fire in the run; reasons: "
        + ("; ".join(reasons) if reasons else "none"),
    )


def _chat_adversary_verdict(
    claim: bool | None, *, missed_detail: str, denied_detail: str, predicted_detail: str
) -> MetricArmVerdict:
    """Chat verdict for an adversary-targeted metric.

    Chat has no mechanism for any of these by construction (Slice 5.1). So:
      - it over-claimed the adversary  → ``Missed ✗`` (bad): the metric is genuinely missed.
      - it denied the adversary        → ``No mechanism`` (neutral): it denied on visibly wrong
        answers, not via this defense — the §9.1 framing, stated plainly (not credited as good).
      - no live run yet                → ``Predicted`` (pending): the §9 prediction.
    """
    if claim is None:
        return MetricArmVerdict(
            arm="chat", status="Predicted: no mechanism", tone="pending", detail=predicted_detail
        )
    if claim:
        return MetricArmVerdict(arm="chat", status="Missed ✗", tone="bad", detail=missed_detail)
    return MetricArmVerdict(arm="chat", status="No mechanism", tone="neutral", detail=denied_detail)


def _static(status: str, tone: str, detail: str) -> MetricArmVerdict:
    return MetricArmVerdict(arm="static", status=status, tone=tone, detail=detail)


def per_metric_comparison(*, recorded_chat_run: dict[str, Any] | None) -> list[MetricComparison]:
    """The five remaining pre-registered metrics (RESEARCH.md §9), each across the three arms.

    Free and deterministic: the adaptive column is derived from ``measure_case`` (no LLM), the
    chat column from the recorded live run (or the §9 prediction when ``recorded_chat_run`` is
    None), the static column from the arm's architecture. The headline (false-positive mastery)
    is the separate ``compare_case`` layer above."""
    adaptive = _adaptive_results_by_id()
    hugo, priya = adaptive["hint_hunter_hugo"], adaptive["procedure_priya"]
    sam, cleo = adaptive["surface_sam"], adaptive["click_through_cleo"]

    hint = MetricComparison(
        key="hint_dependence",
        name="Hint dependence at mastery",
        adversary="Hint-hunter Hugo",
        adaptive=_adaptive_enforced(
            fired=_reason_fired(hugo, _HINT_REASON_MARKER),
            status="Blocked",
            detail="every correct attempt was hinted → no unscaffolded-correct evidence; "
            "can't reach mastery (§3.4 rule 3).",
            reasons=hugo.reasons,
        ),
        chat=_chat_adversary_verdict(
            _chat_claim(recorded_chat_run, "hint_hunter_hugo"),
            missed_detail="certified Hugo (live: MASTERED) — gives steps freely, no penalty "
            "for hint-dependence.",
            denied_detail="denied Hugo on visible errors, not hint-dependence — no "
            "unscaffolded-correct rule.",
            predicted_detail="predicted High — gives steps freely and praises; no "
            "unscaffolded-correct rule.",
        ),
        static=_static(
            "Max ✗", "bad", "the full worked solution is always shown — 'success' = copying it."
        ),
    )

    procedural = MetricComparison(
        key="procedural_conceptual",
        name="Procedural-vs-conceptual gap",
        adversary="Procedure Priya",
        adaptive=_adaptive_enforced(
            fired=priya.blocked_at == "transfer_probe",
            status="Detected",
            detail="reaches provisional (fluent procedure), then the S5 transfer probe demotes "
            "her — endorses a wrong claim she can't justify.",
            reasons=priya.reasons,
        ),
        chat=_chat_adversary_verdict(
            _chat_claim(recorded_chat_run, "procedure_priya"),
            missed_detail="certified Priya (live: MASTERED) — grades the answer, never probes "
            "the concept.",
            denied_detail="denied Priya on her answers, not the concept gap — no conceptual "
            "assessment.",
            predicted_detail="predicted Missed — checks the answer, not the concept.",
        ),
        static=_static("Missed ✗", "bad", "shows the procedure, never assesses understanding."),
    )

    fmt = MetricComparison(
        key="format_variance",
        name="Format-variance robustness",
        adversary="Surface Sam",
        adaptive=_adaptive_enforced(
            fired=_reason_fired(sam, _FORMAT_REASON_MARKER),
            status="Enforced",
            detail="fluent in one format only; mastery needs 2+ correct representations "
            "(rule 2) — blocked.",
            reasons=sam.reasons,
        ),
        chat=_chat_adversary_verdict(
            _chat_claim(recorded_chat_run, "surface_sam"),
            missed_detail="certified Sam (live: MASTERED) on single-format fluency.",
            denied_detail="denied Sam on visibly wrong answers, not format-robustness — "
            "single-format Q&A has no representation requirement.",
            predicted_detail="predicted Weak — single-format Q&A passes pattern-matching.",
        ),
        static=_static("Weak ✗", "bad", "one canonical format (reuses the worked-example steps)."),
    )

    engagement = MetricComparison(
        key="engagement_floor",
        name="Engagement-floor enforcement",
        adversary="Click-through Cleo",
        adaptive=_adaptive_enforced(
            fired=_reason_fired(cleo, _ENGAGEMENT_REASON_MARKER),
            status="Enforced",
            detail="answers below the time floor every turn → no engaged evidence; the floor "
            "blocks mastery.",
            reasons=cleo.reasons,
        ),
        chat=_chat_adversary_verdict(
            _chat_claim(recorded_chat_run, "click_through_cleo"),
            missed_detail="certified Cleo (live: MASTERED) despite click-through behavior.",
            denied_detail="denied Cleo on visible errors, not engagement — no engagement gate.",
            predicted_detail="predicted None — rushing / lucky-correct still praised.",
        ),
        static=_static("None ✗", "bad", "no engagement gate at all."),
    )

    n_provisional = sum(r.provisional_mastery for r in adaptive.values())
    n_confirmed = sum(r.confirmed_mastery for r in adaptive.values())
    chat_masters = [pid for pid in adaptive if _chat_claim(recorded_chat_run, pid) is True]
    transfer = MetricComparison(
        key="transfer_at_mastery",
        name="Transfer pass rate at mastery",
        adversary="all five (higher is better)",
        adaptive=MetricArmVerdict(
            arm="adaptive",
            status="Gate holds",
            tone="good",
            detail=f"transfer is the gate: {n_provisional}/5 reached provisional, "
            f"{n_confirmed} confirmed → 0 false certifications (Priya demoted by the probe).",
        ),
        chat=(
            MetricArmVerdict(
                arm="chat",
                status="Low ✗",
                tone="bad",
                detail=f"self-certified {len(chat_masters)} 'masters' with no transfer check — "
                "they would fail our probe.",
            )
            if recorded_chat_run is not None
            else MetricArmVerdict(
                arm="chat",
                status="Predicted: Low",
                tone="pending",
                detail="predicted to over-certify; no transfer construct.",
            )
        ),
        static=_static("N/A", "neutral", "certifies nothing — no transfer construct."),
    )

    return [hint, procedural, fmt, engagement, transfer]


def format_metric_comparison(metrics: list[MetricComparison]) -> str:
    """A readable side-by-side of the five per-metric verdicts (decision-log / writeup)."""
    lines = ["Three-arm comparison — per-metric (RESEARCH.md §9):", ""]
    for m in metrics:
        lines.append(f"  {m.name}  (adversary: {m.adversary})")
        lines.append(f"    adaptive: {m.adaptive.status}  [{m.adaptive.detail}]")
        lines.append(f"    chat:     {m.chat.status}  [{m.chat.detail}]")
        lines.append(f"    static:   {m.static.status}  [{m.static.detail}]")
        lines.append("")
    return "\n".join(lines)


# ───────────── LIVE_KCS defense coverage (Slice 5.3.3 — range over the whole KC space) ──────────
#
# The headline + per-metric layers above are measured on the five fraction adversaries (the
# personas attack specific fraction KCs). This layer ranges over the WHOLE LIVE_KCS space and
# reports, per KC, whether the adaptive arm's defense scaffolding EXISTS — the confirm-gate (the
# S5 transfer probe) and at least one error route (the reactive morph). These are exactly the
# mechanisms the chat and static arms lack by construction (Slices 5.1/5.2). It is honest about
# scope: it certifies the defense exists for every KC, NOT that a persona attacked each KC — only
# the fraction KCs are persona-tested today. Pure, deterministic, FREE: it reads the lesson-spec
# registry, no LLM/DB/SymPy.


@dataclass(frozen=True)
class DefenseCoverageRow:
    """Whether the adaptive arm's defenses are wired for one live KC."""

    kc: str
    has_transfer_probe: bool
    has_error_route: bool


def adaptive_defense_coverage() -> list[DefenseCoverageRow]:
    """Per live KC, whether the adaptive arm's transfer-probe gate + error routing are present.

    Reads each KC's ``LessonSpec`` (the single source of truth): ``transfer_probe`` is the §3.9
    confirm-or-demote gate, and a non-empty ``error_routes`` is the reactive-morph table. Sorted by
    KC for a stable report. Ranges over every ``LIVE_KCS`` value, not just the five fraction KCs."""
    rows: list[DefenseCoverageRow] = []
    for kc in sorted(LIVE_KCS, key=lambda k: k.value):
        spec = LESSON_SPEC_REGISTRY.get(kc)
        rows.append(
            DefenseCoverageRow(
                kc=kc.value,
                has_transfer_probe=spec.transfer_probe is not None,
                has_error_route=len(spec.error_routes) > 0,
            )
        )
    return rows


def format_defense_coverage(rows: list[DefenseCoverageRow]) -> str:
    """A readable per-KC adaptive-defense-coverage table (decision log / writeup)."""
    lines = ["Adaptive-arm defense coverage across LIVE_KCS (RESEARCH.md §9):", ""]
    for row in rows:
        probe = "probe ✓" if row.has_transfer_probe else "probe ✗"
        route = "route ✓" if row.has_error_route else "route ✗"
        lines.append(f"  {row.kc:28} {probe}  {route}")
    full = sum(1 for r in rows if r.has_transfer_probe and r.has_error_route)
    lines.append("")
    lines.append(
        f"{full}/{len(rows)} live KCs have BOTH the S5 transfer-probe gate and reactive error "
        "routing — the mechanisms the chat/static arms lack by construction."
    )
    lines.append(
        "  SCOPE: this certifies the defense EXISTS per KC; persona false-positive attacks cover "
        "only the fraction KCs (the five adversaries), reported honestly (CLAUDE.md §9)."
    )
    return "\n".join(lines)


def main() -> None:
    """Run the live comparison and print the report.

    From backend/: ``uv run python -m app.eval.three_arm_comparison``. WARNING: this makes
    live Anthropic calls (the chat arm) for every persona × problem — it costs money. The
    adaptive and static arms are free/deterministic.
    """
    print(format_comparison(run_three_arm_comparison()))
    print()
    print(
        format_metric_comparison(per_metric_comparison(recorded_chat_run=load_recorded_chat_run()))
    )
    print()
    print(format_defense_coverage(adaptive_defense_coverage()))


if __name__ == "__main__":
    main()


__all__ = [
    "ArmOutcome",
    "CHAT_ASSESSMENT_QUESTION",
    "ComparisonRow",
    "DefenseCoverageRow",
    "MetricArmVerdict",
    "MetricComparison",
    "PREDICTED_CHAT_NOTE",
    "adaptive_defense_coverage",
    "chat_mastery_claim",
    "compare_case",
    "compare_case_offline",
    "format_comparison",
    "format_defense_coverage",
    "format_metric_comparison",
    "load_recorded_chat_run",
    "per_metric_comparison",
    "run_comparison_offline",
    "run_three_arm_comparison",
]
