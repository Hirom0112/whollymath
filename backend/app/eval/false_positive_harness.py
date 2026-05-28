"""False-positive-mastery harness — the headline defense (Slice 4.1).

PROJECT.md §3.11 / §4: the central claim is that our mastery model does NOT declare
mastery for a learner who only *looks* fluent. The five personas are the adversaries,
each attacking a different mastery rule (CLAUDE.md §9: "the personas serve as
integration tests for the mastery model"). This harness drives every persona through
a tailored sequence and checks that each is denied **confirmed** mastery on the KC it
attacks — and records WHY it was blocked, so the writeup can show the mechanism.

Two-stage mastery (PROJECT.md §3.4, §3.9; ARCHITECTURE.md §6):
  - **provisional** — ``declare_mastery`` over the run's observations (BKT > τ AND the
    four §3.4 rules AND the engagement floor). Catches Sam (rules 2+4), Nate (rule 2),
    Hugo (rule 3), Cleo (engagement floor).
  - **confirmed** — provisional AND the S5 transfer probe passes (representation
    transfer + error-finding with justification). Catches Procedure Priya, who looks
    fluent (reaches provisional) but endorses a wrong claim she cannot justify.

A persona reaches CONFIRMED mastery only if BOTH stages pass. The defense holds when
NO persona reaches confirmed mastery on its attacked dimension. This module only
orchestrates the already-tested pieces (run_persona, declare_mastery,
run_transfer_probe) — no re-implementation, no LLM/DB/SymPy (CLAUDE.md §7).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.mastery.mastery_model import declare_mastery
from app.personas.cleo import CLEO
from app.personas.hugo import HUGO
from app.personas.nate import NATE
from app.personas.persona_config import PersonaConfig
from app.personas.priya import PRIYA
from app.personas.run import ProblemSpec, run_persona
from app.personas.sam import SAM
from app.tutor.transfer_probe import run_transfer_probe

_KC_EQ = KnowledgeComponentId.EQUIVALENCE
_KC_ADD = KnowledgeComponentId.ADDITION_UNLIKE
_KC_SUB = KnowledgeComponentId.SUBTRACTION_UNLIKE
_KC_NL = KnowledgeComponentId.NUMBER_LINE_PLACEMENT
_SYM = Representation.SYMBOLIC
_AREA = Representation.AREA_MODEL
_NL = Representation.NUMBER_LINE


@dataclass(frozen=True)
class PersonaCase:
    """One persona's adversarial run: who, which KC, the sequence, and the dimension."""

    persona: PersonaConfig
    kc: KnowledgeComponentId
    attacked_dimension: str
    sequence: list[ProblemSpec]
    recent_format: Representation


@dataclass(frozen=True)
class PersonaMasteryResult:
    """Whether one persona was (correctly) denied confirmed mastery, and why.

    ``confirmed_mastery`` is the false positive the §3.11 defense must prevent — it
    must be False for every persona. ``blocked_at`` says which stage caught it.
    """

    persona_id: str
    persona_name: str
    kc: KnowledgeComponentId
    attacked_dimension: str
    provisional_mastery: bool
    confirmed_mastery: bool
    blocked_at: str  # "provisional" | "transfer_probe" | "NOT BLOCKED"
    reasons: tuple[str, ...]


def measure_case(case: PersonaCase) -> PersonaMasteryResult:
    """Run one persona case and report whether confirmed mastery was denied."""
    run = run_persona(case.persona, case.sequence)
    provisional, reasons = declare_mastery(case.kc, run.observations)

    if not provisional:
        return PersonaMasteryResult(
            persona_id=case.persona.persona_id,
            persona_name=case.persona.name,
            kc=case.kc,
            attacked_dimension=case.attacked_dimension,
            provisional_mastery=False,
            confirmed_mastery=False,
            blocked_at="provisional",
            reasons=tuple(reasons),
        )

    # Provisional passed (the persona looks fluent) — the transfer probe is the
    # confirm-or-demote gate (§3.9). Priya is the one this stage must catch.
    probe = run_transfer_probe(case.persona, case.kc, recent_format=case.recent_format)
    if probe.passed:
        probe_reasons: tuple[str, ...] = ()
        blocked_at = "NOT BLOCKED"
    else:
        probe_reasons = (
            f"transfer probe failed: representation_passed={probe.representation.passed}, "
            f"error_finding_passed={probe.error_finding.passed} "
            f"(can_justify={probe.error_finding.can_justify})",
        )
        blocked_at = "transfer_probe"

    return PersonaMasteryResult(
        persona_id=case.persona.persona_id,
        persona_name=case.persona.name,
        kc=case.kc,
        attacked_dimension=case.attacked_dimension,
        provisional_mastery=True,
        confirmed_mastery=probe.passed,
        blocked_at=blocked_at,
        reasons=probe_reasons,
    )


def harness_cases() -> list[PersonaCase]:
    """The five adversarial cases, one per persona (PROJECT.md §4.2)."""
    return [
        # Surface Sam — fluent only in his tied symbolic format; the same KC collapses
        # to add-across in every other representation. Attacks rules 2 (diversity) + 4
        # (interleaving). Interleaved, multi-format addition (+ a subtraction item).
        PersonaCase(
            persona=SAM,
            kc=_KC_ADD,
            attacked_dimension="blocked / format-tied (rules 2 & 4)",
            sequence=[
                ProblemSpec(kc=_KC_ADD, seed=1, surface_format=_SYM),
                ProblemSpec(kc=_KC_SUB, seed=2, surface_format=_SYM),
                ProblemSpec(kc=_KC_ADD, seed=3, surface_format=_AREA),
                ProblemSpec(kc=_KC_ADD, seed=4, surface_format=_NL),
                ProblemSpec(kc=_KC_ADD, seed=5, surface_format=_SYM),
            ],
            recent_format=_SYM,
        ),
        # Natural-number Nate — correct on symbolic equivalence (surface pattern), wrong
        # when the SAME KC is shown as an area model. Attacks rule 2 (single rep).
        PersonaCase(
            persona=NATE,
            kc=_KC_EQ,
            attacked_dimension="single representation (rule 2)",
            sequence=[
                ProblemSpec(kc=_KC_EQ, seed=1, surface_format=_SYM),
                ProblemSpec(kc=_KC_NL, seed=2, surface_format=_NL),
                ProblemSpec(kc=_KC_EQ, seed=3, surface_format=_AREA),
                ProblemSpec(kc=_KC_EQ, seed=4, surface_format=_SYM),
            ],
            recent_format=_SYM,
        ),
        # Hint-hunter Hugo — correct only WITH a hint; every correct attempt is scaffolded.
        # Attacks rule 3 (≥1 unscaffolded correct).
        PersonaCase(
            persona=HUGO,
            kc=_KC_ADD,
            attacked_dimension="hint-dependent (rule 3)",
            sequence=[
                ProblemSpec(kc=_KC_ADD, seed=1, surface_format=_SYM),
                ProblemSpec(kc=_KC_SUB, seed=2, surface_format=_SYM),
                ProblemSpec(kc=_KC_ADD, seed=3, surface_format=_AREA),
                ProblemSpec(kc=_KC_ADD, seed=4, surface_format=_SYM),
            ],
            recent_format=_SYM,
        ),
        # Click-through Cleo — answers below the engagement floor every turn; no engaged
        # evidence. Attacks the engagement-floor rule.
        PersonaCase(
            persona=CLEO,
            kc=_KC_ADD,
            attacked_dimension="low-engagement (engagement floor)",
            sequence=[
                ProblemSpec(kc=_KC_ADD, seed=1, surface_format=_SYM),
                ProblemSpec(kc=_KC_SUB, seed=2, surface_format=_SYM),
                ProblemSpec(kc=_KC_ADD, seed=3, surface_format=_AREA),
                ProblemSpec(kc=_KC_ADD, seed=4, surface_format=_SYM),
            ],
            recent_format=_SYM,
        ),
        # Procedure Priya — genuinely fluent across representations (reaches PROVISIONAL),
        # but cannot justify and endorses a wrong claim on error-finding. Only the
        # transfer probe catches her. Attacks the procedure-without-concept dimension.
        PersonaCase(
            persona=PRIYA,
            kc=_KC_ADD,
            attacked_dimension="procedure-without-concept (transfer probe)",
            sequence=[
                ProblemSpec(kc=_KC_ADD, seed=1, surface_format=_SYM),
                ProblemSpec(kc=_KC_SUB, seed=2, surface_format=_SYM),
                ProblemSpec(kc=_KC_ADD, seed=3, surface_format=_AREA),
                ProblemSpec(kc=_KC_ADD, seed=4, surface_format=_NL),
                ProblemSpec(kc=_KC_ADD, seed=5, surface_format=_SYM),
            ],
            recent_format=_SYM,
        ),
    ]


def run_false_positive_harness() -> list[PersonaMasteryResult]:
    """Measure all five personas. The defense holds iff no result is confirmed-mastered."""
    return [measure_case(case) for case in harness_cases()]


def format_report(results: list[PersonaMasteryResult]) -> str:
    """A readable table of the harness outcome for the decision log / writeup."""
    lines = ["False-positive-mastery harness (PROJECT.md §3.11):", ""]
    for r in results:
        verdict = "CONFIRMED ✗ (FALSE POSITIVE!)" if r.confirmed_mastery else "denied ✓"
        lines.append(f"  {r.persona_name}  [{r.kc.value}]")
        lines.append(f"    attacks: {r.attacked_dimension}")
        lines.append(
            f"    provisional={r.provisional_mastery}  confirmed={r.confirmed_mastery}  "
            f"-> {verdict}  (blocked at: {r.blocked_at})"
        )
        for reason in r.reasons:
            lines.append(f"      - {reason}")
        lines.append("")
    all_denied = all(not r.confirmed_mastery for r in results)
    lines.append(
        f"DEFENSE {'HOLDS ✓' if all_denied else 'BROKEN ✗'}: "
        f"{sum(not r.confirmed_mastery for r in results)}/{len(results)} personas denied mastery"
    )
    return "\n".join(lines)


def main() -> None:
    """Print the harness report.

    Run from backend/: ``uv run python -m app.eval.false_positive_harness``.
    """
    print(format_report(run_false_positive_harness()))


if __name__ == "__main__":
    main()


__all__ = [
    "PersonaCase",
    "PersonaMasteryResult",
    "format_report",
    "harness_cases",
    "measure_case",
    "run_false_positive_harness",
]
