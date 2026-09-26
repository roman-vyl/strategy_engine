"""Shared range-invariant float64 view of one market range.

OpenSpec `batch-computation-reuse`, group 2 (design.md D4, "Class-A
conversion"): the Decimal -> float64 conversion of a range's OHLCV bars,
its `DatetimeIndex` and its `time_ms` grid are pure functions of the
market bars alone. `MarketArrays` is the one representation of that
conversion. It is built once per evaluation request -- once per
range-batch call (shared by every variant) or once per single-spec
evaluation -- and every node that previously re-derived these values
from `MarketBar` Decimals (indicator frame construction, setup/trigger
price series, the exit-policy frame) reads them from here instead.

This is a strict amortization, not conditional reuse: there is no
identity or memo concept. The conversion formulas are exactly the ones
every former per-node conversion used (`float(bar.<field>)` per bar,
`pd.to_datetime(time_ms, unit="ms", utc=True)`), so every value is
bit-identical to what each node computed for itself before.

Each derived value is computed lazily on first use and then retained
for the lifetime of this object. Laziness keeps observable failure
timing unchanged: a conversion that raises does so at the same point in
a candidate's evaluation as the former per-node conversion did (and
nothing is retained, so every later candidate reaching that point raises
the same way). Everything handed out is immutable (tuples of Python
floats, read-only float64 arrays, `pd.DatetimeIndex`); DataFrames are
built fresh per caller so no mutable pandas object is ever shared between
nodes or candidates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from strategy_engine.domain.market import MarketBar, MarketFrame

if TYPE_CHECKING:
    from strategy_engine.indicators.contracts import FeatureFrameLike

OHLCV_FIELDS: tuple[str, ...] = ("open", "high", "low", "close", "volume")


class MarketArrays:
    """Float64 OHLCV / `DatetimeIndex` / `time_ms` for one range's bars."""

    __slots__ = ("_bars", "_time_ms", "_index", "_values", "_arrays")

    def __init__(self, time_ms: tuple[int, ...], bars: tuple[MarketBar, ...]) -> None:
        self._bars = bars
        self._time_ms = time_ms
        self._index: pd.DatetimeIndex | None = None
        self._values: dict[str, tuple[float, ...]] = {}
        self._arrays: dict[str, np.ndarray] = {}

    @classmethod
    def from_market_frame(cls, market_frame: MarketFrame) -> MarketArrays:
        return cls(tuple(bar.open_time_ms for bar in market_frame.bars), market_frame.bars)

    @property
    def bars(self) -> tuple[MarketBar, ...]:
        return self._bars

    @property
    def time_ms(self) -> tuple[int, ...]:
        return self._time_ms

    def is_derived_from(self, market_frame: MarketFrame) -> bool:
        """True only for arrays built from this exact frame's bars
        (object identity -- never a content comparison)."""

        return self._bars is market_frame.bars

    def index(self) -> pd.DatetimeIndex:
        index = self._index
        if index is None:
            index = pd.to_datetime(self._time_ms, unit="ms", utc=True)
            self._index = index
        return index

    def values(self, field: str) -> tuple[float, ...]:
        """Per-bar `float(bar.<field>)` as a tuple of Python floats."""

        values = self._values.get(field)
        if values is None:
            if field not in OHLCV_FIELDS:
                raise KeyError(field)
            values = tuple(float(getattr(bar, field)) for bar in self._bars)
            self._values[field] = values
        return values

    def array(self, field: str) -> np.ndarray:
        """Read-only float64 array of `values(field)` (same bits)."""

        array = self._arrays.get(field)
        if array is None:
            array = np.array(self.values(field), dtype=np.float64)
            array.flags.writeable = False
            self._arrays[field] = array
        return array

    def ohlcv_columns(self) -> dict[str, object]:
        """A fresh `{field: float64 array}` dict in OHLCV column order,
        ready to seed a `pd.DataFrame` (which copies dict inputs)."""

        return {field: self.array(field) for field in OHLCV_FIELDS}

    def dataframe(self) -> pd.DataFrame:
        """A fresh float64 OHLCV DataFrame indexed by `index()`."""

        return pd.DataFrame(self.ohlcv_columns(), index=self.index())


def frame_market_arrays(frame: FeatureFrameLike) -> MarketArrays:
    """The shared arrays attached to an evaluated feature frame, or --
    for a frame constructed without them (direct/test construction) --
    arrays derived from that frame's own `time_ms`/`market_bars` through
    the same conversion."""

    arrays = frame.market_arrays
    if arrays is None:
        return MarketArrays(frame.time_ms, frame.market_bars)
    return arrays
