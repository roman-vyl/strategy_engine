"""Pre-market validation for immutable executed-trade receipts."""

from __future__ import annotations

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.ranges import timeframe_duration_ms
from strategy_engine.domain.values import parse_normalized_decimal_text
from strategy_engine.strategies.contracts import OpenTradeProjectionRequest

_SUPPORTED_SIDES = frozenset({"long", "short"})
_SUPPORTED_PROFILES = frozenset({"always_on", "aligned", "countertrend", "neutral"})

def validate_open_trade_request(request: OpenTradeProjectionRequest) -> None:
    receipt = request.executed_trade_receipt
    if receipt.side not in _SUPPORTED_SIDES:
        raise InvalidRequestError("side must be long or short", side=receipt.side)
    if receipt.locked_exit_profile not in _SUPPORTED_PROFILES:
        raise InvalidRequestError(
            "locked_exit_profile is unsupported",
            locked_exit_profile=receipt.locked_exit_profile,
        )

    step_ms = timeframe_duration_ms(request.market.base_timeframe)
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
