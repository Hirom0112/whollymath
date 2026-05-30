"""Per-turn transcripts of the three-arm comparison, for the on-screen "benchmark
theater" (a teaching view of Slice 5.3 / PROJECT.md §3.11).

The Slice 5.3 dashboard (``three_arm_comparison`` → ``api/eval_view``) shows the
*verdicts*: did each arm wrongly certify each adversarial learner? This module gives
the step-by-step the verdict is read off of — the same persona, the same problems, run
through all three arms, recorded turn by turn — so a reader can watch *why* the adaptive
tutor denies false mastery, where a chat tutor self-certifies, and that the static
walkthrough checks nothing.

It re-uses the already-tested arm engines and re-implements none of them (CLAUDE.md §7):

  - **adaptive** — ``run_persona`` drives the persona through the reactive tutor (SymPy
    verify + §3.4 mastery rules + §3.6 policy); the verdict is ``declare_mastery`` +
    ``run_transfer_probe`` (exactly ``false_positive_harness.measure_case``'s two-stage
    gate, inlined here so the per-turn run and its verdict come from one pass).
  - **chat** — ``run_chat_session`` with the ``IllustrativeChatProvider`` (NO live LLM,
    so the view is free and deterministic). The per-turn tutor *wording* is therefore a
    labelled placeholder, NOT a model run; the REAL chat signal — whether it self-
    certified mastery — comes from the committed live run (``chat_baseline_run.json``)
    or the §9 prediction, never invented here (CLAUDE.md §5, §8).
  - **static** — ``run_static_session`` (a fixed worked-example walkthrough, no verify,
    no mastery).

Boundaries: NO SymPy and NO mastery logic of its own (it calls the domain verifier and
mastery model through the arm engines), and NO live LLM (the chat provider is canned).
Deterministic: same persona ⇒ same transcript every call (every underlying piece is).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sympy import Rational

from app.domain.problem_generators import Problem, generate_problem
from app.eval.chat_baseline import ChatTurn, run_chat_session
from app.eval.false_positive_harness import PersonaCase, harness_cases
from app.eval.static_worked_example import StaticTurn, run_static_session
from app.eval.three_arm_comparison import load_recorded_chat_run
from app.llm.provider import Message, Tier
from app.mastery.mastery_model import declare_mastery
from app.personas.run import PersonaRun, run_persona
from app.tutor.transfer_probe import (
    TransferItemOutcome,
    build_error_finding_transfer_item,
    build_representation_transfer_item,
    run_transfer_probe,
)

# Neutral, conversational placeholders for the chat arm's tutor turns. They deliberately
# do NOT assert a grade: we cannot run the live model for free, so putting a specific
# "that's right/wrong" in its mouth would misrepresent it (CLAUDE.md §5, §8.2 — the LLM
# never decides correctness here, and we never fake what it said). The view labels these
# as illustrative; the arm's REAL signal is its self-certification verdict, taken from the
# committed live run. They cycle by turn only so a multi-turn chat does not read as a stuck
# loop.
_ILLUSTRATIVE_CHAT_REPLIES = (
    "Thanks for sharing your answer! Let's keep going — ready for the next one? 😊",
    "Okay, got it. Tell me a bit about how you worked that out!",
    "Nice — let's move on to the next problem together.",
    "Cool, thanks for that! Here's another one for you.",
)


class IllustrativeChatProvider:
    """A no-LLM stand-in ``LLMProvider`` for the offline benchmark theater.

    Returns canned, grade-neutral chat replies (``_ILLUSTRATIVE_CHAT_REPLIES``) instead of
    calling a model, so the view renders the *shape* of a chat session for free and
    deterministically. It is NOT the chat baseline's real behaviour — the real arm calls a
    live model that judges correctness itself (the whole point of the control, RESEARCH.md
    §2.1) — which is why the view marks every reply as illustrative and reads the real
    mastery verdict from the recorded live run, not from these strings (CLAUDE.md §5).
    """

    def __init__(self) -> None:
        self._turn = 0

    def complete(
        self,
        messages: list[Message],
        *,
        tier: Tier,
        system: str | None = None,
        max_tokens: int = 1024,
    ) -> str:
        reply = _ILLUSTRATIVE_CHAT_REPLIES[self._turn % len(_ILLUSTRATIVE_CHAT_REPLIES)]
        self._turn += 1
        return reply


def _render_answer(value: Rational | None) -> str:
    """Render a submitted answer the way the learner would have entered it (or '—' for
    no answer): a bare integer when whole, else ``p/q``."""
    if value is None:
        return "—"
    return str(value.p) if value.q == 1 else f"{value.p}/{value.q}"


@dataclass(frozen=True)
class AdaptiveTurn:
    """One adaptive-arm turn: the problem, the persona's answer, and the tutor's verified
    response (the SymPy verdict, the labelled error class, the one-line feedback, the
    resulting surface state, and whether the attempt was hinted / below the engagement
    floor)."""

    problem_statement: str
    surface_format: str
    student_answer: str
    correct: bool
    error_category: str
    feedback: str
    surface_state: str
    hint_used: bool
    latency_ms: int


@dataclass(frozen=True)
class TransferProbeStep:
    """One item of the S5 transfer probe, made visible (PROJECT.md §3.9).

    The transfer probe is the step that catches a learner who answers correctly but does
    not understand — so the theater shows it, not just its verdict. ``item_type`` is
    ``representation`` (same skill, new format) or ``error_finding`` ("Tim says ¼+¼=2/8 —
    why is he wrong?"); ``prompt`` is what the learner was shown; ``passed`` is the per-item
    verdict; ``detail`` is a plain-language line on what the persona did.
    """

    item_type: str
    prompt: str
    surface_format: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class PersonaTranscript:
    """One persona run through all three arms, turn by turn, with each arm's verdict.

    Frozen. The ``adaptive_*`` verdict fields are exactly ``measure_case``'s two-stage
    gate (provisional ``declare_mastery`` then the S5 ``run_transfer_probe``); when the
    persona reaches provisional, ``adaptive_probe_steps`` records the transfer-probe items
    that confirmed or denied it. The ``chat_*`` verdict is the recorded LIVE
    self-certification (or the §9 prediction when no live run is committed), never the
    illustrative replies; static has no verdict by construction.
    """

    persona_id: str
    persona_name: str
    attacks: str
    kc: str
    problems: tuple[str, ...]

    adaptive_turns: tuple[AdaptiveTurn, ...]
    adaptive_provisional: bool
    adaptive_confirmed: bool
    adaptive_blocked_at: str
    adaptive_reasons: tuple[str, ...]
    adaptive_probe_ran: bool
    adaptive_probe_steps: tuple[TransferProbeStep, ...]

    chat_turns: tuple[ChatTurn, ...]
    chat_claimed_mastery: bool | None
    chat_self_assessment: str
    chat_live: bool

    static_turns: tuple[StaticTurn, ...]


@dataclass(frozen=True)
class PersonaSummary:
    """The persona-switcher entry: who, and the one mastery dimension they attack."""

    persona_id: str
    persona_name: str
    attacks: str
    kc: str


def persona_summaries() -> list[PersonaSummary]:
    """The five adversarial personas, in harness order, for the switcher (PROJECT.md §4.2)."""
    return [
        PersonaSummary(
            persona_id=case.persona.persona_id,
            persona_name=case.persona.name,
            attacks=case.attacked_dimension,
            kc=case.kc.value,
        )
        for case in harness_cases()
    ]


def _problems_for(case: PersonaCase) -> list[Problem]:
    """The concrete ``Problem`` objects the case's spec sequence names (same items every arm)."""
    return [generate_problem(s.kc, s.seed, s.surface_format) for s in case.sequence]


def _adaptive_turns(run: PersonaRun) -> list[AdaptiveTurn]:
    """Map a recorded persona run to per-turn adaptive rows (skip pure-explain turns with
    no verified result — the harness sequences submit an answer every turn)."""
    rows: list[AdaptiveTurn] = []
    for turn in run.turns:
        if turn.result is None:
            continue
        rows.append(
            AdaptiveTurn(
                problem_statement=turn.problem.statement,
                surface_format=turn.problem.surface_format.value,
                student_answer=_render_answer(turn.action.submitted_answer),
                correct=turn.result.correct,
                error_category=turn.result.error_category.value,
                feedback=turn.result.feedback,
                surface_state=turn.result.surface_state.value,
                hint_used=turn.action.requested_hint,
                latency_ms=int(turn.action.think_time_seconds * 1000),
            )
        )
    return rows


@dataclass(frozen=True)
class _AdaptiveOutcome:
    """The full adaptive verdict for one run: the two-stage gate plus the visible probe."""

    provisional: bool
    confirmed: bool
    blocked_at: str
    reasons: tuple[str, ...]
    probe_ran: bool
    probe_steps: tuple[TransferProbeStep, ...]


def _representation_detail(outcome: TransferItemOutcome) -> str:
    """Plain line for the representation item: did the skill survive a new format?"""
    answer = _render_answer(outcome.submitted_answer)
    if outcome.passed:
        return f"Solved it in the new format ({answer}) — the skill held up."
    return f"Got {answer} in the new format — the skill didn't transfer."


def _error_finding_detail(outcome: TransferItemOutcome) -> str:
    """Plain line for the error-finding item: catch AND explain the mistake?"""
    if outcome.passed:
        return "Caught the wrong answer and explained why — real understanding."
    if not outcome.can_justify:
        return "Couldn't explain why it's wrong — ran the steps without understanding them."
    return "Didn't reject the wrong answer."


def _adaptive_outcome(case: PersonaCase, run: PersonaRun) -> _AdaptiveOutcome:
    """The two-stage adaptive verdict for this run (mirrors ``measure_case``), plus the
    transfer-probe items made visible when the run reaches provisional.

    Stage 1 is ``declare_mastery`` over the run's observations; only if it passes does the
    S5 transfer probe run as the confirm-or-demote gate (§3.9). The probe items are rebuilt
    (same default seeds ⇒ identical items) so their prompts can be shown alongside the
    verdicts ``run_transfer_probe`` returns.
    """
    provisional, reasons = declare_mastery(case.kc, run.observations)
    if not provisional:
        return _AdaptiveOutcome(False, False, "provisional", tuple(reasons), False, ())

    repr_item = build_representation_transfer_item(
        case.kc, recent_format=case.recent_format, seed=0
    )
    err_item = build_error_finding_transfer_item(case.kc, seed=0)
    probe = run_transfer_probe(case.persona, case.kc, recent_format=case.recent_format)

    steps = (
        TransferProbeStep(
            item_type="representation",
            prompt=repr_item.problem.statement,
            surface_format=repr_item.problem.surface_format.value,
            passed=probe.representation.passed,
            detail=_representation_detail(probe.representation),
        ),
        TransferProbeStep(
            item_type="error_finding",
            prompt=err_item.problem.statement,
            surface_format=err_item.problem.surface_format.value,
            passed=probe.error_finding.passed,
            detail=_error_finding_detail(probe.error_finding),
        ),
    )

    if probe.passed:
        return _AdaptiveOutcome(True, True, "NOT BLOCKED", (), True, steps)
    probe_reason = (
        f"transfer probe failed: representation_passed={probe.representation.passed}, "
        f"error_finding_passed={probe.error_finding.passed} "
        f"(can_justify={probe.error_finding.can_justify})"
    )
    return _AdaptiveOutcome(True, False, "transfer_probe", (probe_reason,), True, steps)


def _chat_verdict(
    persona_id: str, recorded_run: dict[str, Any] | None
) -> tuple[bool | None, str, bool]:
    """The chat arm's REAL mastery signal for this persona.

    Returns ``(claimed_mastery, self_assessment, live)``. From the committed live run if we
    have one (``claimed_mastery`` true/false + its ``MASTERED``/``NOT_YET`` word); otherwise
    the §9 prediction (``None`` = not measured), so we never invent a verdict (CLAUDE.md §5).
    """
    if recorded_run is not None:
        results = recorded_run.get("results", {})
        assert isinstance(results, dict)
        rec = results.get(persona_id)
        if rec is not None:
            return bool(rec["claimed_mastery"]), str(rec["self_assessment"]), True
    return None, "predicted (no live run committed)", False


def build_persona_transcript(persona_id: str) -> PersonaTranscript | None:
    """Run one persona through all three arms and record every turn + each arm's verdict.

    ``None`` when ``persona_id`` is not one of the five harness personas (the route maps
    that to a 404). Deterministic and free: the adaptive and static arms are pure, and the
    chat arm uses the canned ``IllustrativeChatProvider`` (no live LLM call).
    """
    case = next((c for c in harness_cases() if c.persona.persona_id == persona_id), None)
    if case is None:
        return None

    problems = _problems_for(case)

    run = run_persona(case.persona, case.sequence)
    adaptive = _adaptive_outcome(case, run)

    chat_turns = run_chat_session(case.persona, problems, provider=IllustrativeChatProvider())
    static_turns = run_static_session(case.persona, problems)

    claimed, self_assessment, chat_live = _chat_verdict(persona_id, load_recorded_chat_run())

    return PersonaTranscript(
        persona_id=case.persona.persona_id,
        persona_name=case.persona.name,
        attacks=case.attacked_dimension,
        kc=case.kc.value,
        problems=tuple(p.statement for p in problems),
        adaptive_turns=tuple(_adaptive_turns(run)),
        adaptive_provisional=adaptive.provisional,
        adaptive_confirmed=adaptive.confirmed,
        adaptive_blocked_at=adaptive.blocked_at,
        adaptive_reasons=adaptive.reasons,
        adaptive_probe_ran=adaptive.probe_ran,
        adaptive_probe_steps=adaptive.probe_steps,
        chat_turns=tuple(chat_turns),
        chat_claimed_mastery=claimed,
        chat_self_assessment=self_assessment,
        chat_live=chat_live,
        static_turns=tuple(static_turns),
    )


__all__ = [
    "AdaptiveTurn",
    "IllustrativeChatProvider",
    "PersonaSummary",
    "PersonaTranscript",
    "TransferProbeStep",
    "build_persona_transcript",
    "persona_summaries",
]
