"""Indicator plan and feature-frame contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from strategy_engine.domain.market import MarketBar, MarketFrame, MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.domain.validity import Validity
from strategy_engine.domain.values import canonical_json_hash


@dataclass(frozen=True, slots=True)
class PlannedFeature:
    output_id: str
    kind: str
    timeframe: str
    source: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    dependencies: tuple[str, ...] = ()

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "output_id": self.output_id,
            "kind": self.kind,
            "timeframe": self.timeframe,
            "source": self.source,
            "parameters": self.parameters,
            "dependencies": list(self.dependencies),
        }


@dataclass(frozen=True, slots=True)
class IndicatorPlan:
    plan_version: str
    features: tuple[PlannedFeature, ...]

    @property
    def plan_hash(self) -> str:
        return canonical_json_hash(
            {
                "plan_version": self.plan_version,
                "features": [feature.canonical_payload() for feature in self.features],
            }
        )


@dataclass(frozen=True, slots=True)
class IndicatorRangeRequest:
    market: MarketStream
    time_range: TimeRange
    plan: IndicatorPlan
    expected_market_data_hash: str | None = None
    # Internal-only seam (batch-market-dataset-reuse): when set, this exact
    # already-acquired MarketFrame is used instead of fetching one, so a
    # batch caller can share one acquisition across variants. Not exposed on
    # any HTTP request DTO; absent (None) preserves today's fetch-per-call
    # behavior exactly.
    market_frame: MarketFrame | None = None


@dataclass(frozen=True, slots=True)
class FeatureFrame:
    """The public indicator-evaluation contract. `series` values are
    normalized-decimal-text strings (`ema-indicator-vertical-slice-v1`
    and sibling vertical-slice specs) -- this shape and its serialization
    semantics are unchanged by `compact-strategy-evaluation-boundary-v1`.
    Internal strategy evaluation uses `NativeFeatureFrame` instead and
    never constructs this type."""

    market: MarketStream
    requested_range: TimeRange
    time_ms: tuple[int, ...]
    series: dict[str, tuple[str | None, ...]]
    validity: dict[str, Validity]
    plan_hash: str
    market_data_hash: str
    market_bars: tuple[MarketBar, ...] = ()


class FeatureFrameLike(Protocol):
    """Structural contract shared by `FeatureFrame` and
    `NativeFeatureFrame` -- lets strategy-computation functions
    (`ema_pullback/{contexts,direction_blockers,setups,triggers,exits,
    potential_entries}.py`) accept either without duplicating their
    logic per frame type. `series` is typed loosely (`Mapping[str,
    tuple[Any, ...]]`) deliberately: it's the one field whose element
    type legitimately differs (`str | None` on the wire type, `float |
    None` natively) between the two concrete frames this Protocol
    covers -- every consumer already tolerates both via `float(value)`
    (a no-op on an already-native value)."""

    @property
    def market(self) -> MarketStream: ...

    @property
    def requested_range(self) -> TimeRange: ...

    @property
    def time_ms(self) -> tuple[int, ...]: ...

    @property
    def series(self) -> Mapping[str, tuple[Any, ...]]: ...

    @property
    def validity(self) -> dict[str, Validity]: ...

    @property
    def plan_hash(self) -> str: ...

    @property
    def market_data_hash(self) -> str: ...

    @property
    def market_bars(self) -> tuple[MarketBar, ...]: ...


@dataclass(frozen=True, slots=True)
class NativeFeatureFrame:
    """Internal-only computation result: `series` values are native
    `float | None`, never string-boxed. `RangeIndicatorEvaluator
    .evaluate_native` is the single source of indicator math; the public
    `FeatureFrame`/`evaluate` boxes this same computation at the wire
    boundary rather than duplicating the formulas
    (`compact-strategy-evaluation-boundary-v1`). Not exposed on any HTTP
    contract."""

    market: MarketStream
    requested_range: TimeRange
    time_ms: tuple[int, ...]
    series: dict[str, tuple[float | None, ...]]
    validity: dict[str, Validity]
    plan_hash: str
    market_data_hash: str
    market_bars: tuple[MarketBar, ...] = ()
