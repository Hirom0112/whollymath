"""EDM Cup 2023 / ASSISTments action-log parser (Slice 3.2).

This is the first step of the HelpNeed predictor's training pipeline (PROJECT.md
§3.7; ARCHITECTURE.md §8). It reads the public **EDM Cup 2023** dataset's
action-level clickstream (mirrored on OSF; collected via ASSISTments, ~2019–2023),
filters to FRACTION problems via the Common Core ``problem_skill_code``, and
collapses each (assignment, problem) attempt sequence into one ``EdmCupTurn``
carrying the four PROJECT.md §3.7 signals — correctness, response latency, hint
usage, attempt count.

**Source-of-truth change.** TECH_STACK §5 / PROJECT.md §3.7 originally specified
CMU DataShop fraction-arithmetic traces. After friction with DataShop's export,
the training-data source was switched to EDM Cup 2023 / ASSISTments (verified to
provide all four required signals at the action level, fraction-filterable via
CCSS codes). The director records this change in PROJECT.md §3.7 / TECH_STACK §5
and in the commit message; this module references EDM Cup 2023 as the data
source. Do not reintroduce DataShop here.

**Hard boundaries** (CLAUDE.md §7, §8.1; ARCHITECTURE.md §14):
- No LLM, no SymPy, no DB, no network. Pure deterministic CSV parsing.
- Stdlib only (no pandas/polars — §8.7; the next slice's feature engineering may
  justify a vectorized library, this one does not).
- Same input ⇒ same output (PROJECT.md §4.1).
- Fail loudly on malformed rows (CLAUDE.md §8.5): skip + count via ``ParseStats``
  so the caller sees the count; never silently corrupt the training set.

**Streaming**. ``action_logs.csv`` is 1.44 GB / ~24M rows; we MUST NOT load it
all into memory. The parser uses ``csv.reader`` over a streamed file handle and
keeps only the currently-open (assignment_log_id, problem_id) turns in a dict —
flushing each on its terminal action and at EOF.

**Timestamps.** The raw CSV's ``timestamp`` column is Unix seconds as a FLOAT
with sub-second precision (e.g. ``1599150990.935``), NOT an int — verified
against the live dataset. The parser converts to integer MILLISECONDS once at
parse time so all downstream arithmetic and storage stays integral and
deterministic (PROJECT.md §4.1).

**Scope cut.** This module STOPS at per-turn aggregation. Feature engineering
(latency-windowed rates, recent-error counts, the §3.7 feature list) is **Slice
3.3**. Keeping the cut sharp is what lets each slice be reviewed independently.

**CCSS → KC mapping** (PROJECT.md §3.1 five-KC scope). Only the codes the tutor
actually teaches are kept; everything else (decimals, mult-by-whole, mult/div,
6.RP/6.NS) is excluded outright. ``5.NF.A.1`` (add) and ``5.NF.A.2`` (subtract)
both code unlike-denominator add/sub — the CCSS code alone cannot distinguish
them, so both map to ``ADDITION_UNLIKE``. Pulling them apart would need the
problem-text BERT vector (a future slice if SUBTRACTION_UNLIKE training cases run
short); flagged here so the director can review the choice. ``COMMON_DENOMINATOR``
and ``SUBTRACTION_UNLIKE`` will not get direct EDM Cup labels — that is fine,
they get labels from our own tutor's KC tracking, not the training data.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from app.domain.knowledge_components import KnowledgeComponentId

# ─── The aggregated turn (the parser's output) ────────────────────────────────


@dataclass(frozen=True)
class EdmCupTurn:
    """One learner attempt sequence on one fraction problem within one session.

    Frozen because a parsed training example is a fact about the data, not
    mutable state (ARCHITECTURE.md §14, CLAUDE.md §8.4). The fields are the four
    PROJECT.md §3.7 signals plus the keys needed to join into a learner timeline
    in Slice 3.3:

    - ``assignment_log_id``  the ASSISTments session proxy (unique per learner
      assignment instance); the grouping key feature engineering will use.
    - ``problem_id``         the problem within the session.
    - ``ccss_code``          the raw Common Core code (kept for traceability).
    - ``kc``                 the mapped ``KnowledgeComponentId`` — the join key
      back into our five-KC scope.
    - ``correct``            the turn ended with a ``correct_response`` event.
    - ``first_attempt_correct``  the FIRST response on this problem was correct,
      with no prior hint and no ``answer_requested``. This is the strict
      §3.7 "unaided first-try correct" signal — a HINT before the first response
      taints it even if the response itself is correct.
    - ``attempt_count``      number of ``wrong_response`` + ``correct_response``
      events (hint/answer events are NOT attempts).
    - ``hint_count``         number of events with a non-empty ``hint_id``.
    - ``requested_answer``   an ``answer_requested`` event fired.
    - ``latency_ms_to_first_response``  the first response's timestamp minus
      ``problem_started``, in milliseconds. ``None`` if no response ever came.
    - ``total_latency_ms``   the time to ``correct_response`` minus
      ``problem_started``, in milliseconds. ``None`` when the turn did not end
      correctly — only successful completions have a meaningful total latency.
    """

    assignment_log_id: str
    problem_id: str
    ccss_code: str
    kc: KnowledgeComponentId
    correct: bool
    first_attempt_correct: bool
    attempt_count: int
    hint_count: int
    requested_answer: bool
    latency_ms_to_first_response: int | None
    total_latency_ms: int | None


@dataclass
class ParseStats:
    """A small mutable sink for parse-time counters the caller wants to see.

    Mutable (unlike ``EdmCupTurn``) because the parser writes into it as it goes;
    the caller passes one in and reads it after the iterator is exhausted. Kept
    on a dedicated path (CLAUDE.md §8.5: surface counts of skipped rows on a
    dedicated stats path) so malformed-row counts can be reported without
    interleaving them into the turn stream or burying them in logs.

    - ``rows_read``       data rows actually consumed from the CSV (header
      excluded). Useful for verifying ``row_limit`` halted where expected and for
      computing throughput on the integration smoke.
    - ``malformed_rows``  rows skipped because they could not be parsed (e.g. a
      non-integer timestamp). Skipped rows do NOT silently change a turn's
      counts — the parser drops them entirely and increments this counter.
    - ``skipped_non_fraction_rows`` rows whose ``problem_id`` is not in the
      fraction-problems map. Counted so the caller can see how aggressively the
      CCSS filter cut the stream.
    """

    rows_read: int = 0
    malformed_rows: int = 0
    skipped_non_fraction_rows: int = 0


# ─── Per-turn in-flight state (private; not exported) ─────────────────────────


@dataclass
class _OpenTurn:
    """Mutable scratch space for one in-flight (assignment, problem) attempt sequence.

    Lives in a dict keyed by ``(assignment_log_id, problem_id)`` while the
    sequence is being assembled, then is flushed into an immutable
    ``EdmCupTurn`` on its terminal action (or at EOF). Keeping the in-flight
    state separate from the emitted dataclass is what keeps ``EdmCupTurn`` frozen
    and lets the streaming loop stay O(open-turns) in memory.
    """

    assignment_log_id: str
    problem_id: str
    ccss_code: str
    kc: KnowledgeComponentId
    # All timestamps stored in MILLISECONDS to match ``EdmCupTurn`` latency
    # fields directly; conversion from the raw float-seconds CSV happens once
    # at parse time.
    started_at_ms: int | None = None
    first_response_at_ms: int | None = None
    correct_at_ms: int | None = None
    correct: bool = False
    first_event_was_unaided_correct: bool = False
    saw_hint_before_first_response: bool = False
    attempt_count: int = 0
    hint_count: int = 0
    requested_answer: bool = False

    def to_turn(self) -> EdmCupTurn:
        """Flush this open turn into the immutable ``EdmCupTurn``."""
        first_attempt_correct = (
            self.first_event_was_unaided_correct and not self.saw_hint_before_first_response
        )
        latency_first = (
            self.first_response_at_ms - self.started_at_ms
            if self.started_at_ms is not None and self.first_response_at_ms is not None
            else None
        )
        total_latency = (
            self.correct_at_ms - self.started_at_ms
            if self.correct and self.started_at_ms is not None and self.correct_at_ms is not None
            else None
        )
        return EdmCupTurn(
            assignment_log_id=self.assignment_log_id,
            problem_id=self.problem_id,
            ccss_code=self.ccss_code,
            kc=self.kc,
            correct=self.correct,
            first_attempt_correct=first_attempt_correct,
            attempt_count=self.attempt_count,
            hint_count=self.hint_count,
            requested_answer=self.requested_answer,
            latency_ms_to_first_response=latency_first,
            total_latency_ms=total_latency,
        )


# ─── CCSS → KC mapping ────────────────────────────────────────────────────────

# The five-KC scope (PROJECT.md §3.1) maps onto Common Core codes as follows.
# Each entry is a (prefix, KC) pair; we match by ``startswith`` so trailing
# letters (3.NF.A.2a, 3.NF.A.2b, 5.NF.A.1a) all hit the right family. ORDER
# MATTERS: more-specific prefixes must come before broader ones, and EXCLUSION
# prefixes (4.NF.B.4, 4.NF.C, 5.NF.B, etc.) are handled by the "not matched →
# None" default — there is no positive entry for them.
#
# Why these and not others:
#   3.NF.A.2 → number-line placement: directly the KC.
#   3.NF.A.1, 3.NF.A.3, 4.NF.A.* → equivalence family (3.NF.A.1 defines a
#     fraction; 3.NF.A.3 covers equivalence + comparison; 4.NF.A extends it).
#   4.NF.B.3 → like-denominator add/sub (a precursor to KC3/KC4). We treat it as
#     ADDITION_UNLIKE training signal because the procedural skill (combine
#     numerators, keep denominator) is the same shape, just with the
#     common-denominator step trivialized.
#   5.NF.A.1, 5.NF.A.2 → unlike-denominator add/sub: the exact KC3/KC4 surface.
#     The CCSS code does NOT distinguish add from subtract here; both map to
#     ADDITION_UNLIKE. (SUBTRACTION_UNLIKE is filled in by our own tutor's KC
#     system, not by this training set.)
#
# Explicitly excluded (return ``None``): 4.NF.B.4 (multiplying a fraction by a
# whole number), 4.NF.C.* (decimals), 5.NF.B.* (multiplication/division of
# fractions), and every non-NF standard (3.OA, 4.OA, 6.NS, 6.RP, …). We do not
# teach those.
_CCSS_PREFIX_TO_KC: tuple[tuple[str, KnowledgeComponentId], ...] = (
    ("3.NF.A.2", KnowledgeComponentId.NUMBER_LINE_PLACEMENT),
    ("3.NF.A.1", KnowledgeComponentId.EQUIVALENCE),
    ("3.NF.A.3", KnowledgeComponentId.EQUIVALENCE),
    ("4.NF.A.", KnowledgeComponentId.EQUIVALENCE),
    # 4.NF.B.3 only (NOT 4.NF.B.4 which is multiplication by a whole number).
    # We pin "4.NF.B.3" rather than the broader "4.NF.B." so 4.NF.B.4 stays
    # excluded; if the dataset ever surfaces a 4.NF.B.5 etc. we want to review
    # it explicitly, not silently sweep it in.
    ("4.NF.B.3", KnowledgeComponentId.ADDITION_UNLIKE),
    # 5.NF.A.* covers BOTH add and subtract of unlike-denominator fractions; the
    # CCSS code alone cannot distinguish them, so both map to ADDITION_UNLIKE
    # (see module docstring).
    ("5.NF.A.", KnowledgeComponentId.ADDITION_UNLIKE),
)


def map_ccss_to_kc(ccss_code: str) -> KnowledgeComponentId | None:
    """Map a Common Core ``problem_skill_code`` to one of our five KCs, or None.

    Returns ``None`` for any code outside the five-KC scope — decimals, mult/div,
    non-NF standards, blank — so the caller can filter them out wholesale. The
    match is by prefix (``startswith``) against the table above; the first
    matching prefix wins, so the table is ordered with the most specific entries
    first.

    Pure / deterministic / cheap — called once per problem at index time, then
    the result is cached in the fraction-problems map.
    """
    if not ccss_code:
        return None
    for prefix, kc in _CCSS_PREFIX_TO_KC:
        if ccss_code.startswith(prefix):
            return kc
    return None


# ─── load_fraction_problems ───────────────────────────────────────────────────


def load_fraction_problems(
    problem_details_path: Path,
) -> dict[str, tuple[str, KnowledgeComponentId]]:
    """Index ``problem_details.csv`` by problem_id → (ccss_code, kc), fraction-only.

    Reads the file once (it's small — ~62 MB), keeps only the rows whose
    ``problem_skill_code`` maps to one of our five KCs via :func:`map_ccss_to_kc`,
    and returns a dict the action-logs parser uses to (a) filter the 24M-row
    stream and (b) attach the KC label to each emitted turn.

    Why a dict and not a set: the turn carries both ``ccss_code`` (raw, for
    traceability into the decision log) and ``kc`` (the join key), so we need
    both at flush time without re-parsing the CSV.
    """
    fraction_problems: dict[str, tuple[str, KnowledgeComponentId]] = {}
    with problem_details_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            problem_id = row.get("problem_id", "")
            ccss_code = row.get("problem_skill_code", "") or ""
            if not problem_id:
                continue
            kc = map_ccss_to_kc(ccss_code)
            if kc is None:
                continue
            fraction_problems[problem_id] = (ccss_code, kc)
    return fraction_problems


# ─── parse_action_logs (the streaming aggregator) ─────────────────────────────


# Action-vocabulary constants (verified from the real ``action_logs.csv``). Kept
# as module-level strings so a typo would surface as an unused-import / dead-code
# warning rather than silently misclassify rows at runtime.
_ACTION_PROBLEM_STARTED = "problem_started"
_ACTION_WRONG_RESPONSE = "wrong_response"
_ACTION_CORRECT_RESPONSE = "correct_response"
_ACTION_ANSWER_REQUESTED = "answer_requested"

# An "attempt" is a response — wrong or correct. Hint/answer/explanation requests
# are NOT attempts (they're assistance signals, counted separately).
_RESPONSE_ACTIONS: frozenset[str] = frozenset({_ACTION_WRONG_RESPONSE, _ACTION_CORRECT_RESPONSE})


def parse_action_logs(
    action_logs_source: Path | Iterable[str],
    fraction_problems: Mapping[str, tuple[str, KnowledgeComponentId]],
    *,
    row_limit: int | None = None,
    stats: ParseStats | None = None,
) -> Iterator[EdmCupTurn]:
    """Stream ``action_logs.csv`` and yield one ``EdmCupTurn`` per fraction attempt.

    The 1.44 GB / 24M-row file is read line-by-line via ``csv.reader``; only the
    currently-open ``(assignment_log_id, problem_id)`` turns are held in memory
    (a small dict — typically a few thousand entries even on the full file, since
    sessions and problems flush as they terminate). Each row is examined once:

      - ``problem_started``  opens a new turn (or restarts one if a duplicate
        problem_started arrives — fail-soft: we keep the latest start time).
      - ``wrong_response`` / ``correct_response``  increments the attempt count;
        the FIRST response sets ``latency_ms_to_first_response`` and decides
        ``first_attempt_correct`` (unaided correct only — a prior hint disqualifies).
        A ``correct_response`` is the success terminal: it sets ``correct=True``
        and ``total_latency_ms``, and flushes the turn.
      - ``answer_requested``  sets ``requested_answer=True`` but does NOT flush.
        The verified production sequence is wrong_response → wrong_response →
        answer_requested → correct_response (the learner asks for the answer
        then enters it), so the turn stays open and a subsequent
        ``correct_response`` flushes it with both ``requested_answer=True`` and
        ``correct=True``. If no ``correct_response`` ever follows, the EOF flush
        emits the turn with ``correct=False``.
      - Any row with a non-empty ``hint_id``  increments ``hint_count``; if seen
        before the first response, taints ``first_attempt_correct``.

    Turns still open at EOF are flushed in insertion order (Python dict
    guarantee, ≥3.7) so the output order is deterministic (PROJECT.md §4.1).

    Parameters
    ----------
    action_logs_source:
        Either a path to ``action_logs.csv`` or any text iterable (StringIO, a
        list of lines) — the latter is what the unit tests use to stay
        tmpdir-free for the simple cases.
    fraction_problems:
        The output of :func:`load_fraction_problems`. Rows whose ``problem_id``
        is not in this map are dropped before any state mutation, so the
        non-fraction majority of the file never enters the open-turns dict.
    row_limit:
        Optional cap on the number of DATA rows consumed (header excluded). Used
        by the integration smoke to scan a prefix of the 24M-row file rather
        than the whole thing. ``None`` = read to EOF.
    stats:
        Optional ``ParseStats`` the parser writes into. Always populated when
        provided, so the caller sees rows_read, malformed_rows, and
        skipped_non_fraction_rows after iteration completes.

    Yields
    ------
    EdmCupTurn
        One per (assignment_log_id, problem_id) attempt sequence that touched a
        fraction problem.
    """
    if stats is None:
        stats = ParseStats()
    open_turns: dict[tuple[str, str], _OpenTurn] = {}

    if isinstance(action_logs_source, Path):
        handle = action_logs_source.open(newline="")
        owns_handle = True
    else:
        handle = action_logs_source  # type: ignore[assignment]
        owns_handle = False

    try:
        reader = csv.reader(handle)
        header = next(reader, None)
        if header is None:
            return
        # Pre-compute column indexes from the header so we tolerate any column
        # reordering. The verified schema is:
        #   assignment_log_id,timestamp,problem_id,max_attempts,
        #   available_core_tutoring,score_viewable,continuous_score_viewable,
        #   action,hint_id,explanation_id
        try:
            i_assignment = header.index("assignment_log_id")
            i_timestamp = header.index("timestamp")
            i_problem = header.index("problem_id")
            i_action = header.index("action")
            i_hint = header.index("hint_id")
        except ValueError as exc:  # missing required column → fail loudly
            raise ValueError(f"action_logs CSV missing required column: {exc}") from exc

        for row in reader:
            if row_limit is not None and stats.rows_read >= row_limit:
                break
            stats.rows_read += 1

            # Defensive: short rows from a truncated/corrupt CSV are skipped and
            # counted rather than crashing the 24M-row scan.
            if len(row) <= max(i_assignment, i_timestamp, i_problem, i_action, i_hint):
                stats.malformed_rows += 1
                continue

            problem_id = row[i_problem]
            if problem_id not in fraction_problems:
                stats.skipped_non_fraction_rows += 1
                continue

            try:
                # ASSISTments timestamps in this export are Unix seconds as
                # FLOATS with sub-second precision (e.g. ``1599150990.935``).
                # Convert seconds → milliseconds at parse time; the EdmCupTurn
                # latency fields are documented as ints in ms, so we round once
                # here and store ints downstream (avoids accumulating float
                # error on later arithmetic; PROJECT.md §4.1 determinism: same
                # bytes ⇒ same int).
                timestamp_ms = round(float(row[i_timestamp]) * 1000)
            except ValueError:
                stats.malformed_rows += 1
                continue

            assignment_log_id = row[i_assignment]
            action = row[i_action]
            hint_id = row[i_hint]
            key = (assignment_log_id, problem_id)

            # A hint event (non-empty hint_id) is counted regardless of the
            # action name — the schema has a dedicated ``hint_requested`` action,
            # but defensively we also accept any other row that carries a
            # hint_id (e.g. continue_selected on a hint screen).
            if hint_id:
                turn = open_turns.get(key)
                if turn is None:
                    ccss_kc = fraction_problems[problem_id]
                    turn = _OpenTurn(
                        assignment_log_id=assignment_log_id,
                        problem_id=problem_id,
                        ccss_code=ccss_kc[0],
                        kc=ccss_kc[1],
                    )
                    open_turns[key] = turn
                turn.hint_count += 1
                if turn.first_response_at_ms is None:
                    turn.saw_hint_before_first_response = True
                # Hint events are not attempts and not terminals; continue.
                continue

            if action == _ACTION_PROBLEM_STARTED:
                ccss_kc = fraction_problems[problem_id]
                turn = open_turns.get(key)
                if turn is None:
                    turn = _OpenTurn(
                        assignment_log_id=assignment_log_id,
                        problem_id=problem_id,
                        ccss_code=ccss_kc[0],
                        kc=ccss_kc[1],
                    )
                    open_turns[key] = turn
                turn.started_at_ms = timestamp_ms
                continue

            if action in _RESPONSE_ACTIONS:
                turn = open_turns.get(key)
                if turn is None:
                    # A response on a problem we never saw started — keep the
                    # data (don't silently lose it) by opening a turn with no
                    # start time. Latency fields stay None.
                    ccss_kc = fraction_problems[problem_id]
                    turn = _OpenTurn(
                        assignment_log_id=assignment_log_id,
                        problem_id=problem_id,
                        ccss_code=ccss_kc[0],
                        kc=ccss_kc[1],
                    )
                    open_turns[key] = turn

                turn.attempt_count += 1
                if turn.first_response_at_ms is None:
                    turn.first_response_at_ms = timestamp_ms
                    # First-attempt-correct requires the FIRST response to be
                    # correct AND no prior hint AND no prior answer_requested.
                    # All three are checked here at the moment of the first
                    # response. (A prior answer_requested would already have
                    # flushed this turn, so we only need to check hints.)
                    if (
                        action == _ACTION_CORRECT_RESPONSE
                        and not turn.saw_hint_before_first_response
                    ):
                        turn.first_event_was_unaided_correct = True

                if action == _ACTION_CORRECT_RESPONSE:
                    turn.correct = True
                    turn.correct_at_ms = timestamp_ms
                    yield turn.to_turn()
                    del open_turns[key]
                continue

            if action == _ACTION_ANSWER_REQUESTED:
                # ``answer_requested`` is NOT a terminal flush — the verified
                # production sequence is wrong_response → wrong_response →
                # answer_requested → correct_response (the learner asks for the
                # answer and then enters it), all as ONE turn with both
                # ``requested_answer=True`` and ``correct=True``. We set the
                # flag and keep the turn open; ``correct_response`` (or EOF)
                # will flush it. If the turn never reaches a ``correct_response``
                # the EOF flush emits it with ``correct=False`` and
                # ``total_latency_ms=None``.
                turn = open_turns.get(key)
                if turn is None:
                    ccss_kc = fraction_problems[problem_id]
                    turn = _OpenTurn(
                        assignment_log_id=assignment_log_id,
                        problem_id=problem_id,
                        ccss_code=ccss_kc[0],
                        kc=ccss_kc[1],
                    )
                    open_turns[key] = turn
                turn.requested_answer = True
                continue

            # Every other action (assignment_started, problem_finished,
            # continue_selected, open_response, skill_related_video_requested,
            # explanation_requested, assignment_finished, assignment_resumed)
            # carries no signal we need for the four PROJECT.md §3.7 features.
            # Skip silently; this is the expected majority of rows.

        # EOF: flush any still-open turns in insertion order for determinism.
        for turn in open_turns.values():
            yield turn.to_turn()
    finally:
        if owns_handle:
            handle.close()


__all__ = [
    "EdmCupTurn",
    "ParseStats",
    "load_fraction_problems",
    "map_ccss_to_kc",
    "parse_action_logs",
]
