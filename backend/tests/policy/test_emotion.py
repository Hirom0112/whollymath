"""Tests for the deterministic avatar-emotion selection (Slice 1.3).

The load-bearing assertions (CLAUDE.md §8.1/§8.3, ARCHITECTURE.md §14):
  - the mapping is DETERMINISTIC (same moment ⇒ same cue);
  - a wrong/stuck moment NEVER yields ``celebrate`` (the LLM can't celebrate a wrong answer
    because it never chooses the emotion at all — the policy does, from the moment type);
  - a correct verdict / passed transfer probe DOES yield ``celebrate``;
  - the mapping is closed and total over ``MomentType`` and the intensity is bounded.
"""

from __future__ import annotations

from app.policy.emotion import Emotion, EmotionCue, MomentType, select_emotion


def test_selection_is_deterministic_same_moment_same_cue() -> None:
    """Same moment ⇒ identical cue, every call (the determinism the avatar relies on)."""
    for moment in MomentType:
        assert select_emotion(moment) == select_emotion(moment)


def test_wrong_verdict_never_celebrates() -> None:
    """A wrong answer must soften, never celebrate — the §8.3 invariant in one assertion."""
    cue = select_emotion(MomentType.WRONG_VERDICT)
    assert cue.emotion != Emotion.CELEBRATE
    assert cue.emotion == Emotion.REASSURE


def test_stuck_nudge_never_celebrates() -> None:
    """A stuck/help moment must not celebrate — it encourages forward."""
    cue = select_emotion(MomentType.STUCK_NUDGE)
    assert cue.emotion != Emotion.CELEBRATE
    assert cue.emotion == Emotion.ENCOURAGE


def test_correct_verdict_celebrates() -> None:
    """A correct verdict is a win — celebrate."""
    assert select_emotion(MomentType.CORRECT_VERDICT).emotion == Emotion.CELEBRATE


def test_transfer_probe_pass_celebrates_harder() -> None:
    """A passed transfer probe is the bigger win — celebrate at full intensity."""
    probe = select_emotion(MomentType.TRANSFER_PROBE_PASS)
    item = select_emotion(MomentType.CORRECT_VERDICT)
    assert probe.emotion == Emotion.CELEBRATE
    assert probe.intensity > item.intensity


def test_conceptual_nudge_thinks() -> None:
    """A 'let's picture this' conceptual prompt plays the pondering beat."""
    assert select_emotion(MomentType.CONCEPTUAL_NUDGE).emotion == Emotion.THINK


def test_resting_is_neutral() -> None:
    """The resting default has no special affect."""
    assert select_emotion(MomentType.RESTING).emotion == Emotion.NEUTRAL


def test_mapping_is_total_and_intensity_bounded() -> None:
    """Every moment has a defined cue; every intensity is a bounded [0,1] scalar."""
    for moment in MomentType:
        cue = select_emotion(moment)
        assert isinstance(cue, EmotionCue)
        assert isinstance(cue.emotion, Emotion)
        assert 0.0 <= cue.intensity <= 1.0
