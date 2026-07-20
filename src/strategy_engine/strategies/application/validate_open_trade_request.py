"""Pre-market validation for immutable executed-trade receipts."""

from __future__ import annotations

import re

from strategy_engine.domain.errors import InvalidRequestError, TradeContractMismatchError
from strategy_engine.domain.ranges import timeframe_duration_ms
from strategy_engine.domain.values import parse_normalized_decimal_text
from strategy_engine.strategies.contracts import OpenTradeProjectionRequest

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_SUPPORTED_SIDES = frozenset({"long", "short"})
_SUPPORTED_PROFILES = frozenset({"always_on", "aligned", "countertrend", "neutral"})


def _require_non_empty(name: str, value: str) -> None:
    if not value.strip():
        raise InvalidRequestError(f"{name} must be non-empty", field=name)


def validate_open_trade_request(request: OpenTradeProjectionRequest) -> None:
    receipt = request.executed_trade_receipt
    for name in (
        "trade_id",
        "instance_id",
        "strategy_id",
        "strategy_version",
        "ticker",
        "base_timeframe",
        "abi_entry_correlation",
    ):
        _require_non_empty(name, getattr(receipt, name))

    if not _HASH_RE.fullmatch(receipt.source_config_hash):
        raise InvalidRequestError("source_config_hash must be lowercase SHA-256")
    if receipt.side not in _SUPPORTED_SIDES:
        raise InvalidRequestError("side must be long or short", side=receipt.side)
    if receipt.locked_exit_profile not in _SUPPORTED_PROFILES:
        raise InvalidRequestError(
            "locked_exit_profile is unsupported",
            locked_exit_profile=receipt.locked_exit_profile,
        )

    step_ms = timeframe_duration_ms(receipt.base_timeframe)
    for name in ("source_plan_bar_open_time_ms", "entry_bar_open_time_ms"):
        value = getattr(receipt, name)
        if value < 0 or value % step_ms != 0:
            raise InvalidRequestError(f"{name} must be base-timeframe aligned", field=name)
    if request.target_bar_open_time_ms < 0 or request.target_bar_open_time_ms % step_ms != 0:
        raise InvalidRequestError("target_bar_open_time_ms must be base-timeframe aligned")
    if not (
        receipt.source_plan_bar_open_time_ms
        <= receipt.entry_bar_open_time_ms
        <= request.target_bar_open_time_ms
    ):
        raise InvalidRequestError("trade timestamps must satisfy source_plan <= entry <= target")

    planned = parse_normalized_decimal_text(receipt.planned_entry_price)
    executed = parse_normalized_decimal_text(receipt.executed_entry_price)
    stop = parse_normalized_decimal_text(receipt.initial_stop_price)
    take = parse_normalized_decimal_text(receipt.initial_take_price)
    if any(value <= 0 for value in (planned, executed, stop, take)):
        raise InvalidRequestError("receipt prices must be positive")
    valid_geometry = stop < planned < take if receipt.side == "long" else take < planned < stop
    if not valid_geometry:
        raise InvalidRequestError("receipt stop/entry/take geometry is invalid")

    mismatches: dict[str, object] = {}
    if request.strategy.strategy_id != receipt.strategy_id:
        mismatches["strategy_id"] = receipt.strategy_id
    if request.strategy.strategy_version != receipt.strategy_version:
        mismatches["strategy_version"] = receipt.strategy_version
    if request.strategy.instance_id != receipt.instance_id:
        mismatches["instance_id"] = receipt.instance_id
    if request.market.ticker != receipt.ticker:
        mismatches["ticker"] = receipt.ticker
    if request.market.base_timeframe != receipt.base_timeframe:
        mismatches["base_timeframe"] = receipt.base_timeframe
    if request.strategy.config_hash != receipt.source_config_hash:
        mismatches["source_config_hash"] = receipt.source_config_hash
    if mismatches:
        raise TradeContractMismatchError(mismatches=mismatches)
