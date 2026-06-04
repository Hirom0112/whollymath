"""End-to-end "every live lesson actually works" smoke harness (production-readiness gate).

This is the AUTOMATED, deterministic proof that the full student loop —
generate → present → grade → advance — works through the REAL API boundary for EVERY live
Knowledge Component and EVERY playable catalog lesson, not just in unit tests. It is the
"it works" gate referenced by the build tracker (Phase 4): if a live KC cannot be answered
correctly through the public surface, or a playable lesson 500s, or a KC emits a widget the
frontend cannot render, this suite fails loudly rather than letting a dead-end ship.

How it drives the system (CLAUDE.md §9 — endpoints are contract-tested end-to-end):
  - Sessions and turns go through the REAL FastAPI stack via the in-process ASGI client
    (``tests.api.asgi_client``; the same transport every other API contract test uses — httpx
    is not a backend dependency, so ``TestClient`` is unavailable, see that module's docstring).
    Routing, Pydantic validation, status codes and the ``SessionStore`` seam are all exercised.
  - The CORRECT answer for an arbitrary problem is computed from the un-projected domain
    ``Problem`` the SAME app's store still holds (``SessionStore.current_problem`` — the thin read
    that exposes ``correct_value`` / ``operands`` / ``correct_points`` / … which ``ProblemView``
    deliberately drops so the wire never leaks the answer, service.py ``_problem_view`` / §8.2).
    The answer is derived from the canonical SymPy answer fields the generator computed — never
    by re-parsing the kid-facing statement — so it generalizes to all 43 KCs and all six answer
    kinds with one code path (CLAUDE.md §8.2: SymPy is the oracle; this harness only reads what
    the oracle already decided, it does not re-judge math). No LLM anywhere (§8.1).

Determinism (CLAUDE.md §9): ``start_kc`` seeds each problem from a fresh ``uuid4`` session id, so
WHICH problem is served varies run to run — but the answer is read off whatever problem was
actually served, so the PASS/FAIL verdict is invariant to the draw. We additionally pin
``random.seed`` per case so a given case replays the same sequence, making any failure reproducible.
"""

from __future__ import annotations

import random
from typing import Any

import pytest
from app.api.app import create_app
from app.api.service import SessionStore
from app.domain.curriculum import CURRICULUM, CatalogLesson
from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId
from app.domain.problem_generators import AnswerKind, Problem
from fastapi import FastAPI

from tests.api.asgi_client import post_json

# The exactly-8 answer surfaces the frontend ``selectWidget`` knows how to render
# (frontend/src/workspace/WidgetContract.ts). A live KC whose first problem resolves to anything
# else would be a dead-end in the UI — the learner could never answer it. ``yes_no`` is the
# odd one out: the frontend dispatches it on ``answer_kind == 'yes_no'`` BEFORE looking at
# ``widget_id`` (a yes/no judgment must land on buttons, never a typing surface), so for a yes/no
# problem the backend ``widget_id`` is irrelevant. The other seven are routed by ``widget_id``
# (or, for ``number_line``, by widget_id + ``tick_segments``). This mirrors ``selectWidget``.
_FRONTEND_WIDGET_IDS: frozenset[str] = frozenset(
    {
        "fraction_editor",
        "number_entry",
        "number_line",
        "expression",
        "inequality",
        "coordinate_plane",
        "classify_sets",
    }
)

# The five Unit-7 dataset KCs whose problem statement is backed by a display stimulus (a dot plot /
# data table / histogram). Their ``ProblemView`` must carry a ``stimulus`` so the surface can render
# the data, not just the prompt text (CCSS 6.SP / TEKS 6.12D).
_DATASET_STATS_KCS: frozenset[KnowledgeComponentId] = frozenset(
    {
        KnowledgeComponentId.SUMMARY_STATISTICS,
        KnowledgeComponentId.MEAN_ABSOLUTE_DEVIATION,
        KnowledgeComponentId.CENTER_SPREAD_SHAPE,
        KnowledgeComponentId.DATA_DISPLAYS,
        KnowledgeComponentId.CATEGORICAL_DATA,
    }
)

# Every live KC, as a sorted list so the parametrized case order is stable (deterministic ids).
_LIVE_KCS_SORTED: list[KnowledgeComponentId] = sorted(LIVE_KCS, key=lambda kc: kc.value)


def _correct_answer(problem: Problem) -> str:
    """The SymPy-correct answer string for ANY served problem, read off its canonical answer field.

    One code path per ``AnswerKind`` (the wire contract each KC was built to, per
    knowledge_components.py): the verifier judges a yes/no item by SymPy over ``operands`` (so we
    recompute the truth the same way ``_verify_yes_no`` does — equality, or magnitude for the
    "greater" relation), and judges the typed/structured kinds against the canonical answer the
    generator stored (``correct_expression`` / ``correct_inequality`` / ``correct_points`` /
    ``correct_sets``); the default numeric kind is graded against ``correct_value``. This reads
    what the oracle already computed — it never re-decides correctness (CLAUDE.md §8.2)."""
    kind = problem.answer_kind
    if kind is AnswerKind.YES_NO:
        operands = problem.operands
        if problem.yes_no_relation == "better_buy":
            # better-buy: operands = (qA, pA, qB, pB); Store A wins iff pA/qA < pB/qB (recomputed
            # the same way _verify_yes_no does — cross-multiplied over exact Rationals, qA, qB > 0).
            assert operands is not None and len(operands) == 4, (
                f"better-buy problem {problem.problem_id!r} must carry four operands"
            )
            qa, pa, qb, pb = operands
            truth = bool(pa * qb < pb * qa)
            return "yes" if truth else "no"
        assert operands is not None and len(operands) == 2, (
            f"yes/no problem {problem.problem_id!r} must carry two operands"
        )
        if problem.yes_no_relation == "greater":
            truth = bool(operands[0] > operands[1])
        else:
            truth = bool(operands[0] == operands[1])
        return "yes" if truth else "no"
    if kind is AnswerKind.EXPRESSION:
        assert problem.correct_expression is not None
        return problem.correct_expression
    if kind is AnswerKind.INEQUALITY:
        assert problem.correct_inequality is not None
        return problem.correct_inequality
    if kind is AnswerKind.COORDINATE:
        assert problem.correct_points is not None
        return problem.correct_points
    if kind is AnswerKind.NUMBER_SETS:
        assert problem.correct_sets is not None
        return problem.correct_sets
    # NUMERIC: the canonical Rational, written as p/q (the verifier judges by VALUE, so an
    # unreduced or whole-number form like 12/1 is accepted exactly).
    value = problem.correct_value
    return f"{value.p}/{value.q}"


def _wrong_answer(problem: Problem) -> str:
    """A deliberately WRONG answer string for a served problem — proves grading is real, not a stub.

    Each kind gets an answer guaranteed to differ from the correct one: flip a yes/no, a far-off
    inequality/coordinate, a value-shifted numeric, and for number-sets a label set that cannot
    equal the canonical membership. These are not misconception probes — just "a wrong answer must
    be rejected"."""
    kind = problem.answer_kind
    if kind is AnswerKind.YES_NO:
        return "no" if _correct_answer(problem) == "yes" else "yes"
    if kind is AnswerKind.EXPRESSION:
        return "0"  # never equivalent to a variable-bearing expression the generator emits
    if kind is AnswerKind.INEQUALITY:
        return "x > 987654"  # a bound no generated constraint uses
    if kind is AnswerKind.COORDINATE:
        return "(987,654)"  # a point no generated figure contains
    if kind is AnswerKind.NUMBER_SETS:
        # "natural" alone is wrong unless the value is a bare natural; pick a different non-empty
        # set in that one case so the answer is always a wrong, valid-vocabulary set.
        return "natural" if problem.correct_sets != "natural" else "integer,rational"
    value = problem.correct_value
    return f"{value.p + 1}/{value.q}" if value.q != 1 else f"{value.p + 7}"


def _start_kc_session(app: FastAPI, kc: KnowledgeComponentId) -> tuple[str, dict[str, Any]]:
    """Start a lesson for ``kc`` via the REAL /session endpoint; return (session_id, problem)."""
    status_code, body = post_json(app, "/session", {"kc": kc.value})
    assert status_code == 200, f"/session for {kc.value} returned {status_code}: {body}"
    assert isinstance(body, dict)
    return body["session_id"], body["problem"]


def _submit(app: FastAPI, session_id: str, problem_id: str, answer: str) -> dict[str, Any]:
    """Submit one answer through the REAL /turn endpoint; return the parsed turn response."""
    status_code, body = post_json(
        app,
        "/turn",
        {
            "session_id": session_id,
            "problem_id": problem_id,
            "action": "submit_answer",
            "submitted_answer": answer,
            "surface_state": "S1_symbolic_focus",
            "latency_ms": 5000,
            "hint_used": False,
        },
    )
    assert status_code == 200, f"/turn returned {status_code}: {body}"
    assert isinstance(body, dict)
    return body


def _store(app: FastAPI) -> SessionStore:
    """The same in-memory ``SessionStore`` the app's routes use (held on ``app.state``).

    Reading the un-projected domain ``Problem`` from here is how the harness gets the SymPy-correct
    answer the wire deliberately withholds (service.py ``_problem_view`` / §8.2) — it is the exact
    store the /turn handler grades against, so the answer we compute is the one that route judges.
    """
    store = app.state.session_store
    assert isinstance(store, SessionStore)
    return store


# ─────────────────────────── Per-KC end-to-end smoke (all 43 live KCs) ────────────────────────────


@pytest.mark.parametrize("kc", _LIVE_KCS_SORTED, ids=lambda kc: kc.value)
def test_live_kc_runs_end_to_end_through_the_api(kc: KnowledgeComponentId) -> None:
    """Every live KC: generate → present → grade-correct → advance, AND grade-wrong → reject.

    Through the REAL API for ``kc``:
      1. /session serves a first problem with a non-empty statement, a widget_id, and answer_kind.
      2. The widget_id is one the frontend actually renders (no UI dead-end) — or the problem is a
         yes/no item, which the frontend dispatches on answer_kind before widget_id (selectWidget).
      3. For the 5 dataset stats KCs the problem carries a stimulus; stat-questions is yes/no.
      4. Submitting the SymPy-correct answer is graded correct, carries a mastery snapshot, and
         either serves a next problem or completes the lesson (generate→grade→advance works).
      5. On a FRESH problem, submitting a deliberately wrong answer is graded INCORRECT (grading is
         real, not a stub that always says yes).
    """
    # Reproducible draw per case (the verdict itself is draw-invariant — see module docstring).
    random.seed(hash(kc.value) & 0xFFFF_FFFF)
    app = create_app()
    store = _store(app)

    # 1–3. Start the lesson and inspect the first problem the wire ships.
    session_id, problem_view = _start_kc_session(app, kc)
    assert problem_view["statement"].strip(), f"{kc.value}: first problem has an empty statement"
    assert problem_view["widget_id"], f"{kc.value}: first problem carries no widget_id"
    answer_kind = problem_view["answer_kind"]
    assert answer_kind, f"{kc.value}: first problem carries no answer_kind"

    # The emitted surface must be renderable by the frontend, else the lesson dead-ends in the UI.
    is_yes_no = answer_kind == "yes_no"
    assert is_yes_no or problem_view["widget_id"] in _FRONTEND_WIDGET_IDS, (
        f"{kc.value}: widget_id {problem_view['widget_id']!r} is not one the frontend renders "
        f"(answer_kind={answer_kind!r}); the lesson would be a UI dead-end"
    )

    if kc in _DATASET_STATS_KCS:
        assert problem_view["stimulus"] is not None, (
            f"{kc.value}: a dataset stats KC must ship a display stimulus, not just prompt text"
        )
    if kc is KnowledgeComponentId.STATISTICAL_QUESTIONS:
        assert answer_kind == "yes_no", (
            f"{kc.value}: must be a yes/no item (recognize a statistical question)"
        )

    # 4. Correct answer → correct, mastery present, and the journey continues (advance or complete).
    correct_problem = store.current_problem(session_id)
    assert correct_problem is not None, f"{kc.value}: store lost the live problem"
    correct_response = _submit(
        app, session_id, problem_view["problem_id"], _correct_answer(correct_problem)
    )
    assert correct_response["correct"] is True, (
        f"{kc.value}: the SymPy-correct answer was graded incorrect — the loop is broken"
    )
    assert isinstance(correct_response["mastery"], list) and correct_response["mastery"], (
        f"{kc.value}: a graded turn must carry a mastery snapshot"
    )
    advanced = correct_response["next_problem"] is not None
    completed = bool(correct_response["lesson_complete"])
    assert advanced or completed, (
        f"{kc.value}: a correct answer neither served a next problem nor completed the lesson"
    )

    # 5. A wrong answer on a FRESH problem is rejected (grading is real).
    wrong_session_id, wrong_problem_view = _start_kc_session(app, kc)
    wrong_problem = store.current_problem(wrong_session_id)
    assert wrong_problem is not None
    wrong_response = _submit(
        app, wrong_session_id, wrong_problem_view["problem_id"], _wrong_answer(wrong_problem)
    )
    assert wrong_response["correct"] is False, (
        f"{kc.value}: a deliberately wrong answer was NOT rejected — the verifier is not grading"
    )


# ──────────────────────── Catalog gating contract (every catalog lesson) ──────────────────────────


def _resolve_live_kc(kc_id: str | None) -> KnowledgeComponentId | None:
    """The live KC a catalog ``kc_id`` resolves to, or None — mirrors unit_progress._resolve_kc.

    A lesson is PLAYABLE exactly when its kc_id resolves to a member of LIVE_KCS (the authoritative
    signal the unit-progress view derives ``playable`` from). Re-deriving it here lets the test
    assert the gating contract straight from the catalog, independent of the view layer."""
    if kc_id is None:
        return None
    try:
        kc = KnowledgeComponentId(kc_id)
    except ValueError:
        return None
    return kc if kc in LIVE_KCS else None


def _all_catalog_lessons() -> list[CatalogLesson]:
    """Every lesson in the Grade-6 catalog, in teaching order (flattened across units)."""
    return [lesson for unit in CURRICULUM for lesson in unit.lessons]


@pytest.mark.parametrize("lesson", _all_catalog_lessons(), ids=lambda lesson: lesson.slug)
def test_catalog_lesson_gating_contract_holds(lesson: CatalogLesson) -> None:
    """Lock the catalog gating contract for every lesson — no lesson is mis-gated.

    A catalog lesson is in exactly one of two states, and each is justified:
      - PLAYABLE: its kc_id resolves to a live KC. The lesson MUST start through the real /session
        endpoint and serve a real first problem (no live lesson 500s, no empty statement).
      - NON-PLAYABLE: it is NOT playable for an EXPECTED reason only — ``concept_only`` (an owner
        decision it will never be a tutor lesson, DEC.FINLIT), an interleave gate (``kc_id is
        None``), or a genuinely-unbuilt-but-named KC (a ``kc_id`` that is a KnowledgeComponentId
        member outside LIVE_KCS — a forward-declared Grade-6 ontology KC not yet built).

    The forbidden state this asserts against: a lesson that is non-playable for an UNEXPECTED reason
    (a kc_id string that is not even a KnowledgeComponentId member — a typo'd / stray id that can
    never resolve). A playable lesson whose KC is not live is impossible by how ``playable`` is
    derived, and the aggregate test below pins that direction too.
    """
    resolved = _resolve_live_kc(lesson.kc_id)
    if resolved is not None:
        # PLAYABLE: the live lesson must actually start and present a real problem.
        assert resolved in LIVE_KCS  # the derivation guarantees this; assert it can't drift.
        status_code, body = post_json(create_app(), "/session", {"kc": resolved.value})
        assert status_code == 200, (
            f"playable lesson {lesson.slug} (KC {resolved.value}) failed to start: "
            f"{status_code} {body}"
        )
        assert isinstance(body, dict) and body["problem"]["statement"].strip(), (
            f"playable lesson {lesson.slug} started but served no real problem"
        )
        return

    # NON-PLAYABLE: must be one of the three sanctioned reasons, never a stray/unexpected one.
    if lesson.concept_only:
        return  # owner-decided concept lesson (no tutor mechanism by design).
    if lesson.kc_id is None:
        return  # interleave gate — no single KC.
    # The only remaining sanctioned reason: a real KnowledgeComponentId whose content is not built.
    try:
        KnowledgeComponentId(lesson.kc_id)
    except ValueError:
        pytest.fail(
            f"lesson {lesson.slug} is non-playable for an UNEXPECTED reason: kc_id "
            f"{lesson.kc_id!r} is not a KnowledgeComponentId member, not an interleave gate, and "
            f"not concept_only — a mis-gated lesson (likely a typo'd / stray KC id)."
        )


# The two live KCs deliberately NOT given their own Grade-6 catalog lesson slot. Both are original
# FOUNDATION skills (PROJECT.md §3.1's five fraction KCs) that the Grade-6 catalog reaches by other
# means, so no lesson names them as its primary ``kc_id``:
#   - KC_common_denominator is UPGRADED into the GCF/LCM lesson (curriculum.py u2_l3: "Upgrades
#     KC_common_denominator to 'find the LCM'"), which carries kc_id KC_gcf_lcm; the bare
#     common-denominator skill stays live for the remediation drop (§11) but is not its own lesson.
#   - KC_subtraction_unlike is REVIEWED inside the add/subtract review lesson (u2_l2), whose single
#     kc_id is KC_addition_unlike; subtraction stays live for remediation and direct launch.
# Both remain reachable through the public API by direct KC launch (the per-KC test above proves
# they run end-to-end) and via remediation routing — they are foundation skills, not orphaned
# content. This allowlist documents that as a deliberate gating fact, so the invariant below still
# catches a NEWLY-orphaned KC (a Grade-6 lesson KC that lost its only catalog reference).
_FOUNDATION_KCS_WITHOUT_OWN_LESSON: frozenset[str] = frozenset(
    {
        KnowledgeComponentId.COMMON_DENOMINATOR.value,
        KnowledgeComponentId.SUBTRACTION_UNLIKE.value,
    }
)


def test_every_playable_catalog_kc_is_live_and_every_live_kc_is_reachable() -> None:
    """The two-way gating invariant, asserted in aggregate (a guard against silent drift).

    Forward: every catalog lesson the surface marks PLAYABLE points at a KC in LIVE_KCS — there is
    no lesson that is playable yet backed by a KC the tutor cannot serve. Backward: every live KC is
    referenced by at least one catalog lesson, EXCEPT the two foundation skills the Grade-6 catalog
    reaches by other means (``_FOUNDATION_KCS_WITHOUT_OWN_LESSON`` — both still reachable through
    the API by direct KC launch and by remediation, just not via a dedicated lesson). This catches a
    NEWLY-orphaned Grade-6 KC (one that lost its only catalog reference) without falsely flagging
    the two documented foundation skills."""
    playable_kc_ids: set[str] = set()
    for lesson in _all_catalog_lessons():
        resolved = _resolve_live_kc(lesson.kc_id)
        if resolved is not None:
            assert lesson.kc_id == resolved.value
            playable_kc_ids.add(resolved.value)

    # Forward direction is enforced per-lesson above; here assert the backward direction, allowing
    # only the two documented foundation skills to be unreferenced by a catalog lesson.
    live_kc_ids = {kc.value for kc in LIVE_KCS}
    orphaned = live_kc_ids - playable_kc_ids - _FOUNDATION_KCS_WITHOUT_OWN_LESSON
    assert not orphaned, (
        f"live KCs are not reachable from any catalog lesson (orphaned content): {sorted(orphaned)}"
    )
