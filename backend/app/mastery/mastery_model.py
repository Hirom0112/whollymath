"""The mastery model: per-KC BKT + the §3.4 anti-gaming augmentation rules.

Slices 1.5 (BKT per KC) and 1.6 (the §3.4 rules). This is the single most
load-bearing system in the project: if a learner who only pattern-matches,
leans on hints, drills one representation, or clicks through can reach
"mastered", the false-positive-mastery headline metric (PROJECT.md §3.9) is a
lie and the personas (PROJECT.md §4.2) walk straight through. So mastery is
NOT "BKT crossed τ" — it is BKT > τ AND four structural rules AND an engagement
floor. ARCHITECTURE.md §6; PROJECT.md §3.4.

This module is **pure, deterministic logic** (CLAUDE.md §8.1): no LLM, no DB,
no SymPy. It consumes an attempt log (``Observation`` records produced by the
tutor/verifier upstream) and the KC registry from Layer 1, and returns a
mastery probability and a mastery declaration with reasons. Persistence
(``MasteryState`` in app/db) is a separate concern and is intentionally not
touched here.

Locked tunings used (PROJECT.md §8 decision 0.D.5; all tunable in weeks 4–5
with the change recorded in the decision log):
  - τ (mastery threshold) = 0.90 (raised from 0.85; product-owner authorized
    2026-05-29 — "2 right ≠ mastered", make luck-mastery harder)
  - minimum scored attempts before mastery = 5 (new gate, 2026-05-29: BKT alone
    can cross τ in 2 corrects; a real tutor needs more evidence than that)
  - interleaving cadence = 3 items across ≥2 KCs
  - productive-struggle window = 60s (the engagement floor lives well below it)

Cold-start (PROJECT.md §8 decision 0.D.2): the Turn-0 routing self-report seeds
a BKT *prior*, not a commitment — see ``initial_prior_from_self_report``.

Mastery declared here is **provisional until the transfer probe (S5)** passes
(ARCHITECTURE.md §6); the transfer probe is a later slice and is deliberately
not built here.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.knowledge_components import KnowledgeComponentId, Representation

# ─────────────────────────── Locked tunings (0.D.5) ───────────────────────────

# τ: a KC's BKT probability must exceed this before mastery can even be considered
# (PROJECT.md §3.4 rule 1, §8 0.D.5). Named so the week-4/5 tuning is one edit.
# Raised 0.85 -> 0.90 on 2026-05-29 (product-owner authorized; supersedes the
# 0.D.5 lock): crossing τ in two corrects was too easy, so we demand a higher
# posterior before mastery is even considered.
MASTERY_THRESHOLD: float = 0.90

# Minimum scored attempts on a KC before mastery may be declared, regardless of
# BKT probability (new gate, 2026-05-29; ANDed with the §3.4 rules below). BKT
# can cross τ in as few as two corrects, but "two right" is not mastery in a
# real tutor — we require a floor of distinct scored attempts on the KC so a
# lucky short streak cannot trip the declaration. Counts every scored attempt on
# the KC (correct or not, hinted or not, engaged or not): the floor is about
# *how much was attempted*, not how it scored — the quality gates are the other
# rules. Strictly > 0 is the load-bearing property; 5 is the initial pick.
MIN_ATTEMPTS_FOR_MASTERY: int = 5

# §3.4 rule 2: correctness across at least this many distinct representations of
# the same KC. Defeats Natural-number Nate (symbolic-pass / magnitude-fail).
MIN_REPRESENTATIONS: int = 2

# §3.6 / §8 0.D.5: a mastery-grade interleaved set is >= 3 items spread across
# >= 2 KCs. Defeats Surface Sam: a blocked same-KC run is block-fluency, not
# transferable mastery (Rohrer interleaving research).
INTERLEAVE_CADENCE: int = 3
INTERLEAVE_MIN_KCS: int = 2

# §3.4 rule 3: hinted-correct attempts are real but partial evidence — the
# scaffold did some of the reasoning — so they enter BKT downweighted rather
# than as full successes. Defeats Hint-hunter Hugo. (A value strictly < 1.0 is
# the load-bearing property; 0.4 is the initial pick, tunable in weeks 4–5.)
HINTED_CORRECT_WEIGHT: float = 0.4

# Engagement floor (PROJECT.md §3.4, §4.2 Persona 5): a genuine attempt at a
# fraction item takes seconds. Click-through Cleo answers in under ~2s, picking
# the first option without engaging. Responses faster than this floor are
# flagged and do not count as mastery evidence. Well below the 60s
# productive-struggle window (0.D.5) — the floor catches non-engagement, the
# window protects slow thinking. 2_000 ms is the initial pick (tunable).
ENGAGEMENT_FLOOR_MS: int = 2_000


# ───────────────────────────── BKT (Slice 1.5) ─────────────────────────────


@dataclass(frozen=True)
class BktParams:
    """The four standard Bayesian Knowledge Tracing parameters for one KC.

    Frozen because parameters are configuration, not runtime state. Per-KC
    tuning is possible later by constructing a different ``BktParams``; the
    defaults below are a reasonable starting point pending DataShop calibration
    (ARCHITECTURE.md §6, §10).

    - ``p_init``   P(L0): prior probability the skill is already known (the
                   cold-start prior; see ``initial_prior_from_self_report``).
    - ``p_transit``P(T): probability the skill transitions unknown→known on a
                   single practice opportunity (learning).
    - ``p_slip``   P(S): probability of an incorrect answer despite knowing it.
    - ``p_guess``  P(G): probability of a correct answer without knowing it.
    """

    p_init: float
    p_transit: float
    p_slip: float
    p_guess: float


# Default BKT parameters. Conventional ITS starting values (slip/guess small,
# modest learn rate); to be calibrated against DataShop traces and the persona
# suite in later slices (ARCHITECTURE.md §6, §10).
DEFAULT_BKT_PARAMS: BktParams = BktParams(
    p_init=0.2,
    p_transit=0.15,
    p_slip=0.1,
    p_guess=0.2,
)


def bkt_update(prior_prob: float, *, correct: bool, params: BktParams) -> float:
    """One standard BKT update: return the posterior P(known) after an observation.

    Standard two-step BKT (Corbett & Anderson 1995):

      1. Condition the current mastery estimate on the observed evidence
         (Bayes' rule), using slip/guess as the emission probabilities:

           if correct:
             P(L | obs) =        L·(1 - p_slip)
                          ─────────────────────────────────────
                          L·(1 - p_slip) + (1 - L)·p_guess

           if incorrect:
             P(L | obs) =          L·p_slip
                          ─────────────────────────────────────
                          L·p_slip + (1 - L)·(1 - p_guess)

      2. Apply the learning transition (the learner may have *learned* it on
         this opportunity):

           P(L') = P(L | obs) + (1 - P(L | obs))·p_transit

    The result is clamped to [0, 1] for numerical safety; it is a probability
    and every downstream consumer assumes that invariant.
    """
    if correct:
        numerator = prior_prob * (1.0 - params.p_slip)
        denominator = numerator + (1.0 - prior_prob) * params.p_guess
    else:
        numerator = prior_prob * params.p_slip
        denominator = numerator + (1.0 - prior_prob) * (1.0 - params.p_guess)

    # Degenerate denominator (e.g. params at exact 0/1 extremes): fall back to
    # the prior rather than dividing by zero. In practice slip/guess are in
    # (0, 1) so this branch is defensive only.
    conditioned = prior_prob if denominator == 0.0 else numerator / denominator

    posterior = conditioned + (1.0 - conditioned) * params.p_transit
    return min(1.0, max(0.0, posterior))


# ──────────────────── Cold-start prior hook (Slice 1.5; 0.D.2) ────────────────────

# The seeded prior for the KC the learner routed into at Turn 0, and the
# (lower) default prior for everything else / "I'm not sure". Both are deliberately
# modest: the self-report is a PRIOR, not a commitment (0.D.2), so even the
# chosen KC starts well below τ and a single wrong answer can pull it back down.
_SELF_REPORT_CHOSEN_PRIOR: float = 0.4
_SELF_REPORT_UNSURE_PRIOR: float = 0.2


def initial_prior_from_self_report(
    kc: KnowledgeComponentId,
    *,
    chosen_kc: KnowledgeComponentId | None,
) -> float:
    """Seed a KC's BKT prior P(L0) from the Turn-0 routing self-report.

    PROJECT.md §8 decision 0.D.2: cold start is a two-step. Turn 0 is a
    kid-friendly routing question; the learner's choice (``chosen_kc``) — or the
    de-emphasized "I'm not sure" default (``chosen_kc is None``) — seeds the
    prior. This is explicitly **a prior, not a commitment**: the chosen KC gets a
    modestly higher starting probability, but it is still far below τ, so Turn-1
    performance (and all later evidence) can override it via ``bkt_update``. The
    self-report is never referenced back to the learner; predicted-vs-actual is a
    metacognitive-calibration signal logged elsewhere, not enforced here.

    Returns the prior for ``kc`` specifically: higher if the learner routed into
    it, the unsure-default otherwise.
    """
    if chosen_kc is not None and kc == chosen_kc:
        return _SELF_REPORT_CHOSEN_PRIOR
    return _SELF_REPORT_UNSURE_PRIOR


# ──────────────────────── Observation / attempt record ────────────────────────


@dataclass(frozen=True)
class Observation:
    """One attempt at one item, as the mastery model needs to see it.

    This is the minimal record the §3.4 rules range over. It is produced
    upstream (the tutor records the turn; the SymPy verifier in Layer 1 decides
    ``correct`` — the mastery model never judges math itself, CLAUDE.md §8.2).

    - ``kc``             which knowledge component the item exercised.
    - ``correct``        the verifier's verdict (already decided in domain/).
    - ``representation`` which surface it was answered in (rule 2 ranges over this).
    - ``hinted``         whether scaffolding/hints were used (rule 3 downweights).
    - ``latency_ms``     time-to-answer; below the engagement floor → flagged.
    """

    kc: KnowledgeComponentId
    correct: bool
    representation: Representation
    hinted: bool
    latency_ms: int

    def is_low_engagement(self) -> bool:
        """True if this response was faster than the engagement floor.

        A flagged response is non-evidence for mastery (PROJECT.md §3.4, §4.2
        Persona 5). Repeated low-engagement responses are what the policy layer
        turns into a re-engagement prompt; this method models only the flag.
        """
        return self.latency_ms < ENGAGEMENT_FLOOR_MS


# ───────────────── Per-KC mastery probability (BKT + rules 3 & 4) ─────────────────


def _evidence_weight(obs: Observation, *, interleaved: bool) -> float:
    """How much a single correct observation counts toward BKT, in [0, 1].

    Encodes two §3.4 rules at the evidence level:
      - rule 3: hinted-correct is downweighted (the scaffold did part of the work).
      - rule 4: a *blocked* correct (no other KC since the last same-KC item)
        counts for less than an interleaved correct (block-fluency, not transfer).

    Low-engagement responses contribute nothing (the engagement floor): a lucky
    sub-floor click is not evidence of knowing.
    """
    if obs.is_low_engagement():
        return 0.0
    weight = 1.0
    if obs.hinted:
        weight *= HINTED_CORRECT_WEIGHT
    if not interleaved:
        weight *= _BLOCKED_CORRECT_WEIGHT
    return weight


# A blocked correct (a same-KC item with no other KC since the previous same-KC
# item) counts for less than an interleaved one. Strictly < 1.0 is the
# load-bearing property (PROJECT.md §3.4 rule 4); 0.5 is the initial pick.
_BLOCKED_CORRECT_WEIGHT: float = 0.5


def _is_interleaved_at(observations: list[Observation], index: int) -> bool:
    """Whether the observation at ``index`` is interleaved rather than blocked.

    Interleaved = a different KC appeared since this KC's previous occurrence.
    The first time a KC appears it is treated as interleaved (there is no prior
    same-KC run to make it "blocked"). This is the per-item analog of the §3.6
    interleaving rule; the set-level cadence (≥3 across ≥2 KCs) is checked in
    ``declare_mastery``.
    """
    target_kc = observations[index].kc
    for prior in reversed(observations[:index]):
        if prior.kc == target_kc:
            # Found this KC's previous occurrence with no other KC in between.
            return False
        return True  # the immediately preceding item was a different KC
    return True  # first occurrence of this KC


def kc_mastery_probability(
    kc: KnowledgeComponentId,
    observations: list[Observation],
    *,
    params: BktParams = DEFAULT_BKT_PARAMS,
) -> float:
    """Run BKT over the log for one KC and return its mastery probability.

    Per-KC: only observations for ``kc`` update its probability; other KCs'
    items are ignored here (but their *presence* in the log is what makes a
    target-KC item count as interleaved — see ``_is_interleaved_at``).

    Evidence is weighted per ``_evidence_weight``. We fold the weight into the
    Bayesian step as a soft observation: a correct item with weight ``w`` is
    treated as a blend of "fully updated on correct" and "left unchanged",
    ``posterior = w·update(prior, correct) + (1 - w)·prior``. This makes a
    hinted, blocked, or sub-floor success move the estimate strictly less than a
    clean one, without leaving the [0, 1] interval. Incorrect items always count
    in full (a wrong answer is unambiguous negative evidence; we never discount
    failure).
    """
    prob = params.p_init
    for i, obs in enumerate(observations):
        if obs.kc != kc:
            continue
        if not obs.correct:
            prob = bkt_update(prob, correct=False, params=params)
            continue
        weight = _evidence_weight(obs, interleaved=_is_interleaved_at(observations, i))
        full = bkt_update(prob, correct=True, params=params)
        prob = weight * full + (1.0 - weight) * prob
    return prob


# ───────────────────── §3.4 rule checks (Slice 1.6) ─────────────────────


def _distinct_correct_representations(
    kc: KnowledgeComponentId, observations: list[Observation]
) -> set[Representation]:
    """Representations in which ``kc`` was answered correctly *and* engaged.

    Sub-floor (low-engagement) corrects do not count — a flagged click is not a
    demonstration in that representation (PROJECT.md §3.4 rules 2 + engagement).
    """
    return {
        o.representation
        for o in observations
        if o.kc == kc and o.correct and not o.is_low_engagement()
    }


def _has_unscaffolded_correct(kc: KnowledgeComponentId, observations: list[Observation]) -> bool:
    """§3.4 rule 3: at least one correct, engaged, NON-hinted attempt on ``kc``."""
    return any(
        o.kc == kc and o.correct and not o.hinted and not o.is_low_engagement()
        for o in observations
    )


def _has_interleaved_mastery_set(kc: KnowledgeComponentId, observations: list[Observation]) -> bool:
    """§3.6 / 0.D.5: the mastery evidence must be a VARIED (non-blocked) set of
    ≥ INTERLEAVE_CADENCE correct, engaged items — not a blocked drill of one identical
    item type. Two ways to satisfy it (either suffices):

    1. **Cross-KC interleaving** (the original gate): the set spans ≥ INTERLEAVE_MIN_KCS
       KCs, with the target among them. This is the multi-skill mixed practice the eval
       harness feeds (Rohrer 2015; the original Surface-Sam defense).
    2. **Within-skill representation interleaving** (added 2026-05-29, product-owner
       decision: single-skill lessons): a lesson on the target KC ALONE still counts as
       varied practice when its correct, engaged items span ≥ MIN_REPRESENTATIONS distinct
       representations of the KC (e.g. number-line PLACING and COMPARING) — i.e. the learner
       did not just repeat one identical format. This is strictly within rule 2's bar, so
       Surface Sam (tied to one representation) still fails it; the S5 transfer probe remains
       the second gate. PROJECT.md §3.4 rule 4 / §3.6 updated accordingly.

    Sub-floor (low-engagement) corrects never count toward either path.
    """
    engaged_correct = [o for o in observations if o.correct and not o.is_low_engagement()]
    if len(engaged_correct) < INTERLEAVE_CADENCE:
        return False
    kcs_present = {o.kc for o in engaged_correct}
    if len(kcs_present) >= INTERLEAVE_MIN_KCS and kc in kcs_present:
        return True  # path 1: cross-KC interleaving
    target_reps = {o.representation for o in engaged_correct if o.kc == kc}
    return len(target_reps) >= MIN_REPRESENTATIONS  # path 2: within-skill representation mix


def _scored_attempt_count(kc: KnowledgeComponentId, observations: list[Observation]) -> int:
    """Number of scored attempts on ``kc`` (the minimum-attempts floor counts these).

    Every attempt on the KC counts — correct or not, hinted or not, engaged or
    not. The floor is a quantity-of-evidence gate ("two right ≠ mastered"); the
    quality of that evidence is judged by the other §3.4 rules.
    """
    return sum(1 for o in observations if o.kc == kc)


def _is_engagement_floored(kc: KnowledgeComponentId, observations: list[Observation]) -> bool:
    """Engagement floor (defeats Click-through Cleo): True when ``kc`` has NO
    engaged evidence at all — every attempt on it was below the time floor.

    A learner who only ever answers sub-floor has produced no real evidence;
    declaring mastery off lucky clicks is the exact false positive this blocks.
    """
    kc_obs = [o for o in observations if o.kc == kc]
    if not kc_obs:
        return False
    return all(o.is_low_engagement() for o in kc_obs)


def declare_mastery(
    kc: KnowledgeComponentId,
    observations: list[Observation],
    *,
    params: BktParams = DEFAULT_BKT_PARAMS,
) -> tuple[bool, list[str]]:
    """Decide whether ``kc`` is (provisionally) mastered, with reasons if not.

    Mastery requires ALL of (PROJECT.md §3.4; ARCHITECTURE.md §6):
      1. BKT probability > τ (MASTERY_THRESHOLD).
      2. Correct across ≥ MIN_REPRESENTATIONS representations of the KC.
      3. ≥ 1 unscaffolded (non-hinted) correct attempt.
      4. Evidence from an interleaved set (≥ cadence items across ≥ 2 KCs),
         not a blocked same-KC run.
    Plus: not engagement-floored, and ≥ MIN_ATTEMPTS_FOR_MASTERY scored attempts
    on the KC (the minimum-attempts floor: "two right ≠ mastered").

    Returns ``(mastered, reasons)``. When ``mastered`` is False, ``reasons``
    names every failing rule (so the caller / decision log sees exactly which
    adversarial pattern was blocked); when True, ``reasons`` is empty.

    The declaration is **provisional**: it means "ready for the transfer probe
    (S5)", not "confirmed". A failed transfer probe demotes the KC back to
    scaffolded practice. The transfer probe is a later slice and is not built
    here; this function deliberately exposes no transfer-confirmation API.
    """
    reasons: list[str] = []

    # Check the engagement floor first: if there is no engaged evidence, none of
    # the other rules can be satisfied honestly anyway.
    if _is_engagement_floored(kc, observations):
        reasons.append(
            "engagement floor: every attempt on this KC was below the time-to-answer "
            "floor (no engaged evidence)"
        )

    attempts = _scored_attempt_count(kc, observations)
    if attempts < MIN_ATTEMPTS_FOR_MASTERY:
        reasons.append(
            f"minimum attempts: {attempts} scored attempt(s) on this KC, "
            f"need >= {MIN_ATTEMPTS_FOR_MASTERY} (two right != mastered)"
        )

    prob = kc_mastery_probability(kc, observations, params=params)
    if prob <= MASTERY_THRESHOLD:
        reasons.append(f"BKT threshold: mastery probability {prob:.3f} <= tau {MASTERY_THRESHOLD}")

    reps = _distinct_correct_representations(kc, observations)
    if len(reps) < MIN_REPRESENTATIONS:
        reasons.append(
            f"representation diversity: correct in {len(reps)} representation(s), "
            f"need >= {MIN_REPRESENTATIONS} (rule 2)"
        )

    if not _has_unscaffolded_correct(kc, observations):
        reasons.append(
            "scaffolding: no unscaffolded (no-hint) correct attempt; all correct "
            "attempts were hinted (rule 3)"
        )

    if not _has_interleaved_mastery_set(kc, observations):
        reasons.append(
            f"interleaving: evidence is a blocked run, not an interleaved set of "
            f">= {INTERLEAVE_CADENCE} items across >= {INTERLEAVE_MIN_KCS} KCs (rule 4)"
        )

    return (len(reasons) == 0, reasons)
