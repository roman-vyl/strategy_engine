"""Build the sparse decision-event contract from dense per-bar decision
series -- `compact-strategy-evaluation-boundary-v1`.

Emits one `StrategyDecisionEvent` per bar carrying at least one of
entry/signal_exit/stop_ready; bars with none of these produce no event.
Mutual exclusivity of `entries[long]`/`entries[short]` is proven today by
`direction`'s strict-inequality construction (not by the trigger layer
itself), so it is asserted here rather than assumed -- a future
`direction` component that violates it fails loudly instead of silently
picking a side.
"""

from __future__ import annotations

from strategy_engine.domain.errors import EvaluationInvariantError
from strategy_engine.strategies.contracts import (
    DecisionEntry,
    DecisionSignalExit,
    DecisionStopReady,
    StrategyDecisionEvent,
)


def build_decision_events(
    *,
    entries_long: tuple[bool, ...],
    entries_short: tuple[bool, ...],
    stop_loss_ratio_long: tuple[float | None, ...],
    stop_loss_ratio_short: tuple[float | None, ...],
    take_profit_ratio_long: tuple[float | None, ...],
    take_profit_ratio_short: tuple[float | None, ...],
    signal_exit_long: tuple[bool, ...],
    signal_exit_short: tuple[bool, ...],
    stop_ready_long: tuple[bool, ...],
    stop_ready_short: tuple[bool, ...],
) -> tuple[StrategyDecisionEvent, ...]:
    bar_count = len(entries_long)
    events: list[StrategyDecisionEvent] = []
    for i in range(bar_count):
        long_entry = entries_long[i]
        short_entry = entries_short[i]
        if long_entry and short_entry:
            raise EvaluationInvariantError(
                "entries[long] and entries[short] were both true on the same bar",
                bar_index=i,
            )

        entry: DecisionEntry | None = None
        if long_entry:
            entry = DecisionEntry(
                side="long",
                stop_loss_ratio=stop_loss_ratio_long[i],
                take_profit_ratio=take_profit_ratio_long[i],
            )
        elif short_entry:
            entry = DecisionEntry(
                side="short",
                stop_loss_ratio=stop_loss_ratio_short[i],
                take_profit_ratio=take_profit_ratio_short[i],
            )

        signal_exit: DecisionSignalExit | None = None
        if signal_exit_long[i] or signal_exit_short[i]:
            signal_exit = DecisionSignalExit(long=signal_exit_long[i], short=signal_exit_short[i])

        stop_ready: DecisionStopReady | None = None
        if stop_ready_long[i] or stop_ready_short[i]:
            stop_ready = DecisionStopReady(long=stop_ready_long[i], short=stop_ready_short[i])

        if entry is not None or signal_exit is not None or stop_ready is not None:
            events.append(
                StrategyDecisionEvent(
                    bar_index=i,
                    entry=entry,
                    signal_exit=signal_exit,
                    stop_ready=stop_ready,
                )
            )
    return tuple(events)
