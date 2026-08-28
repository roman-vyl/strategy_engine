from __future__ import annotations

import pytest

from strategy_engine.domain.errors import EvaluationInvariantError
from strategy_engine.strategies.decision_events import build_decision_events


def _series(*, bar_count: int = 4, **overrides: object) -> dict[str, tuple]:
    base = {
        "entries_long": tuple(False for _ in range(bar_count)),
        "entries_short": tuple(False for _ in range(bar_count)),
        "stop_loss_ratio_long": tuple(None for _ in range(bar_count)),
        "stop_loss_ratio_short": tuple(None for _ in range(bar_count)),
        "take_profit_ratio_long": tuple(None for _ in range(bar_count)),
        "take_profit_ratio_short": tuple(None for _ in range(bar_count)),
        "signal_exit_long": tuple(False for _ in range(bar_count)),
        "signal_exit_short": tuple(False for _ in range(bar_count)),
        "stop_ready_long": tuple(False for _ in range(bar_count)),
        "stop_ready_short": tuple(False for _ in range(bar_count)),
    }
    base.update(overrides)
    return base


def test_bar_with_no_decision_emits_no_event() -> None:
    events = build_decision_events(**_series(bar_count=3))
    assert events == ()


def test_long_entry_carries_its_own_ratios_only() -> None:
    entries_long = (False, True, False)
    stop_loss_ratio_long = (None, 0.01, None)
    take_profit_ratio_long = (None, 0.02, None)
    events = build_decision_events(
        **_series(
            bar_count=3,
            entries_long=entries_long,
            stop_loss_ratio_long=stop_loss_ratio_long,
            take_profit_ratio_long=take_profit_ratio_long,
        )
    )
    assert len(events) == 1
    event = events[0]
    assert event.bar_index == 1
    assert event.entry is not None
    assert event.entry.side == "long"
    assert event.entry.stop_loss_ratio == 0.01
    assert event.entry.take_profit_ratio == 0.02
    assert event.signal_exit is None
    assert event.stop_ready is None


def test_short_entry_carries_its_own_ratios_only() -> None:
    events = build_decision_events(
        **_series(
            bar_count=2,
            entries_short=(True, False),
            stop_loss_ratio_short=(0.03, None),
            take_profit_ratio_short=(0.04, None),
        )
    )
    assert len(events) == 1
    assert events[0].entry.side == "short"
    assert events[0].entry.stop_loss_ratio == 0.03
    assert events[0].entry.take_profit_ratio == 0.04


def test_signal_exit_true_on_either_side_emits_event_without_entry() -> None:
    events = build_decision_events(
        **_series(bar_count=2, signal_exit_long=(False, True))
    )
    assert len(events) == 1
    assert events[0].bar_index == 1
    assert events[0].entry is None
    assert events[0].signal_exit.long is True
    assert events[0].signal_exit.short is False
    assert events[0].stop_ready is None


def test_stop_ready_true_on_either_side_emits_event_without_entry() -> None:
    events = build_decision_events(
        **_series(bar_count=2, stop_ready_short=(True, False))
    )
    assert len(events) == 1
    assert events[0].bar_index == 0
    assert events[0].entry is None
    assert events[0].signal_exit is None
    assert events[0].stop_ready.long is False
    assert events[0].stop_ready.short is True


def test_multiple_decision_kinds_on_one_bar_combine_into_one_event() -> None:
    events = build_decision_events(
        **_series(
            bar_count=1,
            entries_long=(True,),
            stop_loss_ratio_long=(0.01,),
            take_profit_ratio_long=(0.02,),
            signal_exit_short=(True,),
            stop_ready_long=(True,),
        )
    )
    assert len(events) == 1
    event = events[0]
    assert event.entry.side == "long"
    assert event.signal_exit.short is True
    assert event.stop_ready.long is True


def test_simultaneous_long_and_short_entry_fails_loudly() -> None:
    with pytest.raises(EvaluationInvariantError):
        build_decision_events(
            **_series(bar_count=1, entries_long=(True,), entries_short=(True,))
        )


def test_response_size_proportional_to_decisions_not_bar_count() -> None:
    bar_count = 10_000
    entries_long = tuple(i == 5000 for i in range(bar_count))
    events = build_decision_events(**_series(bar_count=bar_count, entries_long=entries_long))
    assert len(events) == 1
    assert events[0].bar_index == 5000
