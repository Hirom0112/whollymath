"""The avatar's emotion vocabulary — deterministically chosen, never by the LLM (Slice 1.3).

The tutor's mascot (Slice 2.2 "Pie") both SPEAKS the help text and plays an EMOTION
animation. The load-bearing invariant (CLAUDE.md §8.1/§8.3, ARCHITECTURE.md §14): the LLM
fills ONLY the natural-language ``text`` (in ``persona_surface/tutor_voice``); the *emotion*
and its *intensity* are chosen HERE, deterministically, from the already-known MOMENT TYPE
the deterministic policy/turn-loop is in (a correct verdict, a stuck nudge, a transfer-probe
pass, …). So the LLM can never (for example) "celebrate" a wrong answer, and the avatar's
affect never depends on — and never leaks — the learner's knowledge state (§8.3).

Both ``Emotion`` and the moment→emotion mapping live in ``policy/`` (not ``llm/``), because
this is a UI-adaptation decision, the same layer that owns the surface-state vocabulary
(``surface_states.py``) and the transition rules (ARCHITECTURE.md §4: the policy is the
single source of truth for what the UI does). ``select_emotion`` is a PURE function — no
LLM, no SymPy, no DB — so it is safe on the sub-100ms path and trivially deterministic
(same moment ⇒ same cue, the §9 test discipline).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Emotion(StrEnum):
    """The CLOSED set of avatar emotions (Slice 1.3).

    A ``StrEnum`` so each member serializes as its stable string for the API and the
    generated TS union (the Avatar component, Slice 2.2, switches on these). Changing a
    VALUE is a breaking change to the wire contract and the generated TS union.

      - ``encourage`` — gentle forward push (a hint, "you're close, keep going").
      - ``celebrate`` — a win: a correct verdict or a passed transfer probe.
      - ``think``     — a pondering beat (a conceptual nudge, "let's picture this").
      - ``reassure``  — a soft, low-pressure beat after a wrong answer or a stuck moment.
      - ``neutral``   — the resting default; no special affect to play.
    """

    ENCOURAGE = "encourage"
    CELEBRATE = "celebrate"
    THINK = "think"
    REASSURE = "reassure"
    NEUTRAL = "neutral"


class MomentType(StrEnum):
    """The deterministic "moment" the tutor is in when it speaks (Slice 1.3).

    This is the only input ``select_emotion`` reads — and it is supplied by the
    deterministic caller (the policy/turn-loop), NEVER derived from the learner's mastery
    state or handed to the LLM. It names *what kind of beat this is*, not *who the learner
    is*, so the avatar's affect stays knowledge-state-blind (§8.3).

      - ``CORRECT_VERDICT``    — the SymPy verdict was correct (§10 step 4).
      - ``TRANSFER_PROBE_PASS``— the S5 transfer probe passed (a bigger win than a single item).
      - ``WRONG_VERDICT``      — the SymPy verdict was incorrect; soften, never celebrate.
      - ``STUCK_NUDGE``        — a help moment: a reactive hint or a proactive/ mid-problem nudge.
      - ``CONCEPTUAL_NUDGE``   — a "let's picture this" conceptual prompt (the first hint level).
      - ``RESTING``            — no special moment; the resting default.
    """

    CORRECT_VERDICT = "correct_verdict"
    TRANSFER_PROBE_PASS = "transfer_probe_pass"
    WRONG_VERDICT = "wrong_verdict"
    STUCK_NUDGE = "stuck_nudge"
    CONCEPTUAL_NUDGE = "conceptual_nudge"
    RESTING = "resting"


# Intensity is a small BOUNDED scalar in [0.0, 1.0] (Slice 1.3): how strongly to play the
# emotion. Deterministic per moment — a passed transfer probe (a hard-won, rarer win) plays
# the celebration harder than a single correct item; a soft reassure stays gentle. We keep a
# tiny, named step ladder rather than free floats so the values are legible and stable.
_INTENSITY_GENTLE = 0.3
_INTENSITY_STEADY = 0.6
_INTENSITY_STRONG = 1.0


@dataclass(frozen=True)
class EmotionCue:
    """The deterministic affect to play with a line of tutor speech: an emotion + its intensity.

    Frozen and value-only so it is trivially comparable in tests (same moment ⇒ equal cue) and
    cannot be mutated downstream. ``persona_surface/tutor_voice`` pairs this with the LLM-voiced
    ``text``; the API projects both onto the wire (Slice 1.3).
    """

    emotion: Emotion
    intensity: float


# The single source of truth for moment → affect (Slice 1.3). A closed, total mapping so every
# MomentType has a defined cue and ``select_emotion`` never falls back to a guess. The invariant
# is visible right here: WRONG_VERDICT and STUCK_NUDGE map to REASSURE — NEVER to CELEBRATE.
_MOMENT_TO_CUE: dict[MomentType, EmotionCue] = {
    MomentType.CORRECT_VERDICT: EmotionCue(Emotion.CELEBRATE, _INTENSITY_STEADY),
    MomentType.TRANSFER_PROBE_PASS: EmotionCue(Emotion.CELEBRATE, _INTENSITY_STRONG),
    MomentType.WRONG_VERDICT: EmotionCue(Emotion.REASSURE, _INTENSITY_GENTLE),
    MomentType.STUCK_NUDGE: EmotionCue(Emotion.ENCOURAGE, _INTENSITY_STEADY),
    MomentType.CONCEPTUAL_NUDGE: EmotionCue(Emotion.THINK, _INTENSITY_STEADY),
    MomentType.RESTING: EmotionCue(Emotion.NEUTRAL, _INTENSITY_GENTLE),
}


def select_emotion(moment: MomentType) -> EmotionCue:
    """The deterministic emotion + intensity for a tutor MOMENT (Slice 1.3) — pure, no LLM/DB.

    The same ``moment`` always yields the same cue (the §9 determinism the avatar relies on).
    The mapping is closed and total over ``MomentType``, so every moment has a defined cue and
    a wrong/stuck moment can NEVER yield ``celebrate``. This is the policy-layer half of the
    Slice 1.3 invariant: the LLM voices the words, the policy decides the feeling.
    """
    return _MOMENT_TO_CUE[moment]


__all__ = ["Emotion", "EmotionCue", "MomentType", "select_emotion"]
