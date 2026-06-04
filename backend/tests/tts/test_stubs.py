"""Tests pinning the inert stub (Slice A): it ships NO behavior and fails loudly if called.

The Rhubarb viseme upgrade is a documented seam, not a feature (CLAUDE.md §5 "report partial as
partial") — an OPTIONAL acoustic upgrade needing an external binary; phoneme lip-sync already ships
via grapheme→viseme derivation (frontend ``avatar/visemes.ts``). This test asserts the seam stays
inert so it cannot be mistaken for working code. (The old number-splicing seam was deleted —
superseded by live synth, ``app/tts/live_synth.py``, which voices number-templated lines directly.)
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

# rhubarb_visemes.stub is not an importable module name via dotted path (the ".stub" suffix is
# deliberate), so load it by file location to exercise its inert contract.
_TTS_DIR = Path(__file__).resolve().parents[2] / "app" / "tts"


def _load_stub_module(filename: str, name: str) -> Any:  # Any: a path-loaded module is untyped

    spec = importlib.util.spec_from_file_location(name, _TTS_DIR / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rhubarb_stub_is_inert() -> None:
    module = _load_stub_module("rhubarb_visemes.stub.py", "rhubarb_visemes_stub")
    assert module.IS_STUB is True
    with pytest.raises(NotImplementedError):
        module.rhubarb_visemes_for(Path("anything.mp3"))
