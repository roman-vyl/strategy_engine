"""Guards the raw_spec_identity.py dependency-neutral DAG (design.md).

`raw_spec_identity.py` must never import from any family execution
module, `feature_plan.py`, or `static_semantics.py` -- those modules
import *from* it. A reintroduced import edge in that direction would
recreate the `feature_plan.py -> exits.py -> feature_plan.py`-style
cycle this module exists to avoid.
"""

from __future__ import annotations

import ast
from pathlib import Path

_FORBIDDEN_MODULE_SUFFIXES = (
    "feature_plan",
    "exits",
    "setups",
    "direction_blockers",
    "triggers",
    "risk",
    "static_semantics",
)


def _module_path() -> Path:
    import strategy_engine.strategies.ema_pullback.raw_spec_identity as module

    return Path(module.__file__)


def test_raw_spec_identity_has_no_import_edge_back_to_consumers() -> None:
    tree = ast.parse(_module_path().read_text(encoding="utf-8"))
    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)
        elif isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)

    for module_name in imported_modules:
        for suffix in _FORBIDDEN_MODULE_SUFFIXES:
            assert not module_name.endswith(f".{suffix}"), (
                f"raw_spec_identity.py must not import {module_name!r} "
                "-- it would recreate an import cycle"
            )
