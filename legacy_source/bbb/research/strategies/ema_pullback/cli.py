"""Shared CLI argument parsing for ema_pullback entrypoints."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="EMA pullback research runner (external config only)."
    )
    p.add_argument(
        "--config",
        type=Path,
        required=True,
        help="External single-file strategy experiment config (YAML/JSON)",
    )
    p.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Override SQLite path (default: Settings / DATA_ENGINE_DB_PATH)",
    )
    return p.parse_args(argv)
