"""End-to-end session-walk tests for the tutor orchestrator (Slices 1.7, 2.6).

The tutor session loop (``app/tutor/session.py``) orchestrates the already-tested
Layer-1 domain, the mastery model, and the §3.6 adaptation policy; these tests do
NOT re-test SymPy verification, the BKT math, or the transition table row-by-row
(those have their own suites). They assert the *orchestration*:

  - the two-step cold start (locked decision 0.D.2): a kid-friendly routing
    choice seeds a BKT prior (a prior, NOT a commitment), and Turn 1 presents the
    locked calibration problem for the chosen route;
  - the session loop: present a problem, accept an answer, verify via the domain,
    build a mastery ``Observation``, update the in-session mastery view, append the
    turn to history, and report a result;
  - the REACTIVE §3.6 policy (Slice 2.6): the loop maintains the two counters
    ``next_transition`` routes on, applies the resulting transition to
    ``surface_state`` BETWEEN problems (gated by the refuse-rules), and reports the
    labeled transition on the ``TurnResult`` — so the surface may move S1↔S2↔S3↔S4.

Determinism (CLAUDE.md §2; PROJECT.md §4.1): the session is seeded, so the same
inputs walk the same path every run.
"""

from __future__ import annotations

from app.api.schemas import SurfaceState
from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.domain.verifier import ErrorCategory
from app.mastery.mastery_model import initial_prior_from_self_report
from app.tutor.session import (
    UNSURE_ROUTE,
    TutorSession,
    routing_choices,
)
from sympy import Rational

# ─── Turn 0: routing → prior seed (0.D.2) ──────────────────────────────────


def test_routing_offers_three_kc_options_plus_deemphasized_unsure() -> None:
    """The routing question offers three KC options + a de-emphasized 'I'm not
    sure' default (0.D.2). The unsure option maps to KC_equivalence and is flagged
    de-emphasized so the surface can render it lower-weight (no quiz framing)."""
    choices = routing_choices()

    kc_options = [c for c in choices if not c.is_unsure_default]
    unsure = [c for c in choices if c.is_unsure_default]

    assert len(kc_options) == 3
    assert len(unsure) == 1
    # The three real options map to distinct KCs.
    assert len({c.routes_to for c in kc_options}) == 3
    # The de-emphasized default routes to equivalence (0.D.2).
    assert unsure[0].routes_to == KnowledgeComponentId.EQUIVALENCE
    assert unsure[0] is UNSURE_ROUTE


def test_routing_into_a_kc_seeds_its_prior_above_the_unsure_default() -> None:
    """Routing into a KC seeds that KC's BKT prior ABOVE the unsure default for the
    other KCs — the self-report is a prior, not a commitment (0.D.2)."""
    session = TutorSession.cold_start(chosen_kc=KnowledgeComponentId.ADDITION_UNLIKE)

    chosen_prior = session.prior_for(KnowledgeComponentId.ADDITION_UNLIKE)
    other_prior = session.prior_for(KnowledgeComponentId.EQUIVALENCE)

    assert chosen_prior > other_prior
    # Matches the mastery model's documented seeding (single source of truth).
    assert chosen_prior == initial_prior_from_self_report(
        KnowledgeComponentId.ADDITION_UNLIKE,
        chosen_kc=KnowledgeComponentId.ADDITION_UNLIKE,
    )


def test_unsure_route_seeds_equivalence_at_the_unsure_default() -> None:
    """The 'I'm not sure' default seeds no KC above the default (chosen_kc is
    None): every prior is the unsure-default value (0.D.2)."""
    session = TutorSession.cold_start(chosen_kc=None)

    # Every KC sits at the unsure default; nothing is elevated.
    priors = {kc: session.prior_for(kc) for kc in KnowledgeComponentId}
    assert len(set(priors.values())) == 1


# ─── Turn 1: the locked calibration problem per route (0.D.2) ──────────────


def test_addition_route_calibration_is_one_third_plus_one_quarter() -> None:
    """Addition route → the locked Turn-1 calibration problem '1/3 + 1/4' (0.D.2),
    presented in S1, with the SymPy-correct value 7/12 and no preemptive hint."""
    session = TutorSession.cold_start(chosen_kc=KnowledgeComponentId.ADDITION_UNLIKE)
    problem = session.current_problem

    assert problem.kc == KnowledgeComponentId.ADDITION_UNLIKE
    assert problem.operands == (Rational(1, 3), Rational(1, 4))
    assert problem.correct_value == Rational(7, 12)
    assert session.surface_state == SurfaceState.SYMBOLIC_FOCUS
    # No hint is offered preemptively at calibration (0.D.2; refuse-rule 5).
    assert session.last_turn is None


def test_equivalence_route_calibration_is_two_thirds_equals_four_sixths() -> None:
    """Equivalence route → the locked 'is 2/3 = 4/6?' calibration item (0.D.2)."""
    session = TutorSession.cold_start(chosen_kc=KnowledgeComponentId.EQUIVALENCE)
    problem = session.current_problem

    assert problem.kc == KnowledgeComponentId.EQUIVALENCE
    assert problem.operands == (Rational(2, 3), Rational(4, 6))


def test_number_line_route_calibration_places_three_fifths() -> None:
    """Number-line route → place 3/5 (0.D.2): correct_value is the magnitude 3/5."""
    session = TutorSession.cold_start(chosen_kc=KnowledgeComponentId.NUMBER_LINE_PLACEMENT)
    problem = session.current_problem

    assert problem.kc == KnowledgeComponentId.NUMBER_LINE_PLACEMENT
    assert problem.correct_value == Rational(3, 5)
    assert problem.operands == (Rational(3, 5),)


def test_unsure_route_calibration_is_the_equivalence_item() -> None:
    """The 'I'm not sure'/default route uses the equivalence calibration (0.D.2)."""
    session = TutorSession.cold_start(chosen_kc=None)
    problem = session.current_problem

    assert problem.kc == KnowledgeComponentId.EQUIVALENCE
    assert problem.operands == (Rational(2, 3), Rational(4, 6))


def test_routing_choice_object_drives_cold_start() -> None:
    """cold_start accepts the RouteOption the surface returns, mapping it to its
    chosen KC (the unsure option → None, so it seeds at the unsure default)."""
    add_option = next(
        c for c in routing_choices() if c.routes_to == KnowledgeComponentId.ADDITION_UNLIKE
    )
    session = TutorSession.from_route(add_option)
    assert session.current_problem.kc == KnowledgeComponentId.ADDITION_UNLIKE

    unsure_session = TutorSession.from_route(UNSURE_ROUTE)
    # Unsure routes to equivalence as a calibration target but seeds no KC above
    # the default (it was a default, not a self-claim).
    assert unsure_session.current_problem.kc == KnowledgeComponentId.EQUIVALENCE
    priors = {kc: unsure_session.prior_for(kc) for kc in KnowledgeComponentId}
    assert len(set(priors.values())) == 1


# ─── The session loop: verify → mastery → record ───────────────────────────


def test_correct_calibration_answer_verifies_true_and_raises_mastery() -> None:
    """Submitting the correct calibration answer verifies True and raises the
    chosen KC's in-session mastery probability above its cold-start prior. A lone
    correct answer in S1 does not move the surface (§3.6: the fade rule needs 2
    unhinted corrects and only applies away from S1)."""
    session = TutorSession.cold_start(chosen_kc=KnowledgeComponentId.ADDITION_UNLIKE)
    prior = session.mastery_probability(KnowledgeComponentId.ADDITION_UNLIKE)

    result = session.submit_answer("7/12", latency_ms=8_000)

    assert result.correct is True
    assert result.error_category == ErrorCategory.NONE
    after = session.mastery_probability(KnowledgeComponentId.ADDITION_UNLIKE)
    assert after > prior
    # A single correct answer in S1 stays in S1 (no transition fired).
    assert result.surface_state == SurfaceState.SYMBOLIC_FOCUS
    assert session.surface_state == SurfaceState.SYMBOLIC_FOCUS
    assert result.transition.is_state_change is False
    # A snapshot for the answered KC is in the result.
    snapshot_kcs = {s.kc for s in result.mastery_snapshot}
    assert KnowledgeComponentId.ADDITION_UNLIKE in snapshot_kcs


def test_add_across_wrong_answer_verifies_false_with_operation_error() -> None:
    """The add-across error on 1/3 + 1/4 (= 2/7) verifies False and is classified
    OPERATION (a wrong-procedure error), per the domain verifier."""
    session = TutorSession.cold_start(chosen_kc=KnowledgeComponentId.ADDITION_UNLIKE)

    # add-across of 1/3 + 1/4 is (1+1)/(3+4) = 2/7.
    result = session.submit_answer("2/7", latency_ms=6_000)

    assert result.correct is False
    assert result.error_category == ErrorCategory.OPERATION
    # Feedback is a single non-empty line (the surface label; refuse-rule 4 shape).
    assert result.feedback
    assert "\n" not in result.feedback


def test_session_records_turns_in_order_with_state_at_time_of_turn() -> None:
    """The session records each turn in submission order, each tagged with the state
    the turn HAPPENED in (the state before that turn's transition applied).

    Both turns here started in S1 (the first turn's OPERATION error is what then
    moves the surface to S3, between problems), so both recorded turn states are S1
    even though the surface ends in S3."""
    session = TutorSession.cold_start(chosen_kc=KnowledgeComponentId.ADDITION_UNLIKE)

    session.submit_answer("2/7", latency_ms=6_000)  # add-across wrong → moves S1→S3
    session.present_problem(
        kc=KnowledgeComponentId.ADDITION_UNLIKE,
        seed=42,
        surface_format=Representation.SYMBOLIC,
    )
    correct = session.current_problem.correct_value
    session.submit_answer(f"{correct.p}/{correct.q}", latency_ms=9_000)

    history = session.history
    assert len(history) == 2
    # Recorded in order: first wrong, then correct.
    assert history[0].result.correct is False
    assert history[1].result.correct is True
    # Each turn is tagged with the state it was answered in. The first turn was in S1
    # and its OPERATION error moved the surface to S3, so the SECOND turn was in S3.
    assert history[0].surface_state == SurfaceState.SYMBOLIC_FOCUS
    assert history[1].surface_state == SurfaceState.FRACTION_BARS_PRIMARY


def test_observation_records_representation_hint_and_latency() -> None:
    """Each recorded turn carries the mastery Observation the loop built from it:
    the KC, correctness, representation, hinted flag, and latency — the fields the
    mastery model's §3.4 rules range over."""
    session = TutorSession.cold_start(chosen_kc=KnowledgeComponentId.ADDITION_UNLIKE)

    session.submit_answer("7/12", latency_ms=8_000, hint_used=True)
    obs = session.history[-1].observation

    assert obs.kc == KnowledgeComponentId.ADDITION_UNLIKE
    assert obs.correct is True
    assert obs.representation == Representation.SYMBOLIC
    assert obs.hinted is True
    assert obs.latency_ms == 8_000


def test_self_report_is_never_echoed_but_logged_as_calibration_signal() -> None:
    """0.D.2: the self-report is never referenced back to the learner; predicted-
    vs-actual is logged as a metacognitive-calibration signal only (not acted on).
    The signal records the routed KC and whether the Turn-1 attempt was correct,
    and the learner-facing feedback never mentions the route."""
    session = TutorSession.cold_start(chosen_kc=KnowledgeComponentId.ADDITION_UNLIKE)

    result = session.submit_answer("7/12", latency_ms=8_000)

    signal = session.calibration_signal
    assert signal is not None
    assert signal.self_reported_kc == KnowledgeComponentId.ADDITION_UNLIKE
    assert signal.first_attempt_correct is True
    # The feedback must not echo the route/self-report back to the learner.
    assert "addition" not in result.feedback.lower()
    assert "route" not in result.feedback.lower()


def test_present_problem_does_not_change_surface_state() -> None:
    """present_problem swaps in a fresh generated problem without changing the
    surface state — transitions apply at ANSWER time, between problems (refuse-rule
    1), never on presenting the next problem."""
    session = TutorSession.cold_start(chosen_kc=KnowledgeComponentId.EQUIVALENCE)
    session.present_problem(
        kc=KnowledgeComponentId.ADDITION_UNLIKE,
        seed=7,
        surface_format=Representation.SYMBOLIC,
    )
    assert session.current_problem.kc == KnowledgeComponentId.ADDITION_UNLIKE
    assert session.surface_state == SurfaceState.SYMBOLIC_FOCUS


# ─── The reactive §3.6 policy in the loop (Slice 2.6) ───────────────────────
#
# These assert the loop APPLIES the §3.6 transition table between problems, gated by
# the refuse-rules. They exercise the loop end-to-end, not the policy in isolation
# (transitions.py has its own row-by-row suite); the point is that the tutor
# maintains the counters next_transition needs and applies the resulting move to
# surface_state with a label.


def _present_addition(session: TutorSession, *, seed: int) -> None:
    """Present a fresh symbolic addition problem (helper for multi-turn walks)."""
    session.present_problem(
        kc=KnowledgeComponentId.ADDITION_UNLIKE,
        seed=seed,
        surface_format=Representation.SYMBOLIC,
    )


def _answer_correct(session: TutorSession, *, latency_ms: int, hint_used: bool = False) -> None:
    """Submit the current problem's correct value (helper)."""
    correct = session.current_problem.correct_value
    session.submit_answer(f"{correct.p}/{correct.q}", latency_ms=latency_ms, hint_used=hint_used)


def test_operation_error_moves_surface_from_s1_to_s3_with_label() -> None:
    """§3.6 rows 2: a single OPERATION error in S1 moves the surface to S3 (fraction
    bars), and the applied transition carries a non-empty label (refuse-rule 4)."""
    session = TutorSession.cold_start(chosen_kc=KnowledgeComponentId.ADDITION_UNLIKE)

    # add-across of 1/3 + 1/4 = 2/7 → OPERATION error.
    result = session.submit_answer("2/7", latency_ms=6_000)

    assert result.error_category == ErrorCategory.OPERATION
    assert result.surface_state == SurfaceState.FRACTION_BARS_PRIMARY
    assert session.surface_state == SurfaceState.FRACTION_BARS_PRIMARY
    assert result.transition.is_state_change is True
    assert result.transition.label  # refuse-rule 4: never present a new state unlabeled


def test_two_consecutive_errors_route_to_worked_example_s4() -> None:
    """§3.6 row 4: 2+ consecutive errors route to the worked example (S4) from any
    state — the stuck catch-all, which takes precedence over single-error routing."""
    session = TutorSession.cold_start(chosen_kc=KnowledgeComponentId.ADDITION_UNLIKE)

    session.submit_answer("2/7", latency_ms=6_000)  # error 1 → S3 (operation)
    assert session.consecutive_errors == 1
    _present_addition(session, seed=11)
    result = session.submit_answer("999/1", latency_ms=6_000)  # error 2 → stuck → S4

    assert result.correct is False
    assert session.consecutive_errors == 2
    assert result.surface_state == SurfaceState.WORKED_EXAMPLE


def test_two_unhinted_correct_in_non_s1_state_fades_to_s1() -> None:
    """§3.6 row 3: two correct, UNHINTED answers in a scaffolded state fade back to
    S1 (the quicker symbolic view). The fade only fires away from S1."""
    session = TutorSession.cold_start(chosen_kc=KnowledgeComponentId.ADDITION_UNLIKE)

    session.submit_answer("2/7", latency_ms=6_000)  # operation error → S3
    assert session.surface_state == SurfaceState.FRACTION_BARS_PRIMARY

    _present_addition(session, seed=21)
    _answer_correct(session, latency_ms=9_000)  # 1st unhinted correct in S3
    assert session.surface_state == SurfaceState.FRACTION_BARS_PRIMARY
    assert session.consecutive_correct_no_hint_in_state == 1

    _present_addition(session, seed=22)
    result = session.submit_answer(
        f"{session.current_problem.correct_value.p}/{session.current_problem.correct_value.q}",
        latency_ms=9_000,
    )  # 2nd unhinted correct in S3 → fade to S1

    # Read the post-fade state into locals so the assertions are not narrowed by the
    # earlier S3 asserts (mypy cannot see submit_answer mutate the attribute).
    final_result_state: SurfaceState = result.surface_state
    final_session_state: SurfaceState = session.surface_state
    assert final_result_state == SurfaceState.SYMBOLIC_FOCUS
    assert final_session_state == SurfaceState.SYMBOLIC_FOCUS
    # Entering the new state resets the in-state streak (§3.6 row 3 is per-state).
    assert session.consecutive_correct_no_hint_in_state == 0


def test_hinted_correct_does_not_advance_the_fade_streak() -> None:
    """§3.6 row 3 'without hints': a HINTED correct never advances the unhinted-
    correct streak, so a hinted run never fades the scaffold (defeats Hugo-style
    hint-leaning fluency masquerading as readiness)."""
    session = TutorSession.cold_start(chosen_kc=KnowledgeComponentId.ADDITION_UNLIKE)
    session.submit_answer("2/7", latency_ms=6_000)  # → S3
    assert session.surface_state == SurfaceState.FRACTION_BARS_PRIMARY

    _present_addition(session, seed=31)
    _answer_correct(session, latency_ms=9_000, hint_used=True)  # hinted correct
    _present_addition(session, seed=32)
    _answer_correct(session, latency_ms=9_000, hint_used=True)  # hinted correct

    # Two hinted corrects do NOT fade: the streak never advanced past 0.
    assert session.consecutive_correct_no_hint_in_state == 0
    assert session.surface_state == SurfaceState.FRACTION_BARS_PRIMARY


def test_correct_answer_resets_the_consecutive_error_counter() -> None:
    """A correct answer resets the consecutive-error counter, so one error then a
    correct does not later reach the 2-error stuck threshold (§3.6 row 4)."""
    session = TutorSession.cold_start(chosen_kc=KnowledgeComponentId.ADDITION_UNLIKE)

    session.submit_answer("2/7", latency_ms=6_000)  # error → errors=1, S3
    assert session.consecutive_errors == 1
    _present_addition(session, seed=41)
    _answer_correct(session, latency_ms=9_000)  # correct → errors reset
    assert session.consecutive_errors == 0


def test_interleaved_set_passed_hook_routes_to_s5() -> None:
    """The interleaved_set_passed hook hands the mastery signal to the policy and
    applies the S5 transition (§3.6 row 6). Slice 2.6 exposes the hook; the transfer
    probe itself (running S5) is Slice 3.7 — this only confirms the routing wires up."""
    session = TutorSession.cold_start(chosen_kc=KnowledgeComponentId.ADDITION_UNLIKE)

    transition = session.interleaved_set_passed(KnowledgeComponentId.ADDITION_UNLIKE)

    assert session.surface_state == SurfaceState.TRANSFER_PROBE
    assert transition.is_state_change is True
    assert transition.label


def test_reactive_walk_is_deterministic() -> None:
    """Determinism (PROJECT.md §4.1): the same answers in the same order drive the
    same surface-state walk and the same final state every run."""

    def walk() -> list[SurfaceState]:
        session = TutorSession.cold_start(chosen_kc=KnowledgeComponentId.ADDITION_UNLIKE)
        states: list[SurfaceState] = []
        session.submit_answer("2/7", latency_ms=6_000)  # operation error
        states.append(session.surface_state)
        _present_addition(session, seed=51)
        _answer_correct(session, latency_ms=9_000)
        states.append(session.surface_state)
        _present_addition(session, seed=52)
        _answer_correct(session, latency_ms=9_000)
        states.append(session.surface_state)
        return states

    assert walk() == walk()
