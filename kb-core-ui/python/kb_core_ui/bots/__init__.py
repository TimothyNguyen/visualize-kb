"""Bot roster and runner — the Python side of internal/bots/.

Bots are executed by re-invoking the kb-core-ui entrypoint
(`kb-core-ui bot <name> ...`), so the CLI and web paths run identical code.
"""

from kb_core_ui.bots.registry import REGISTRY, ArgDef, Def, lookup
from kb_core_ui.bots.runner import (
    MissingArgError,
    Run,
    RunSummary,
    Runner,
    UnknownBotError,
    build_args,
)

__all__ = [
    "REGISTRY",
    "ArgDef",
    "Def",
    "lookup",
    "Run",
    "RunSummary",
    "Runner",
    "UnknownBotError",
    "MissingArgError",
    "build_args",
]
