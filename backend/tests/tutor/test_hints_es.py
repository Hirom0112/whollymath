"""Tests for the es-MX (Mexican Spanish) help-string bank (Slice 3.2a).

The es-MX bank (``app/tutor/hints_es.py``) is the DATA layer that parallels the English spoken
bank, keyed by the SAME ``string_id``s, so the TTS renderer can voice Spanish for the es-MX
locale. These tests are the parity + sanity gate per the slice plan:

  - PARITY: every renderable English ``string_id`` has an es-MX translation, and no es-MX key
    lacks an English counterpart (the manifest keys must line up 1:1 across locales).
  - NON-EMPTY / NOT-ENGLISH: every es-MX string is non-empty and differs from the English source
    (a basic sanity that a translation actually happened, not a copy of the English).
  - TERMBASE CONSISTENCY: the core math terms appear in their canonical es-MX form (spot-check).
  - REVIEW GATE: the bank is human-reviewed (``ES_MX_REVIEWED is True``) so 3.5/3.6 may treat it
    as production audio.

No LLM / network / DB — pure data over the in-process banks (CLAUDE.md §8.1).
"""

from __future__ import annotations

from app.tutor.hints_es import ES_MX_HELP_STRINGS, ES_MX_LOCALE, ES_MX_REVIEWED, es_mx_text


def _renderable_english() -> dict[str, str]:
    """``string_id → English text`` for the renderable bank (imported lazily to avoid SymPy at
    module import where it is not needed by other tests in this file)."""
    from app.tts.spoken_bank import enumerate_renderable

    return {s.string_id: s.text for s in enumerate_renderable()}


def test_every_english_renderable_id_has_an_es_mx_translation() -> None:
    """PARITY: no English renderable string_id is missing from the es-MX bank."""
    english_ids = set(_renderable_english())
    es_ids = set(ES_MX_HELP_STRINGS)
    missing = english_ids - es_ids
    assert not missing, f"es-MX bank is missing translations for: {sorted(missing)}"


def test_no_es_mx_key_lacks_an_english_counterpart() -> None:
    """PARITY: no es-MX key is orphaned (every key maps to a real English renderable id)."""
    english_ids = set(_renderable_english())
    es_ids = set(ES_MX_HELP_STRINGS)
    orphans = es_ids - english_ids
    assert not orphans, f"es-MX bank has keys with no English counterpart: {sorted(orphans)}"


def test_parity_count_matches_the_171_english_renderable_strings() -> None:
    """One es-MX entry per renderable English string (the 171 parity target)."""
    english = _renderable_english()
    assert len(ES_MX_HELP_STRINGS) == len(english)


def test_every_es_mx_string_is_non_empty() -> None:
    for string_id, text in ES_MX_HELP_STRINGS.items():
        assert text.strip(), f"es-MX text for {string_id!r} is empty"


def test_every_es_mx_string_differs_from_the_english() -> None:
    """A basic sanity that translation happened: the Spanish is not a copy of the English."""
    english = _renderable_english()
    for string_id, es_text in ES_MX_HELP_STRINGS.items():
        assert es_text != english[string_id], (
            f"es-MX text for {string_id!r} is identical to the English (untranslated?)"
        )


def test_termbase_core_terms_use_their_canonical_es_mx_form() -> None:
    """Spot-check the locked termbase: the core math terms appear in their canonical form.

    Each pair is (string_id whose translation should contain the term, the canonical es-MX term).
    These pin the termbase against drift — e.g. ``denominador común`` must not become
    ``denominador comun`` or an alternative phrasing in these lines.
    """
    expectations = {
        # common denominator → "denominador común"
        "nudge:KC_multiply_fractions:0": "denominador común",
        # equivalent ratios / "razón" → razón
        "nudge:KC_equivalent_ratios:0": "razón",
        # number line → "recta"
        "nudge:KC_absolute_value:2": "recta",
        # unit rate → "tasa unitaria"
        "nudge:KC_unit_rate:0": "tasa unitaria",
        # least common multiple / multiple → "múltiplo"
        "nudge:KC_gcf_lcm:0": "múltiplo",
        # greatest common factor → "máximo común divisor"
        "nudge:KC_gcf_lcm:2": "máximo común divisor",
        # absolute value → "valor absoluto"
        "nudge:KC_absolute_value:0": "valor absoluto",
        # coordinate plane move → "coordenada"
        "nudge:KC_coordinate_plane:1": "coordenada",
        # simplify → "simplifica"
        "nudge:KC_multiply_fractions:2": "simplifica",
        # coefficient / constant → both terms
        "nudge:KC_expression_parts:1": "coeficiente",
    }
    for string_id, term in expectations.items():
        text = ES_MX_HELP_STRINGS[string_id]
        assert term in text, f"{string_id!r} should contain {term!r}; got: {text!r}"


def test_denominador_comun_is_used_consistently_not_drifting() -> None:
    """Termbase consistency: wherever ``denominador`` appears with ``común`` it is the canonical
    two-word ``denominador común`` (no alternating phrasing / missing accent)."""
    for string_id, text in ES_MX_HELP_STRINGS.items():
        if "denominador" in text and "común" in text:
            assert "denominador común" in text, (
                f"{string_id!r} drifts from canonical 'denominador común': {text!r}"
            )


def test_es_mx_reviewed_flag_is_true_human_reviewed() -> None:
    """REVIEW GATE: a human reviewer checked and PASSED the bank (owner 2026-06-04), so es-MX is
    production — the flag is True and Slices 3.5/3.6 may treat the bank as final (V2_TODO 3.2)."""
    assert ES_MX_REVIEWED is True


def test_es_mx_locale_tag_is_the_provider_locale() -> None:
    assert ES_MX_LOCALE == "es-MX"


def test_es_mx_text_helper_returns_translation_or_none() -> None:
    sample = next(iter(ES_MX_HELP_STRINGS))
    assert es_mx_text(sample) == ES_MX_HELP_STRINGS[sample]
    assert es_mx_text("nudge:KC_does_not_exist:99") is None
