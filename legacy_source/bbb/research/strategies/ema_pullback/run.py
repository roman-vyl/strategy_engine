"""CLI entrypoint for ema_pullback StrategySpec research runs.

Run from repo root (after ``pip install -e ".[research]"``):

    python research/strategies/ema_pullback/run.py --config path/to/experiment.yaml
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running this file without PYTHONPATH tricks.
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from research.strategies.ema_pullback.cli import parse_args  # noqa: E402
from research.strategies.ema_pullback.execution.runner import run_strategy_specs_from_config  # noqa: E402


def main() -> None:
    args = parse_args()
    run_strategy_specs_from_config(args.config, db_path=args.db_path)


if __name__ == "__main__":
    main()
