"""EMA stack episode history (OpenSpec `ema-stack-episode-query-v1`).

A read-only second consumer of the episode projection of
`ema-stack-episode-v1`: the same parameter parser, the same EMA
implementation and the same per-side projector, asked for a market and a
parameter set instead of a strategy. The whole committed history is
computed once per market data version and served in pages of whole
finished episodes, together with the current (unbroken) episode.
"""

from __future__ import annotations

import bisect
import dataclasses
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from strategy_engine.domain.errors import (
    InvalidRequestError,
    MarketDataVersionChangedError,
    MarketStreamNotReadyError,
)
from strategy_engine.domain.market import MarketStream
from strategy_engine.domain.ranges import TimeRange, timeframe_duration_ms
from strategy_engine.domain.values import canonical_json_hash
from strategy_engine.indicators.application.evaluate_range import EvaluateIndicatorRange
from strategy_engine.indicators.contracts import IndicatorRangeRequest
from strategy_engine.ports.market_data import MarketDataPort
from strategy_engine.strategies.ema_pullback.feature_plan import episode_indicator_plan
from strategy_engine.strategies.ema_pullback.stack_episode import (
    EPISODE_NODE_VERSION,
    EpisodeParams,
    SideEpisode,
    compute_side_episode,
    side_entities_to_wire,
)

SIDES = ("long", "short")
QUERY_PARAM_KEYS = frozenset(
    {"fast_period", "anchor_period", "slow_period", "window_bars", "break_bars"}
)
MAX_PAGE_LIMIT = 500


@dataclass(frozen=True, slots=True)
class EpisodeHistoryRequest:
    market: MarketStream
    params: EpisodeParams
    side: str
    before_start_ms: int | None = None
    limit: int = 50
    expected_market_data_hash: str | None = None

    def __post_init__(self) -> None:
        if self.side not in SIDES:
            raise InvalidRequestError("side must be long or short", side=self.side)
        if isinstance(self.limit, bool) or not 1 <= self.limit <= MAX_PAGE_LIMIT:
            raise InvalidRequestError(
                f"page.limit must be between 1 and {MAX_PAGE_LIMIT}", limit=self.limit
            )


@dataclass(frozen=True, slots=True)
class _SideHistory:
    """Finished episodes, oldest first, and the current episode."""

    finished: tuple[dict[str, Any], ...]
    starts: tuple[int, ...]
    current: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class _HistoryEntry:
    """One computed history: both sides of one market and parameter set.
    Its version is the market data it was computed from (bounds and the
    market data hash of the loaded range), not the last candle alone."""

    earliest_ms: int
    latest_ms: int
    market_data_hash: str
    sides: dict[str, _SideHistory]
    loaded_at: float


class _Slot:
    __slots__ = ("entry", "lock")

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.entry: _HistoryEntry | None = None


class EpisodeHistoryCache:
    """Bounded in-memory LRU of computed histories. A memo only: nothing is
    persisted, and losing it costs a recompute."""

    def __init__(self, max_entries: int) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._slots: OrderedDict[tuple[str, str, str], _Slot] = OrderedDict()

    def slot(self, key: tuple[str, str, str]) -> _Slot:
        with self._lock:
            slot = self._slots.get(key)
            if slot is None:
                slot = _Slot()
                self._slots[key] = slot
            self._slots.move_to_end(key)
            while len(self._slots) > self._max_entries:
                self._slots.popitem(last=False)
            return slot

    def __len__(self) -> int:
        with self._lock:
            return len(self._slots)


def _params_wire(params: EpisodeParams) -> dict[str, int]:
    return {
        "fast_period": params.fast_period,
        "anchor_period": params.anchor_period,
        "slow_period": params.slow_period,
        "window_bars": params.window_bars,
        "break_bars": params.break_bars,
    }


def params_hash(params: EpisodeParams) -> str:
    return canonical_json_hash(
        {
            "node": "episode.ema_stack",
            "version": EPISODE_NODE_VERSION,
            "params": _params_wire(params),
        }
    )


def history_id(market: MarketStream, params: EpisodeParams) -> str:
    return canonical_json_hash(
        {
            "ticker": market.ticker,
            "base_timeframe": market.base_timeframe,
            "params": _params_wire(params),
        }
    )


def _times(value: Any) -> Any:
    """Entity wire with bar indices dropped: a point `{bar, time_ms}` becomes
    its `time_ms`, and `episode_id` is left out."""

    if isinstance(value, dict):
        if value.keys() == {"bar", "time_ms"}:
            return value["time_ms"]
        return {key: _times(item) for key, item in value.items() if key != "episode_id"}
    if isinstance(value, list):
        return [_times(item) for item in value]
    return value


def _shape_side(episode: SideEpisode, time_ms: tuple[int, ...]) -> _SideHistory:
    tables = side_entities_to_wire(episode, time_ms)
    grouped: dict[str, dict[int, list[Any]]] = {"zones": {}, "false_breaks": {}, "waves": {}}
    for name, by_episode in grouped.items():
        for row in tables[name]:  # type: ignore[attr-defined]
            by_episode.setdefault(row["episode_id"], []).append(_times(row))
    finished: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for row in tables["episodes"]:  # type: ignore[attr-defined]
        episode_id = row["episode_id"]
        zones = grouped["zones"].get(episode_id, [])
        false_breaks = grouped["false_breaks"].get(episode_id, [])
        record: dict[str, Any] = {
            "start_ms": row["start"]["time_ms"],
            "stack_break_ms": row["stack_break"]["time_ms"],
            "censored": row["censored"],
            "touches": len(zones),
            "false_breaks_count": len(false_breaks),
            "zones": zones,
            "false_breaks": false_breaks,
            "waves": grouped["waves"].get(episode_id, []),
        }
        if row["stack_break"]["bar"] is None:
            record["touch_number"], record["phase"] = _current_state(episode, row["censored"])
            current = record
        else:
            finished.append(record)
    starts = tuple(record["start_ms"] for record in finished)
    return _SideHistory(finished=tuple(finished), starts=starts, current=current)


def _current_state(episode: SideEpisode, censored: bool) -> tuple[int | None, str | None]:
    if censored:
        return None, None
    state = episode.state
    if state["in_zone"][-1] == 1.0:
        phase = "in_zone"
    elif state["in_false_break"][-1] == 1.0:
        phase = "in_false_break"
    else:
        phase = "away"
    return int(state["touch_number"][-1]), phase


class QueryEpisodeHistory:
    def __init__(
        self,
        market_data: MarketDataPort,
        indicators: EvaluateIndicatorRange,
        *,
        revalidate_seconds: float = 300.0,
        max_entries: int = 16,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._market_data = market_data
        self._indicators = indicators
        self._revalidate_seconds = revalidate_seconds
        self._cache = EpisodeHistoryCache(max_entries)
        self._clock = clock

    def execute(self, request: EpisodeHistoryRequest) -> dict[str, object]:
        market, params = request.market, request.params
        bounds = self._market_data.load_bounds(market)
        earliest = bounds.earliest_committed_open_time_ms
        latest = bounds.latest_committed_open_time_ms
        if bounds.state != "ready" or earliest is None or latest is None:
            raise MarketStreamNotReadyError(
                state=bounds.state,
                earliest_committed_open_time_ms=earliest,
                latest_committed_open_time_ms=latest,
            )
        key = (market.ticker, market.base_timeframe, params_hash(params))
        slot = self._cache.slot(key)
        with slot.lock:
            entry = slot.entry
            loaded_now = False
            if entry is None or not self._valid(entry, earliest, latest):
                entry = self._refresh(slot, request, earliest, latest)
                loaded_now = True
            pinned = request.expected_market_data_hash
            if pinned is not None and pinned != entry.market_data_hash:
                if not loaded_now:
                    entry = self._refresh(slot, request, earliest, latest)
                if pinned != entry.market_data_hash:
                    raise MarketDataVersionChangedError(
                        expected_market_data_hash=pinned,
                        actual_market_data_hash=entry.market_data_hash,
                    )
        return self._page(request, entry)

    def _valid(self, entry: _HistoryEntry, earliest: int, latest: int) -> bool:
        return (
            entry.earliest_ms == earliest
            and entry.latest_ms == latest
            and self._clock() - entry.loaded_at <= self._revalidate_seconds
        )

    def _refresh(
        self, slot: _Slot, request: EpisodeHistoryRequest, earliest: int, latest: int
    ) -> _HistoryEntry:
        """Reload the candle range. An unchanged `market_data_hash` keeps the
        computed history (revalidation); a different one recomputes it."""

        market = request.market
        step_ms = timeframe_duration_ms(market.base_timeframe)
        time_range = TimeRange(earliest, latest + step_ms)
        frame = self._market_data.load_range(market, time_range)
        previous = slot.entry
        if (
            previous is not None
            and previous.earliest_ms == earliest
            and previous.latest_ms == latest
            and previous.market_data_hash == frame.market_data_hash
        ):
            entry = dataclasses.replace(previous, loaded_at=self._clock())
        else:
            plan, columns = episode_indicator_plan(request.params)
            native = self._indicators.execute_native(
                IndicatorRangeRequest(
                    market=market, time_range=time_range, plan=plan, market_frame=frame
                )
            )
            sides = {
                side: _shape_side(
                    compute_side_episode(native, columns, request.params, side),
                    native.time_ms,
                )
                for side in SIDES
            }
            entry = _HistoryEntry(
                earliest_ms=earliest,
                latest_ms=latest,
                market_data_hash=frame.market_data_hash,
                sides=sides,
                loaded_at=self._clock(),
            )
        slot.entry = entry
        return entry

    def _page(self, request: EpisodeHistoryRequest, entry: _HistoryEntry) -> dict[str, object]:
        history = entry.sides[request.side]
        market, params = request.market, request.params
        upper = (
            len(history.starts)
            if request.before_start_ms is None
            else bisect.bisect_left(history.starts, request.before_start_ms)
        )
        lower = max(0, upper - request.limit)
        episodes = list(reversed(history.finished[lower:upper]))
        return {
            "history_id": history_id(market, params),
            "market": {
                "ticker": market.ticker,
                "base_timeframe": market.base_timeframe,
                "earliest_ms": entry.earliest_ms,
                "as_of_ms": entry.latest_ms,
            },
            "episode": _params_wire(params),
            "params_hash": params_hash(params),
            "market_data_hash": entry.market_data_hash,
            "side": request.side,
            "current": history.current,
            "episodes": episodes,
            "next_before_start_ms": history.starts[lower] if lower > 0 else None,
        }


__all__ = [
    "MAX_PAGE_LIMIT",
    "QUERY_PARAM_KEYS",
    "SIDES",
    "EpisodeHistoryCache",
    "EpisodeHistoryRequest",
    "QueryEpisodeHistory",
    "history_id",
    "params_hash",
]
