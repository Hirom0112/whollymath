"""The five UI surface states — the shared vocabulary for the adaptive UI.

ARCHITECTURE.md §7 / PROJECT.md §3.5: the interface adapts across exactly five
enumerated surface states ("adapt with restraint", ARCHITECTURE.md §2). Those
states are the *policy's* vocabulary — the adaptation policy (Slice 2.4) routes
between them, the tutor session loop reports the current one, and the API speaks
them on the wire. So the enum lives here in ``policy/`` as the single source of
truth (ARCHITECTURE.md §4), and every other layer imports it forward — rather than
any one outer layer (e.g. the API) owning it and inner layers reaching across the
boundary for it.

A ``StrEnum`` so each member serializes as its stable string for the DB, the API,
and the generated TS union. There is NO transition logic here yet — that is Slice
2.4; this module is only the closed set of states.
"""

from __future__ import annotations

from enum import StrEnum


class SurfaceState(StrEnum):
    """The five enumerated UI surface states (ARCHITECTURE.md §7, PROJECT.md §3.5).

    The turn loop carries the learner's *current* surface state in and returns the
    *next* surface state out (ARCHITECTURE.md §10). There are exactly five — "adapt
    with restraint" (ARCHITECTURE.md §2). Changing a VALUE is a breaking change to
    the DB, the wire contract, and the generated TS union.
    """

    SYMBOLIC_FOCUS = "S1_symbolic_focus"
    NUMBER_LINE_PRIMARY = "S2_number_line_primary"
    FRACTION_BARS_PRIMARY = "S3_fraction_bars_primary"
    WORKED_EXAMPLE = "S4_worked_example"
    TRANSFER_PROBE = "S5_transfer_probe"
