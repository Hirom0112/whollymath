"""Enumerate the FINITE spoken-string bank the avatar voices (Slice A).

This is the single place that walks the tutor copy banks and decides WHICH strings the
build-time renderer (``app/tts/batch.py``) turns into cached Hope audio. The avatar's
speakable lines live across a few modules; this module reads them and yields one
``SpokenString`` per voiceable line, each with a STABLE ``string_id`` (the manifest key the
frontend looks up) and its source-bank provenance.

The rule: PRE-RENDER the strings that have NO variable numbers (a finite, fixed bank). Strings
WITH variable numbers — problem restatements, number-specific worked-example steps, misconception
descriptions that quote concrete numbers — are NOT baked into the bank; they are voiced at serve
time by live synth (``app/tts/live_synth.py``, content-hash cached in the same Hope voice).
``has_variable_numbers`` is the deterministic test that splits the two; ``enumerate_renderable``
returns only the variable-free lines and ``enumerate_deferred`` returns the rest (so the split is
auditable, not silent).

What is in v1 scope (all variable-free):

  - ``NUDGE_BANK`` (``tutor/hints.py``): every nudge — deliberately digit-free conceptual
    prompts (the module already scans the bank to forbid digits/glyphs), so the WHOLE nudge
    bank renders. This is exactly the help-string subset slice 3.6 / the avatar needs.
  - Misconception ``name`` strings (``domain/misconceptions.py``): short human-readable labels,
    digit-free, useful for avatar framing ("that looks like an add-across error").

What is FLAGGED for splicing (number-templated):

  - Worked-example narration (``tutor/worked_example.py``): built at runtime with f-strings
    over a specific ``Problem``'s operands — every step quotes concrete numbers, so it is NOT a
    fixed-phrase render. These dynamic lines are voiced at serve time by live synth
    (``app/tts/live_synth.py``, content-hash cached), not pre-rendered to the bank.
  - Misconception ``description`` strings that quote concrete examples (e.g. "1/4 + 1/4 = 2/8")
    — flagged when they contain digits.
  - Any problem restatement (the live problem text) — inherently per-problem numbers.

No LLM, no SymPy, no network, no DB: a deterministic read over in-process banks (CLAUDE.md
§8.1). Same banks ⇒ same enumeration every call.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

from app.domain.misconceptions import MISCONCEPTION_REGISTRY
from app.tts.provider import Locale
from app.tutor.hints import NUDGE_BANK
from app.tutor.hints_es import ES_MX_LOCALE, es_mx_text

# A line is "number-templated" if it contains a DIGIT. Variable-number lines (problem
# restatements, worked-example steps) always carry concrete numerals; the fixed conceptual
# copy we render in v1 is digit-free by construction (the nudge bank is digit-scanned in
# tutor/hints.py; misconception names are labels). This is a deliberately simple, reviewable
# split (CLAUDE.md §8.5) — a digit is the unambiguous signal that a line is per-problem.
_DIGIT_RE = re.compile(r"\d")


@dataclass(frozen=True)
class SpokenString:
    """One voiceable line of the finite bank, with its stable manifest key and provenance.

    Frozen — an enumerated line is a fact about the bank, not mutable state. Fields:

    - ``string_id``  the STABLE manifest key the frontend looks up (``<source>:<slug>``). It is
      derived from the source bank + a stable discriminator (KC + index, or misconception id),
      NOT from the text, so re-wording a line keeps its id while the content hash (computed in
      the batch renderer) changes — the manifest carries both.
    - ``text``       the exact words to voice.
    - ``source``     which bank it came from (``nudge`` / ``misconception_name``), for auditing.
    """

    string_id: str
    text: str
    source: str


def nudge_string_id(kc_value: str, index: int) -> str:
    """The stable manifest ``string_id`` for the nudge at ``index`` of KC ``kc_value``.

    The single source of truth for the nudge id FORMAT (``nudge:<kc>:<index>``): the build-time
    enumeration (``_all_spoken_strings``) and any runtime lookup that wants a banked nudge's audio
    (``api`` → ``manifest_lookup``) both derive the key here, so the manifest key the renderer
    wrote and the key the API looks up can never drift. Pure; ``kc_value`` is the KC enum's value.
    """
    return f"nudge:{kc_value}:{index}"


def text_for_locale(spoken: SpokenString, locale: Locale) -> str:
    """The text to VOICE for ``spoken`` in ``locale`` — English text, or its es-MX translation.

    This is the single seam that makes the batch renderer locale-aware (Slice 3.2a). The English
    bank holds the source text on ``SpokenString.text``; the es-MX bank (``tutor/hints_es.py``) is
    a parallel ``string_id → Spanish`` map. For ``en`` we return the English source verbatim; for
    ``es-MX`` we return the Mexican-Spanish translation keyed by the SAME ``string_id`` so the
    renderer voices Spanish for the Spanish manifest entry rather than re-voicing English.

    If a renderable id has no es-MX entry we fall back to the English text (so a future gap voices
    *something* rather than crashing the build); the parity test guarantees there is no such gap in
    the shipped bank, so the fallback is a safety net, not the normal path. Pure: same inputs ⇒
    same text every call (CLAUDE.md §8.1 — this is offline build data, no LLM/network).

    NOTE (review gate): the es-MX text is human-reviewed and PASSED (``hints_es.ES_MX_REVIEWED`` is
    True, owner 2026-06-04), so the rendered es-MX audio is production for Slices 3.5/3.6.
    """
    if locale == ES_MX_LOCALE:
        translated = es_mx_text(spoken.string_id)
        if translated is not None:
            return translated
    return spoken.text


def has_variable_numbers(text: str) -> bool:
    """True iff ``text`` is number-templated (carries a digit) — the deferral test.

    Variable-number lines (problem restatements, numeric worked-example steps) are voiced by
    serve-time live synth rather than rendered as fixed phrases; variable-free
    conceptual copy renders in v1. Deterministic and pure.
    """
    return _DIGIT_RE.search(text) is not None


def _all_spoken_strings() -> Iterator[SpokenString]:
    """Walk every voiceable bank and yield one ``SpokenString`` per candidate line.

    Yields BOTH variable-free and number-templated candidates; the split into rendered vs
    deferred is done by ``enumerate_renderable`` / ``enumerate_deferred`` so the same source
    of truth feeds both and nothing is dropped silently.
    """
    # ── NUDGE_BANK (tutor/hints.py): KC + position make a stable id; all are digit-free. ──
    for kc, nudges in NUDGE_BANK.items():
        for index, nudge in enumerate(nudges):
            yield SpokenString(
                string_id=nudge_string_id(kc.value, index),
                text=nudge.text,
                source="nudge",
            )

    # ── Misconception copy (domain/misconceptions.py): names are digit-free labels (v1);
    #    descriptions often quote concrete numbers, so they fall to the deferred set. ──
    for misconception in MISCONCEPTION_REGISTRY.all():
        yield SpokenString(
            string_id=f"misconception_name:{misconception.id.value}",
            text=misconception.name,
            source="misconception_name",
        )


def enumerate_renderable() -> tuple[SpokenString, ...]:
    """The variable-free lines rendered in v1, in deterministic bank order.

    These are the fixed conceptual phrases (nudges, misconception labels) with no per-problem
    numbers — the FIXED-PHRASE bank the avatar voices today.
    """
    return tuple(s for s in _all_spoken_strings() if not has_variable_numbers(s.text))


def enumerate_deferred() -> tuple[SpokenString, ...]:
    """The number-templated lines NOT pre-rendered to the fixed bank.

    Returned (not dropped) so the split is auditable: a caller / report can list exactly which lines
    are number-templated. These are voiced at serve time by live synth (``app/tts/live_synth.py``,
    content-hash cached) rather than baked into the build-time bank.
    """
    return tuple(s for s in _all_spoken_strings() if has_variable_numbers(s.text))


__all__ = [
    "Locale",
    "SpokenString",
    "enumerate_deferred",
    "enumerate_renderable",
    "has_variable_numbers",
    "nudge_string_id",
    "text_for_locale",
]
