from __future__ import annotations

from types import SimpleNamespace

from strategy_engine.strategies.ema_pullback.live_projections.open_trade import (
    _compose_close_signal,
    _standard_signal_candidates,
)


def _spec() -> dict[str, object]:
    return {
        "trade_management": {
            "exit_policy": {
                "always_on": {
                    "exits": [
                        {
                            "instance_id": "always-rsi",
                            "component_id": "rsi_signal_exit",
                            "exit_kind": "signal",
                        }
                    ]
                },
                "profiles": {
                    "aligned": {
                        "exits": [
                            {
                                "instance_id": "aligned-ema",
                                "component_id": "ema_close_loss_exit",
                                "exit_kind": "signal",
                            }
                        ]
                    },
                    "countertrend": {"exits": []},
                    "neutral": {"exits": []},
                },
            }
        }
    }


def _evaluation(*, always: tuple[bool, ...], aligned: tuple[bool, ...]):
    evidence = (
        SimpleNamespace(
            instance_id="always-rsi",
            component_id="rsi_signal_exit",
            exit_kind="signal",
            side="long",
            signal=always,
        ),
        SimpleNamespace(
            instance_id="aligned-ema",
            component_id="ema_close_loss_exit",
            exit_kind="signal",
            side="long",
            signal=aligned,
        ),
    )
    return SimpleNamespace(
        exit_policy=SimpleNamespace(
            signal_by_profile_long={
                "aligned": tuple(a or b for a, b in zip(always, aligned, strict=True)),
                "countertrend": always,
                "neutral": always,
            },
            signal_by_profile_short={
                "aligned": (False,) * len(always),
                "countertrend": (False,) * len(always),
                "neutral": (False,) * len(always),
            },
            rule_evidence=evidence,
        )
    )


def test_locked_profile_selects_target_signal_not_current_profile() -> None:
    candidates = _standard_signal_candidates(
        _evaluation(always=(False, False), aligned=(False, True)),
        _spec(),
        side="long",
        locked_profile="aligned",
        target_index=1,
    )
    assert candidates == (("aligned-ema", "ema_close_loss_exit"),)


def test_intermediate_transient_signal_is_not_recovered() -> None:
    candidates = _standard_signal_candidates(
        _evaluation(always=(True, False), aligned=(False, False)),
        _spec(),
        side="long",
        locked_profile="aligned",
        target_index=1,
    )
    assert candidates == ()


def test_runtime_close_precedes_standard_signal_using_existing_strategy_order() -> None:
    signal = _compose_close_signal(
        runtime_candidates=(("z-runtime", "phase_runtime_exit"),),
        standard_candidates=(("a-signal", "rsi_signal_exit"),),
    )
    assert signal.active is True
    assert signal.reason == "runtime_exit:z-runtime"
    assert signal.component_id == "phase_runtime_exit"
    assert signal.layer == "managed"


def test_same_layer_attribution_is_stable_by_rule_identity() -> None:
    signal = _compose_close_signal(
        runtime_candidates=(),
        standard_candidates=(
            ("z-signal", "rsi_signal_exit"),
            ("a-signal", "ema_close_loss_exit"),
        ),
    )
    assert signal.reason == "signal:a-signal"
    assert signal.component_id == "ema_close_loss_exit"
    assert signal.layer == "exit_policy"


def test_no_target_active_close_rule_returns_inactive_signal() -> None:
    signal = _compose_close_signal(runtime_candidates=(), standard_candidates=())
    assert signal.active is False
    assert signal.reason is None
    assert signal.component_id is None
    assert signal.layer is None


def test_application_result_is_desired_state_without_execution_fields(monkeypatch) -> None:
    from dataclasses import fields
    from decimal import Decimal

    from strategy_engine.domain.market import MarketBar, MarketStream
    from strategy_engine.domain.ranges import TimeRange
    from strategy_engine.indicators.contracts import FeatureFrame
    from strategy_engine.strategies.application import (
        evaluate_open_trade_projection as module,
    )
    from strategy_engine.strategies.contracts import (
        ExecutedTradeReceipt,
        OpenTradeProjectionRequest,
        OpenTradeProjectionResult,
        StrategySpecEnvelope,
    )
    from strategy_engine.strategies.ema_pullback.live_projections import (
        open_trade as adapter_module,
    )
    from strategy_engine.strategies.ema_pullback.managed import (
        ManagedCalculationResult,
        ManagedTradeState,
        StartAfterEntryManagedProjection,
    )

    strategy = StrategySpecEnvelope("ema_pullback", "1", "instance-1", _spec())
    receipt = ExecutedTradeReceipt(
        instance_id="instance-1",
        strategy_id="ema_pullback",
        ticker="BTCUSDT.P",
        base_timeframe="5m",
        side="long",
        source_plan_bar_open_time_ms=0,
        entry_bar_open_time_ms=300_000,
        planned_entry_price="100",
        executed_entry_price="100.5",
        initial_stop_price="95",
        initial_take_price="120",
        locked_exit_profile="aligned",
    )
    market = MarketStream("BTCUSDT.P", "5m")
    frame = FeatureFrame(
        market,
        TimeRange(0, 900_000),
        (0, 300_000, 600_000),
        {},
        {},
        "plan-hash",
        "market-hash",
        (
            MarketBar(
                0,
                Decimal("100"),
                Decimal("101"),
                Decimal("99"),
                Decimal("100"),
                Decimal("1"),
            ),
            MarketBar(
                300_000,
                Decimal("100"),
                Decimal("102"),
                Decimal("98"),
                Decimal("101"),
                Decimal("1"),
            ),
            MarketBar(
                600_000,
                Decimal("101"),
                Decimal("105"),
                Decimal("100"),
                Decimal("104"),
                Decimal("1"),
            ),
        ),
    )
    loader = SimpleNamespace(
        execute=lambda _request: SimpleNamespace(
            frame=frame,
            planned_features=object(),
            target_index=2,
            market_data_hash="market-hash",
        )
    )
    evaluation = _evaluation(always=(False, False, False), aligned=(False, False, True))
    state = ManagedTradeState.initial(
        side="long",
        entry_index=1,
        entry_time_ms=300_000,
        entry_price=100.0,
    )
    state.phase = "protected"
    state.max_phase_reached = "protected"
    state.bars_in_trade = 2
    state.mfe_pct = 0.05
    state.mae_pct = 0.01
    managed = StartAfterEntryManagedProjection(
        replay=ManagedCalculationResult("long", 300_000, (), (), state),
        desired_stop_price=100.0,
        desired_take_price=None,
    )
    monkeypatch.setattr(adapter_module, "evaluate_ema_pullback_frame", lambda *_args: evaluation)
    monkeypatch.setattr(
        adapter_module,
        "evaluate_start_after_entry_managed_projection",
        lambda *_args, **_kwargs: managed,
    )

    result = module.EvaluateOpenTradeProjection(loader).execute(
        OpenTradeProjectionRequest(strategy, market, 600_000, receipt)
    )

    assert result.desired_protection.stop_price == "100"
    assert result.desired_protection.take_price is None
    assert result.close_signal.reason == "signal:aligned-ema"
    assert result.diagnostics.phase == "protected"
    assert {item.name for item in fields(OpenTradeProjectionResult)}.isdisjoint(
        {"fill_price", "exit_price", "exit_time", "pnl", "quantity", "order_ids", "commands"}
    )
