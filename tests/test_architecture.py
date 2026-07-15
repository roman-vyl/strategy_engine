from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parents[1]
SRC = ROOT / "src" / "strategy_engine"


def imports_under(path: Path) -> set[str]:
    imports: set[str] = set()
    for file in path.rglob("*.py"):
        tree = ast.parse(file.read_text(), filename=str(file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
    return imports


def test_domain_is_framework_and_legacy_free() -> None:
    imports = imports_under(SRC / "domain")
    forbidden = ("fastapi", "httpx", "pandas", "numpy", "research", "legacy_source")
    assert not any(name.startswith(forbidden) for name in imports)


def test_application_does_not_import_concrete_adapters() -> None:
    imports = imports_under(SRC / "indicators" / "application") | imports_under(
        SRC / "strategies" / "application"
    )
    assert not any(name.startswith("strategy_engine.adapters") for name in imports)


def test_production_package_never_imports_legacy_or_bbb() -> None:
    imports = imports_under(SRC)
    forbidden = ("legacy_source", "research", "research_api", "data_engine")
    assert not any(name.startswith(forbidden) for name in imports)


def test_http_routes_do_not_own_indicator_or_strategy_semantics() -> None:
    text = "\n".join(path.read_text() for path in (SRC / "adapters" / "http").glob("*.py"))
    assert "pandas" not in text
    assert "numpy" not in text
    assert "def calculate_ema" not in text
    assert "sqlite" not in text.lower()
