"""Architecture invariants for the pure live-history planning chain:

1. The whole chain -- live_calculation/ plus the ema_pullback
   strategy-semantic resolver it (indirectly) composes with -- must stay
   free of MDS/pandas/HTTP dependencies. Covering only live_calculation/
   would leave the strategy resolver, which is just as much a part of the
   pure planning chain (design.md Decision 3), protected by comment alone.

2. Dependency direction: live_calculation/ is generic and must never import
   a concrete strategy-family package (e.g. ema_pullback). It depends only
   on the StrategyHistoryRequirements Protocol in contracts.py (design.md
   Decision 2/12); which concrete family backs that Protocol is a
   composition-layer decision made outside live_calculation/, not something
   the generic planner imports or defaults to.
"""

from __future__ import annotations

import ast
import importlib
import pkgutil

import strategy_engine.strategies.ema_pullback.live_calculation_requirements as resolver_module
import strategy_engine.strategies.live_calculation as live_calculation_pkg

_FORBIDDEN_MODULE_PREFIXES = (
    "pandas",
    "numpy",
    "requests",
    "httpx",
    "aiohttp",
    "strategy_engine.adapters",
    "strategy_engine.ports.market_data",
)

# Concrete strategy-family packages live_calculation/ must never import
# (invariant 2 above). Only ema_pullback exists today; add future concrete
# strategy families here rather than loosening the check.
_FORBIDDEN_STRATEGY_FAMILY_PREFIXES = ("strategy_engine.strategies.ema_pullback",)


def _imported_module_names(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _assert_module_source_has_no_forbidden_import(module_name: str, file_path: str) -> None:
    with open(file_path, encoding="utf-8") as handle:
        source = handle.read()
    imported = _imported_module_names(source)
    for name in imported:
        for forbidden in _FORBIDDEN_MODULE_PREFIXES:
            assert not name.startswith(forbidden), (
                f"{module_name} imports forbidden dependency {name}"
            )


def _assert_module_source_has_no_forbidden_strategy_family_import(
    module_name: str, file_path: str
) -> None:
    with open(file_path, encoding="utf-8") as handle:
        source = handle.read()
    imported = _imported_module_names(source)
    for name in imported:
        for forbidden in _FORBIDDEN_STRATEGY_FAMILY_PREFIXES:
            assert not name.startswith(forbidden), (
                f"{module_name} imports concrete strategy-family package {name} -- "
                "live_calculation/ must depend only on StrategyHistoryRequirements"
            )


def test_live_calculation_modules_import_no_forbidden_dependency() -> None:
    package = live_calculation_pkg
    module_infos = list(
        pkgutil.walk_packages(package.__path__, prefix=f"{package.__name__}.")
    )
    assert module_infos, "expected live_calculation submodules to exist"
    for module_info in module_infos:
        module = importlib.import_module(module_info.name)
        _assert_module_source_has_no_forbidden_import(module_info.name, module.__file__)


def test_live_calculation_modules_do_not_import_concrete_strategy_families() -> None:
    package = live_calculation_pkg
    module_infos = list(
        pkgutil.walk_packages(package.__path__, prefix=f"{package.__name__}.")
    )
    assert module_infos, "expected live_calculation submodules to exist"
    for module_info in module_infos:
        module = importlib.import_module(module_info.name)
        _assert_module_source_has_no_forbidden_strategy_family_import(
            module_info.name, module.__file__
        )


def test_ema_pullback_live_calculation_requirements_imports_no_forbidden_dependency() -> None:
    """The strategy-specific half of the pure planning chain lives outside
    live_calculation/ (design.md Decision 2), so it needs its own explicit
    architecture assertion rather than relying on the package-scoped test
    above."""

    module = resolver_module
    _assert_module_source_has_no_forbidden_import(module.__name__, module.__file__)
