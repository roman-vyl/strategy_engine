"""Tests for Step 16 exit_reason attribution."""

from __future__ import annotations

import pytest

import pandas as pd

from research.strategies.ema_pullback.execution.exit_attribution import (
    ExitAttributionContext,
    classify_exit_attribution,
    classify_exit_reason,
)
from research.strategies.ema_pullback.execution.results import (
    _can_use_exit_attribution,
    extract_trade_records,
)


def _ctx_one_sl(*, idx: pd.DatetimeIndex, sl: float, inst: str = "atr_sl") -> ExitAttributionContext:
    ratio = pd.Series(sl, index=idx, dtype=float)
    nan_s = pd.Series(float("nan"), index=idx, dtype=float)
    return ExitAttributionContext(
        index=idx,
        instance_ids=(inst,),
        exit_kinds=("stop_loss",),
        long_signal_by_rule=(None,),
        short_signal_by_rule=(None,),
        distance_ratio_by_rule=(ratio,),
        sl_stop_agg=ratio,
        tp_stop_agg=nan_s,
    )


def test_classify_open_trade() -> None:
    idx = pd.date_range("2024-01-01", periods=3, freq="h", tz="UTC")
    ctx = _ctx_one_sl(idx=idx, sl=0.02)
    row = {"status": 0, "direction": 0, "entry_idx": 0, "exit_idx": 0}
    close = pd.Series([100.0, 101.0, 102.0], index=idx)
    o = h = l = close
    assert classify_exit_reason(row=row, close=close, high=h, low=l, open_=o, ctx=ctx) == "open"


def test_classify_exit_attribution_stop_metadata() -> None:
    idx = pd.date_range("2024-01-01", periods=5, freq="h", tz="UTC")
    sl = 0.02
    ctx = _ctx_one_sl(idx=idx, sl=sl, inst="atr_stop_1")
    close = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0], index=idx)
    high = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0], index=idx)
    low = pd.Series([100.0, 100.0, 100.0, 97.0, 100.0], index=idx)
    open_ = pd.Series([100.0, 100.0, 100.0, 99.0, 100.0], index=idx)
    row = {"status": 1, "direction": 0, "entry_idx": 1, "exit_idx": 3}
    attr = classify_exit_attribution(
        row=row,
        close=close,
        high=high,
        low=low,
        open_=open_,
        ctx=ctx,
        component_map={"atr_stop_1": "atr_stop_loss"},
    )
    assert attr.exit_reason == "stop_loss:atr_stop_1"
    assert attr.exit_kind == "stop_loss"
    assert attr.exit_instance_id == "atr_stop_1"
    assert attr.exit_component_id == "atr_stop_loss"
    assert attr.exit_group == "always_on"
    assert attr.exit_profile is None


def test_classify_exit_attribution_signal_metadata() -> None:
    idx = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    nan_s = pd.Series(float("nan"), index=idx, dtype=float)
    sig = pd.Series([False, False, True, False], index=idx, dtype=bool)
    context = pd.Series(["neutral", "up", "up", "neutral"], index=idx, dtype=object)
    ctx = ExitAttributionContext(
        index=idx,
        instance_ids=("rsi_exit_1",),
        exit_kinds=("signal",),
        long_signal_by_rule=(sig,),
        short_signal_by_rule=(pd.Series(False, index=idx),),
        distance_ratio_by_rule=(None,),
        rule_groups=("aligned",),
        context_state=context,
        sl_stop_agg=nan_s,
        tp_stop_agg=nan_s,
    )
    close = pd.Series([100.0, 100.0, 100.0, 100.0], index=idx)
    high = low = open_ = close
    row = {"status": 1, "direction": 0, "entry_idx": 1, "exit_idx": 2}
    attr = classify_exit_attribution(
        row=row,
        close=close,
        high=high,
        low=low,
        open_=open_,
        ctx=ctx,
        component_map={"rsi_exit_1": "rsi_signal_exit"},
    )
    assert attr.exit_reason == "signal:rsi_exit_1"
    assert attr.exit_kind == "signal"
    assert attr.exit_group == "profile"
    assert attr.exit_profile == "aligned"
    assert attr.exit_instance_id == "rsi_exit_1"
    assert attr.exit_component_id == "rsi_signal_exit"


def test_classify_exit_attribution_unknown_null_metadata() -> None:
    idx = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    nan_s = pd.Series(float("nan"), index=idx, dtype=float)
    ctx = ExitAttributionContext(
        index=idx,
        instance_ids=("x",),
        exit_kinds=("signal",),
        long_signal_by_rule=(pd.Series(False, index=idx),),
        short_signal_by_rule=(None,),
        distance_ratio_by_rule=(None,),
        sl_stop_agg=nan_s,
        tp_stop_agg=nan_s,
    )
    close = pd.Series([100.0, 100.0, 100.0, 100.0], index=idx)
    high = low = open_ = close
    row = {"status": 1, "direction": 0, "entry_idx": 1, "exit_idx": 2}
    attr = classify_exit_attribution(row=row, close=close, high=high, low=low, open_=open_, ctx=ctx)
    assert attr.exit_reason == "unknown"
    assert attr.exit_group is None
    assert attr.exit_profile is None
    assert attr.exit_component_id is None
    assert attr.exit_instance_id is None
    assert attr.exit_kind is None


def test_classify_long_stop_loss_hit() -> None:
    idx = pd.date_range("2024-01-01", periods=5, freq="h", tz="UTC")
    sl = 0.02
    ctx = _ctx_one_sl(idx=idx, sl=sl, inst="atr_stop_1")
    close = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0], index=idx)
    high = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0], index=idx)
    low = pd.Series([100.0, 100.0, 100.0, 97.0, 100.0], index=idx)
    open_ = pd.Series([100.0, 100.0, 100.0, 99.0, 100.0], index=idx)
    row = {"status": 1, "direction": 0, "entry_idx": 1, "exit_idx": 3}
    assert classify_exit_reason(row=row, close=close, high=high, low=low, open_=open_, ctx=ctx) == (
        "stop_loss:atr_stop_1"
    )


def test_classify_long_take_profit_hit() -> None:
    idx = pd.date_range("2024-01-01", periods=5, freq="h", tz="UTC")
    nan_s = pd.Series(float("nan"), index=idx, dtype=float)
    tp = 0.05
    ratio = pd.Series(tp, index=idx, dtype=float)
    ctx = ExitAttributionContext(
        index=idx,
        instance_ids=("tp1",),
        exit_kinds=("take_profit",),
        long_signal_by_rule=(None,),
        short_signal_by_rule=(None,),
        distance_ratio_by_rule=(ratio,),
        sl_stop_agg=nan_s,
        tp_stop_agg=ratio,
    )
    close = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0], index=idx)
    high = pd.Series([100.0, 100.0, 100.0, 106.0, 100.0], index=idx)
    low = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0], index=idx)
    open_ = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0], index=idx)
    row = {"status": 1, "direction": 0, "entry_idx": 1, "exit_idx": 3}
    assert classify_exit_reason(row=row, close=close, high=high, low=low, open_=open_, ctx=ctx) == (
        "take_profit:tp1"
    )


def test_classify_short_take_profit_hit() -> None:
    idx = pd.date_range("2024-01-01", periods=5, freq="h", tz="UTC")
    nan_s = pd.Series(float("nan"), index=idx, dtype=float)
    tp = 0.05
    ratio = pd.Series(tp, index=idx, dtype=float)
    ctx = ExitAttributionContext(
        index=idx,
        instance_ids=("tp_short",),
        exit_kinds=("take_profit",),
        long_signal_by_rule=(None,),
        short_signal_by_rule=(None,),
        distance_ratio_by_rule=(ratio,),
        sl_stop_agg=nan_s,
        tp_stop_agg=ratio,
    )
    close = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0], index=idx)
    high = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0], index=idx)
    low = pd.Series([100.0, 100.0, 100.0, 94.0, 100.0], index=idx)
    open_ = pd.Series([100.0, 100.0, 100.0, 95.0, 100.0], index=idx)
    row = {"status": 1, "direction": 1, "entry_idx": 1, "exit_idx": 3}
    assert classify_exit_reason(row=row, close=close, high=high, low=low, open_=open_, ctx=ctx) == (
        "take_profit:tp_short"
    )


def test_classify_stop_wins_over_signal_same_bar() -> None:
    idx = pd.date_range("2024-01-01", periods=5, freq="h", tz="UTC")
    sl = 0.02
    ratio = pd.Series(sl, index=idx, dtype=float)
    nan_s = pd.Series(float("nan"), index=idx, dtype=float)
    sig = pd.Series([False, False, False, True, False], index=idx, dtype=bool)
    ctx = ExitAttributionContext(
        index=idx,
        instance_ids=("atr_sl", "rsi_x"),
        exit_kinds=("stop_loss", "signal"),
        long_signal_by_rule=(None, sig),
        short_signal_by_rule=(None, pd.Series(False, index=idx)),
        distance_ratio_by_rule=(ratio, None),
        sl_stop_agg=ratio,
        tp_stop_agg=nan_s,
    )
    close = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0], index=idx)
    high = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0], index=idx)
    low = pd.Series([100.0, 100.0, 100.0, 97.0, 100.0], index=idx)
    open_ = pd.Series([100.0, 100.0, 100.0, 99.0, 100.0], index=idx)
    row = {"status": 1, "direction": 0, "entry_idx": 1, "exit_idx": 3}
    assert classify_exit_reason(row=row, close=close, high=high, low=low, open_=open_, ctx=ctx) == (
        "stop_loss:atr_sl"
    )


def test_classify_short_stop_loss_hit() -> None:
    idx = pd.date_range("2024-01-01", periods=5, freq="h", tz="UTC")
    sl = 0.02
    ratio = pd.Series(sl, index=idx, dtype=float)
    nan_s = pd.Series(float("nan"), index=idx, dtype=float)
    ctx = ExitAttributionContext(
        index=idx,
        instance_ids=("sl_s",),
        exit_kinds=("stop_loss",),
        long_signal_by_rule=(None,),
        short_signal_by_rule=(None,),
        distance_ratio_by_rule=(ratio,),
        sl_stop_agg=ratio,
        tp_stop_agg=nan_s,
    )
    close = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0], index=idx)
    high = pd.Series([100.0, 100.0, 100.0, 104.0, 100.0], index=idx)
    low = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0], index=idx)
    open_ = pd.Series([100.0, 100.0, 100.0, 103.0, 100.0], index=idx)
    row = {"status": 1, "direction": 1, "entry_idx": 1, "exit_idx": 3}
    assert classify_exit_reason(row=row, close=close, high=high, low=low, open_=open_, ctx=ctx) == (
        "stop_loss:sl_s"
    )


def test_classify_long_signal_when_no_stop() -> None:
    idx = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    nan_s = pd.Series(float("nan"), index=idx, dtype=float)
    sig = pd.Series([False, False, True, False], index=idx, dtype=bool)
    ctx = ExitAttributionContext(
        index=idx,
        instance_ids=("rsi_exit_1",),
        exit_kinds=("signal",),
        long_signal_by_rule=(sig,),
        short_signal_by_rule=(pd.Series(False, index=idx),),
        distance_ratio_by_rule=(None,),
        sl_stop_agg=nan_s,
        tp_stop_agg=nan_s,
    )
    close = pd.Series([100.0, 100.0, 100.0, 100.0], index=idx)
    high = low = open_ = close
    row = {"status": 1, "direction": 0, "entry_idx": 1, "exit_idx": 2}
    assert classify_exit_reason(row=row, close=close, high=high, low=low, open_=open_, ctx=ctx) == (
        "signal:rsi_exit_1"
    )


def test_classify_short_signal_when_no_stop() -> None:
    idx = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    nan_s = pd.Series(float("nan"), index=idx, dtype=float)
    sig = pd.Series([False, False, True, False], index=idx, dtype=bool)
    ctx = ExitAttributionContext(
        index=idx,
        instance_ids=("rsi_short",),
        exit_kinds=("signal",),
        long_signal_by_rule=(pd.Series(False, index=idx),),
        short_signal_by_rule=(sig,),
        distance_ratio_by_rule=(None,),
        sl_stop_agg=nan_s,
        tp_stop_agg=nan_s,
    )
    close = pd.Series([100.0, 100.0, 100.0, 100.0], index=idx)
    high = low = open_ = close
    row = {"status": 1, "direction": 1, "entry_idx": 1, "exit_idx": 2}
    assert classify_exit_reason(row=row, close=close, high=high, low=low, open_=open_, ctx=ctx) == (
        "signal:rsi_short"
    )


def test_multiple_signals_same_exit_bar_first_in_spec_order() -> None:
    idx = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    nan_s = pd.Series(float("nan"), index=idx, dtype=float)
    sig_a = pd.Series([False, False, True, False], index=idx, dtype=bool)
    sig_b = pd.Series([False, False, True, False], index=idx, dtype=bool)
    ctx = ExitAttributionContext(
        index=idx,
        instance_ids=("first_signal", "second_signal"),
        exit_kinds=("signal", "signal"),
        long_signal_by_rule=(sig_a, sig_b),
        short_signal_by_rule=(pd.Series(False, index=idx), pd.Series(False, index=idx)),
        distance_ratio_by_rule=(None, None),
        sl_stop_agg=nan_s,
        tp_stop_agg=nan_s,
    )
    close = pd.Series([100.0, 100.0, 100.0, 100.0], index=idx)
    high = low = open_ = close
    row = {"status": 1, "direction": 0, "entry_idx": 1, "exit_idx": 2}
    assert classify_exit_reason(row=row, close=close, high=high, low=low, open_=open_, ctx=ctx) == (
        "signal:first_signal"
    )


def test_multiple_stop_loss_rules_picks_tighter_min_at_entry() -> None:
    idx = pd.date_range("2024-01-01", periods=5, freq="h", tz="UTC")
    entry_i = 1
    exit_i = 3
    close_val = 100.0
    close = pd.Series(close_val, index=idx, dtype=float)
    # Wide SL 3% vs tight SL 1% -> aggregate uses min distance (1%)
    wide = pd.Series([float("nan"), 3.0, float("nan"), float("nan"), float("nan")], index=idx)
    tight = pd.Series([float("nan"), 1.0, float("nan"), float("nan"), float("nan")], index=idx)
    wide_ratio = wide / close
    tight_ratio = tight / close
    agg_sl = pd.concat([wide, tight], axis=1).min(axis=1) / close
    nan_s = pd.Series(float("nan"), index=idx, dtype=float)
    ctx = ExitAttributionContext(
        index=idx,
        instance_ids=("wide_sl", "tight_sl"),
        exit_kinds=("stop_loss", "stop_loss"),
        long_signal_by_rule=(None, None),
        short_signal_by_rule=(None, None),
        distance_ratio_by_rule=(wide_ratio, tight_ratio),
        sl_stop_agg=agg_sl,
        tp_stop_agg=nan_s,
    )
    sl_level = close_val * (1.0 - 0.01)
    high = pd.Series(close_val, index=idx, dtype=float)
    low = pd.Series(close_val, index=idx, dtype=float)
    low.iloc[exit_i] = sl_level - 0.5
    open_ = pd.Series(close_val, index=idx, dtype=float)
    row = {"status": 1, "direction": 0, "entry_idx": entry_i, "exit_idx": exit_i}
    assert classify_exit_reason(row=row, close=close, high=high, low=low, open_=open_, ctx=ctx) == (
        "stop_loss:tight_sl"
    )


def test_multiple_take_profit_rules_picks_tighter_min_at_entry() -> None:
    idx = pd.date_range("2024-01-01", periods=5, freq="h", tz="UTC")
    entry_i = 1
    exit_i = 3
    close_val = 100.0
    close = pd.Series(close_val, index=idx, dtype=float)
    wide = pd.Series([float("nan"), 5.0, float("nan"), float("nan"), float("nan")], index=idx)
    tight = pd.Series([float("nan"), 1.0, float("nan"), float("nan"), float("nan")], index=idx)
    wide_ratio = wide / close
    tight_ratio = tight / close
    agg_tp = pd.concat([wide, tight], axis=1).min(axis=1) / close
    nan_s = pd.Series(float("nan"), index=idx, dtype=float)
    ctx = ExitAttributionContext(
        index=idx,
        instance_ids=("wide_tp", "tight_tp"),
        exit_kinds=("take_profit", "take_profit"),
        long_signal_by_rule=(None, None),
        short_signal_by_rule=(None, None),
        distance_ratio_by_rule=(wide_ratio, tight_ratio),
        sl_stop_agg=nan_s,
        tp_stop_agg=agg_tp,
    )
    tp_level = close_val * (1.0 + 0.01)
    high = pd.Series(close_val, index=idx, dtype=float)
    high.iloc[exit_i] = tp_level + 0.5
    low = pd.Series(close_val, index=idx, dtype=float)
    open_ = pd.Series(close_val, index=idx, dtype=float)
    row = {"status": 1, "direction": 0, "entry_idx": entry_i, "exit_idx": exit_i}
    assert classify_exit_reason(row=row, close=close, high=high, low=low, open_=open_, ctx=ctx) == (
        "take_profit:tight_tp"
    )


def test_can_use_attribution_false_on_index_mismatch() -> None:
    idx = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    close = pd.Series([1.0, 2.0, 3.0, 4.0], index=idx)
    shifted = pd.Series([1.0, 2.0, 3.0, 4.0], index=idx[::-1])
    ctx = _ctx_one_sl(idx=idx, sl=0.02)
    assert not _can_use_exit_attribution(close, high=shifted, low=close, open_s=close, attribution=ctx)
    assert not _can_use_exit_attribution(close, high=close, low=close, open_s=close, attribution=None)


@pytest.mark.optional_vectorbt
def test_extract_trade_records_unknown_without_attribution() -> None:
    vbt = pytest.importorskip("vectorbt")
    idx = pd.date_range("2024-01-01", periods=5, freq="h", tz="UTC")
    close = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0], index=idx)
    entries = pd.Series([False, True, False, False, False], index=idx)
    exits = pd.Series([False, False, False, True, False], index=idx)
    pf = vbt.Portfolio.from_signals(close, entries, exits, freq="1h")
    rec = extract_trade_records(pf, close)
    assert rec[0]["exit_reason"] == "unknown"


@pytest.mark.optional_vectorbt
def test_extract_trade_records_unknown_on_ohlc_index_mismatch() -> None:
    vbt = pytest.importorskip("vectorbt")
    idx = pd.date_range("2024-01-01", periods=5, freq="h", tz="UTC")
    close = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0], index=idx)
    entries = pd.Series([False, True, False, False, False], index=idx)
    exits = pd.Series([False, False, False, True, False], index=idx)
    pf = vbt.Portfolio.from_signals(close, entries, exits, freq="1h")
    ctx = _ctx_one_sl(idx=idx, sl=0.02)
    high = pd.Series(close.values, index=idx[::-1])
    rec = extract_trade_records(pf, close, high=high, low=close, open_s=close, attribution=ctx)
    assert rec[0]["exit_reason"] == "unknown"
