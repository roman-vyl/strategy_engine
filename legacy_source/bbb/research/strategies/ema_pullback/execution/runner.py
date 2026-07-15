"""StrategySpec orchestration for ema_pullback research runs."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from research.experiments.config_loader import LoadedExternalConfig, load_strategy_config_file
from research.strategies.ema_pullback.config import execution_config_from_external
from research.strategies.ema_pullback.execution.backtest import run_strategy_spec
from research.strategies.ema_pullback.execution.data_loader import load_candles_once
from research.strategies.ema_pullback.execution.report_table import (
    comparison_row,
    print_comparison_table,
)
from research.strategies.ema_pullback.execution.results import (
    build_research_run_payload,
    build_run_id,
    default_results_dir,
    write_research_results,
)
from research.strategies.ema_pullback.spec import EmaPullbackStrategySpec

_ROOT = Path(__file__).resolve().parents[4]


def run_strategy_specs_from_config(
    config_source_file: str | Path,
    *,
    db_path: Path | None = None,
    run_id_suffix: str | None = None,
) -> str:
    loaded_config = load_strategy_config_file(config_source_file)
    specs = _validated_specs_for_single_market(loaded_config)
    ex = loaded_config.execution
    run_config = execution_config_from_external(
        family=loaded_config.family,
        symbol=specs[0].symbol,
        timeframe=specs[0].base_timeframe,
        db_path=db_path,
        init_cash=ex.init_cash,
        fees=ex.fees,
        slippage=ex.slippage,
    )
    loaded = load_candles_once(run_config)
    variant_results = [
        run_strategy_spec(
            spec,
            loaded.ohlcv,
            init_cash=run_config.init_cash,
            fees=run_config.fees,
            slippage=run_config.slippage,
        )
        for spec in specs
    ]

    print(
        f"family={run_config.family} experiment_id={loaded_config.experiment_id} "
        f"symbol={run_config.symbol} timeframe={run_config.timeframe} "
        f"candles={loaded.candles_count} variants={len(specs)}"
    )
    print_comparison_table([comparison_row(v) for v in variant_results])

    created_at = datetime.now(timezone.utc)
    run_id = build_run_id(
        created_at,
        run_config.family,
        run_config.symbol,
        run_config.timeframe,
        suffix=run_id_suffix,
    )
    payload = build_research_run_payload(
        run_id=run_id,
        created_at=created_at,
        family=run_config.family,
        symbol=run_config.symbol,
        timeframe=run_config.timeframe,
        candles_count=loaded.candles_count,
        data_range_from_ms=loaded.from_open_time_ms,
        data_range_to_ms=loaded.to_open_time_ms,
        variants=[v.to_payload() for v in variant_results],
        batch_metadata=_batch_success_metadata(loaded_config),
    )
    latest_path, run_path, summary_path = write_research_results(payload)
    print(f"results_artifact={latest_path.relative_to(_ROOT).as_posix()}")
    print(f"run_artifact={run_path.relative_to(_ROOT).as_posix()}")
    print(f"summary_artifact={summary_path.relative_to(_ROOT).as_posix()}")
    print("status=ok")
    return run_id


def run_strategy_specs_from_config_returning_paths(
    config_source_file: str | Path,
    *,
    db_path: Path | None = None,
    run_id_suffix: str | None = None,
) -> tuple[str, Path, Path]:
    """Run one external config and return ``(run_id, latest_path, run_path)``."""

    run_id = run_strategy_specs_from_config(
        config_source_file,
        db_path=db_path,
        run_id_suffix=run_id_suffix,
    )
    base = default_results_dir()
    run_path = base / "runs" / f"{run_id}.json"
    latest_path = base / "latest.json"
    return run_id, latest_path, run_path


def _validated_specs_for_single_market(
    loaded_config: LoadedExternalConfig,
) -> tuple[EmaPullbackStrategySpec, ...]:
    specs = tuple(loaded_config.specs)
    if not specs:
        raise ValueError("external config produced no strategy specs")
    first = specs[0]
    if not isinstance(first, EmaPullbackStrategySpec):
        raise TypeError("external config produced unsupported strategy spec type")
    for spec in specs:
        if not isinstance(spec, EmaPullbackStrategySpec):
            raise TypeError("external config produced unsupported strategy spec type")
        if spec.symbol != first.symbol or spec.base_timeframe != first.base_timeframe:
            raise ValueError("all external config instances must share symbol and base_timeframe in MVP")
    return specs


def _batch_success_metadata(loaded_config: LoadedExternalConfig) -> dict[str, object]:
    entries = [
        {
            **entry.to_payload(),
            "status": "success",
        }
        for entry in loaded_config.entries
    ]
    return {
        **loaded_config.identity_payload(),
        "validation_phase_status": "passed",
        "entries": entries,
        "counters": {
            "total": len(entries),
            "success": len(entries),
            "failed": 0,
        },
    }
