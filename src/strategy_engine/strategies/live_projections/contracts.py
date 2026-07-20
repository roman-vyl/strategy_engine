"""Strategy-family-neutral Live Projections adapter contracts."""

from __future__ import annotations

from typing import Protocol

from strategy_engine.strategies.application.load_live_feature_frame import LiveFeatureFrameBundle
from strategy_engine.strategies.contracts import (
    LiveEntryPlan,
    LiveEntryProjectionRequest,
    OpenTradeProjectionRequest,
)


class LiveEntryProjectionData(Protocol):
    @property
    def plans_by_side(self) -> dict[str, LiveEntryPlan | None]: ...


class DesiredProtectionData(Protocol):
    @property
    def stop_price(self) -> str: ...

    @property
    def take_price(self) -> str | None: ...


class StrategicCloseSignalData(Protocol):
    @property
    def active(self) -> bool: ...

    @property
    def reason(self) -> str | None: ...

    @property
    def component_id(self) -> str | None: ...

    @property
    def layer(self) -> str | None: ...


class OpenTradeDiagnosticsData(Protocol):
    @property
    def phase(self) -> str: ...

    @property
    def max_phase_reached(self) -> str: ...

    @property
    def bars_in_trade(self) -> int: ...

    @property
    def mfe_pct(self) -> str: ...

    @property
    def mae_pct(self) -> str: ...

    @property
    def managed_events(self) -> tuple[dict[str, object], ...]: ...


class OpenTradeProjectionData(Protocol):
    @property
    def desired_protection(self) -> DesiredProtectionData: ...

    @property
    def close_signal(self) -> StrategicCloseSignalData: ...

    @property
    def diagnostics(self) -> OpenTradeDiagnosticsData: ...


class LiveEntryProjectionAdapter(Protocol):
    strategy_id: str

    def evaluate(
        self,
        request: LiveEntryProjectionRequest,
        bundle: LiveFeatureFrameBundle,
    ) -> LiveEntryProjectionData: ...


class OpenTradeProjectionAdapter(Protocol):
    strategy_id: str

    def evaluate(
        self,
        request: OpenTradeProjectionRequest,
        bundle: LiveFeatureFrameBundle,
    ) -> OpenTradeProjectionData: ...
