"""Structural guard for ARCHITECTURE.md §14 invariant 8 (Slice PL.3).

Invariant 8: the verified IDENTITY (sub/email) must NEVER reach the mastery model, the
policy, or the LLM. The auth layer produces only a ``learner_id`` used for
persistence/continuity; the turn decision (verify → mastery → policy → helpneed) must not
see identity.

We enforce the auth-side half structurally, the same way the chat-baseline arm proves it
never imports the verifier/mastery model: ``app/auth/google.py`` — the module that holds the
verified identity — must NOT import ``app.mastery`` / ``app.policy`` / ``app.llm`` /
``app.domain``. (A static import check is the right tool here: it catches the dependency the
moment it is added, independent of runtime paths.)

We also pin the other half — that the turn loop stays identity-free — by asserting the
``/turn`` processing entrypoint's signature does not take an identity/learner argument: it is
driven solely by the ``TurnRequest`` (session_id, problem_id, action, ...). Auth only changes
WHICH learner row persistence/continuity uses, never the turn decision.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from app.api.service import SessionStore

# The layers the verified identity must never reach (invariant 8). The auth module that
# holds the identity must not import any of these.
_FORBIDDEN_IMPORTS = ("app.mastery", "app.policy", "app.llm", "app.domain")


def _imported_modules(path: str) -> set[str]:
    """The set of module names this file imports (parsed from the AST, not text-matched).

    AST parsing (not a substring scan) is the right tool: it inspects the actual ``import`` /
    ``from ... import`` statements, so a layer name merely MENTIONED in a docstring or comment
    does not trip the guard — only a real dependency does.
    """
    tree = ast.parse(Path(path).read_text())
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_auth_google_imports_no_mastery_policy_llm_or_domain() -> None:
    """app/auth/google.py imports none of the layers identity must never reach (invariant 8)."""
    imported = _imported_modules("app/auth/google.py")
    for forbidden in _FORBIDDEN_IMPORTS:
        offending = {m for m in imported if m == forbidden or m.startswith(forbidden + ".")}
        assert not offending, (
            f"app/auth/google.py must not import {forbidden} (invariant 8: identity never "
            f"reaches mastery/policy/LLM/domain); found {offending}"
        )


def test_turn_processing_signature_takes_no_identity() -> None:
    """The /turn entrypoint is driven by TurnRequest alone — it never takes an identity.

    The turn decision must not see identity (invariant 8). ``SessionStore.process_turn`` is
    the seam the /turn route calls; its only parameter is the ``TurnRequest`` wire model, so
    there is no channel for sub/email to enter the verify→mastery→policy→helpneed path.
    """
    params = list(inspect.signature(SessionStore.process_turn).parameters)
    # ``self`` + ``request`` only — no ``identity`` / ``learner`` / ``google_sub`` parameter.
    assert params == ["self", "request"]
