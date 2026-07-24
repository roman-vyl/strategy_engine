from dataclasses import FrozenInstanceError, replace

import pytest

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.market import MarketStream
from strategy_engine.strategies.application.validate_open_trade_request import (
    validate_open_trade_request,
)
from strategy_engine.strategies.contracts import (
    ExecutedTradeReceipt,
    LiveStrategySpec,
    OpenTradeProjectionRequest,
)


def _strategy() -> LiveStrategySpec:
    return LiveStrategySpec("ema_pullback", "instance-1", {})


def _receipt() -> ExecutedTradeReceipt:
    return ExecutedTradeReceipt(
        side="long",
        source_plan_bar_open_time_ms=300_000,
        entry_bar_open_time_ms=600_000,
        planned_entry_price="100",
        executed_entry_price="100.1",
        initial_stop_price="99",
        initial_take_price="102",
        locked_exit_profile="aligned",
    )


def _request(receipt: ExecutedTradeReceipt | None = None) -> OpenTradeProjectionRequest:
    strategy = _strategy()
    return OpenTradeProjectionRequest(
        strategy=strategy,
        market=MarketStream("BTCUSDT.P", "5m"),
        target_bar_open_time_ms=900_000,
        executed_trade_receipt=receipt or _receipt(),
    )


def test_receipt_is_immutable() -> None:
    receipt = _receipt()
    with pytest.raises(FrozenInstanceError):
        receipt.side = "short"  # type: ignore[misc]


def test_valid_receipt_passes_intrinsic_validation() -> None:
    validate_open_trade_request(_request())


@pytest.mark.parametrize(
    "receipt",
    [
        replace(_receipt(), side="flat"),
        replace(_receipt(), locked_exit_profile="unknown"),
        replace(_receipt(), entry_bar_open_time_ms=600_001),
        replace(_receipt(), source_plan_bar_open_time_ms=1_200_000),
        replace(_receipt(), planned_entry_price="0"),
        replace(_receipt(), initial_stop_price="101"),
    ],
)
def test_intrinsic_receipt_validation(receipt: ExecutedTradeReceipt) -> None:
    with pytest.raises(InvalidRequestError):
        validate_open_trade_request(_request(receipt))


@pytest.mark.parametrize("raw", ["010.0", "1.2300", "-0", "+10", "1E+1"])
def test_receipt_prices_require_normalized_decimal_text(raw: str) -> None:
    receipt = replace(_receipt(), planned_entry_price=raw)
    with pytest.raises(InvalidRequestError, match="decimal text must be normalized"):
        validate_open_trade_request(_request(receipt))
