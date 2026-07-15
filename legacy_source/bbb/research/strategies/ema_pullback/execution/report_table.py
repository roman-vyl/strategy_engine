"""Stdout comparison table rendering for ema_pullback variants."""

from __future__ import annotations

from typing import Any

from research.strategies.ema_pullback.execution.result_models import VariantResult


def _flatten_metrics(prefix: str, metrics: Any) -> dict[str, float | int | None]:
    if hasattr(metrics, "trades"):
        return {
            f"{prefix}_trades": metrics.trades,
            f"{prefix}_pnl": metrics.pnl,
            f"{prefix}_return_pct": metrics.return_pct,
            f"{prefix}_profit_factor": metrics.profit_factor,
            f"{prefix}_win_rate": metrics.win_rate,
        }
    return {
        f"{prefix}_trades": metrics["trades"],
        f"{prefix}_pnl": metrics["pnl"],
        f"{prefix}_return_pct": metrics["return_pct"],
        f"{prefix}_profit_factor": metrics["profit_factor"],
        f"{prefix}_win_rate": metrics["win_rate"],
    }


def comparison_row(variant_result: VariantResult | dict[str, Any]) -> dict[str, float | int | str | None]:
    """Flatten a variant result for the stdout comparison table."""

    if isinstance(variant_result, VariantResult):
        anchor_stack = variant_result.strategy_spec["anchor_stack"]
        ot = variant_result.metrics.open_trades
        return {
            "variant": variant_result.variant,
            "config_id": variant_result.config_id,
            "fast": anchor_stack["fast"]["period"],
            "anchor": anchor_stack["anchor"]["period"],
            "slow": anchor_stack["slow"]["period"],
            **_flatten_metrics("long", variant_result.metrics.long),
            **_flatten_metrics("short", variant_result.metrics.short),
            **_flatten_metrics("total", variant_result.metrics.total),
            "total_sharpe": variant_result.metrics.sharpe,
            "total_max_drawdown": variant_result.metrics.max_drawdown,
            "open_trades_long": ot.long,
            "open_trades_short": ot.short,
            "open_trades_total": ot.total,
        }

    m = variant_result["metrics"]
    anchor_stack = variant_result["strategy_spec"]["anchor_stack"]
    total_block = m["total"]
    ot = m["open_trades"]
    return {
        "variant": variant_result["variant"],
        "config_id": variant_result["config_id"],
        "fast": anchor_stack["fast"]["period"],
        "anchor": anchor_stack["anchor"]["period"],
        "slow": anchor_stack["slow"]["period"],
        **_flatten_metrics("long", m["long"]),
        **_flatten_metrics("short", m["short"]),
        **_flatten_metrics(
            "total",
            {k: total_block[k] for k in ("trades", "pnl", "return_pct", "profit_factor", "win_rate")},
        ),
        "total_sharpe": total_block["sharpe"],
        "total_max_drawdown": total_block["max_drawdown"],
        "open_trades_long": ot["long"],
        "open_trades_short": ot["short"],
        "open_trades_total": ot["total"],
    }


def _format_cell(value: float | int | str | None) -> str:
    if value is None:
        return "null"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def print_comparison_table(rows: list[dict[str, float | int | str | None]]) -> None:
    headers = (
        "variant",
        "config_id",
        "fast",
        "anchor",
        "slow",
        "long_trades",
        "long_pnl",
        "long_return_pct",
        "long_profit_factor",
        "long_win_rate",
        "short_trades",
        "short_pnl",
        "short_return_pct",
        "short_profit_factor",
        "short_win_rate",
        "total_trades",
        "total_pnl",
        "total_return_pct",
        "total_profit_factor",
        "total_win_rate",
        "total_sharpe",
        "total_max_drawdown",
        "open_trades_long",
        "open_trades_short",
        "open_trades_total",
    )
    rendered: list[dict[str, str]] = []
    for row in rows:
        rendered.append({h: _format_cell(row[h]) for h in headers})

    widths = {h: len(h) for h in headers}
    for row in rendered:
        for h in headers:
            widths[h] = max(widths[h], len(row[h]))

    separator = "-+-".join("-" * widths[h] for h in headers)
    print(" | ".join(h.ljust(widths[h]) for h in headers))
    print(separator)
    for row in rendered:
        print(" | ".join(row[h].ljust(widths[h]) for h in headers))
