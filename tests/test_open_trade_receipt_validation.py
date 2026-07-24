from dataclasses import FrozenInstanceError, replace

import pytest

from strategy_engine.domain.errors import InvalidRequestError, TradeContractMismatchError
from strategy_engine.domain.market import MarketStream
from strategy_engine.strategies.application.validate_open_trade_request import (
    validate_open_trade_request,
)
from strategy_engine.strategies.contracts import (
    ExecutedTradeReceipt,
    OpenTradeProjectionRequest,
    StrategySpecEnvelope,
)


def _strategy() -> StrategySpecEnvelope:
    return StrategySpecEnvelope("ema_pullback", "1", "instance-1", {})


def _receipt(strategy: StrategySpecEnvelope) -> ExecutedTradeReceipt:
    return ExecutedTradeReceipt(
        trade_id="trade-1",
        instance_id=strategy.instance_id,
        strategy_id=strategy.strategy_id,
        strategy_version=strategy.strategy_version,
        ticker="BTCUSDT.P",
        base_timeframe="5m",
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
        executed_trade_receipt=receipt or _receipt(strategy),
    )


def test_receipt_is_immutable() -> None:
    receipt = _receipt(_strategy())
    with pytest.raises(FrozenInstanceError):
        receipt.trade_id = "changed"  # type: ignore[misc]


def test_valid_receipt_binds_to_request() -> None:
    validate_open_trade_request(_request())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("strategy_id", "other"),
        ("strategy_version", "2"),
        ("instance_id", "other"),
        ("ticker", "ETHUSDT.P"),
        ("base_timeframe", "1m"),
    ],
)
def test_binding_mismatch_is_typed(field: str, value: str) -> None:
    receipt = replace(_receipt(_strategy()), **{field: value})
    with pytest.raises(TradeContractMismatchError) as exc_info:
        validate_open_trade_request(_request(receipt))
    assert exc_info.value.code == "trade_contract_mismatch"
    assert exc_info.value.status_code == 409


@pytest.mark.parametrize(
    "receipt",
    [
        replace(_receipt(_strategy()), trade_id=""),
        replace(_receipt(_strategy()), side="flat"),
        replace(_receipt(_strategy()), locked_exit_profile="unknown"),
        replace(_receipt(_strategy()), entry_bar_open_time_ms=600_001),
        replace(_receipt(_strategy()), source_plan_bar_open_time_ms=1_200_000),
        replace(_receipt(_strategy()), planned_entry_price="0"),
        replace(_receipt(_strategy()), initial_stop_price="101"),
    ],
)
def test_intrinsic_receipt_validation(receipt: ExecutedTradeReceipt) -> None:
    with pytest.raises(InvalidRequestError):
        validate_open_trade_request(_request(receipt))


def test_validation_has_no_market_data_dependency() -> None:
    request = _request(replace(_receipt(_strategy()), instance_id="wrong"))
    with pytest.raises(TradeContractMismatchError):
        validate_open_trade_request(request)


@pytest.mark.parametrize("raw", ["010.0", "1.2300", "-0", "+10", "1E+1"])
def test_receipt_prices_require_normalized_decimal_text(raw: str) -> None:
    receipt = replace(_receipt(_strategy()), planned_entry_price=raw)
    with pytest.raises(InvalidRequestError, match="decimal text must be normalized"):
        validate_open_trade_request(_request(receipt))
