"""Declared invariants for managed specs (OpenSpec
`composite-managed-phase-condition-v1`, tasks 0.1/0.2).

The corpus of `invariants.py` has no managed spec. These cases use atomic
phase rules only (all four atoms, stop/take/runtime rules, both sides, an HTF
`adx_di_threshold`) and pin exactly what that change promises to keep:

- `batch`: the `/range-batch` public line (it carries the serialized
  `managed` projection), `plan_hash`/labels and memoized node identities and
  compute counts -- the same extraction as `invariants.case_invariants`
  (design D6 "atomic rule bytes unchanged", D8, D9);
- `replay`: `/managed-replay` responses (events, per-bar decisions, final
  state) for fixed entries on both sides -- design D5;
- `open_trade`: live open-trade projection results for fixed receipts --
  design D5/D7.

Digests only, like `invariants.py`: no timings, reprs or debug fields.
"""

from __future__ import annotations

import contextlib
import copy
import functools
import json
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import strategy_engine.service.wiring as wiring
from parity.corpus import _variant, base_spec
from parity.harness import (
    _FAKE_MDS_URL,
    Case,
    _fixture_mds_client,
    _patched,
    market_fixture_meta,
)
from parity.invariants import _digest, case_invariants
from strategy_engine.adapters.http import strategy_routes
from strategy_engine.adapters.http.models import (
    ManagedReplayRequestModel,
    OpenTradeProjectionRequestModel,
)
from strategy_engine.domain.market import MarketFrame, MarketStream
from strategy_engine.domain.market_data import StreamBounds
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.service.settings import Settings

Spec = dict[str, Any]

# Entry bar indices into the market fixture (after EMA500 warm-up).
_ENTRY_INDICES = (3000, 5500, 8000)
_OPEN_TRADE_TARGET_OFFSET = 400


def _exit_management(
    *,
    proven_tf: str,
    adx_threshold: float,
    require_di: bool,
    protected_mfe_atr: float,
    runner_mfe_pct: float,
) -> dict[str, Any]:
    return {
        "mode": "managed",
        "phase_rules": [
            {
                "rule_id": "to-proven",
                "to_phase": "proven",
                "condition": {
                    "component_id": "adx_di_threshold",
                    "params": {
                        "timeframe": proven_tf,
                        "period": 14,
                        "adx_threshold": adx_threshold,
                        "require_di_alignment": require_di,
                    },
                },
            },
            {
                "rule_id": "to-protected",
                "to_phase": "protected",
                "condition": {
                    "component_id": "mfe_atr",
                    "params": {
                        "threshold": protected_mfe_atr,
                        "atr": {"timeframe": "base", "period": 48},
                    },
                },
            },
            {
                "rule_id": "to-runner",
                "to_phase": "runner",
                "condition": {"component_id": "mfe_pct", "params": {"threshold": runner_mfe_pct}},
            },
            {
                "rule_id": "to-exhaustion",
                "to_phase": "exhaustion",
                "condition": {"component_id": "bars_in_trade", "params": {"threshold": 300}},
            },
        ],
        "stop_management": [
            {
                "rule_id": "be",
                "component_id": "break_even_stop",
                "activate_when": {"phase_at_least": "protected"},
                "params": {"buffer_type": "none", "buffer": 0.0},
            },
            {
                "rule_id": "lock",
                "component_id": "lock_profit_stop",
                "activate_when": {"phase_at_least": "runner"},
                "params": {"lock_atr": 1.0, "atr": {"timeframe": "base", "period": 48}},
            },
        ],
        "take_management": [
            {
                "rule_id": "disable-tp",
                "component_id": "take_profile_switch",
                "activate_when": {"phase_at_least": "runner"},
                "params": {"action": "disable_fixed_tp"},
            }
        ],
        "runtime_exits": [
            {
                "rule_id": "close-exhaustion",
                "component_id": "phase_runtime_exit",
                "activate_when": {"phase_at_least": "exhaustion"},
                "exit_kind": "market_close",
                "params": {"exit_price": "close"},
            },
            {
                "rule_id": "rsi-exit",
                "component_id": "rsi_signal_exit",
                "activate_when": {"phase_at_least": "proven"},
                "exit_kind": "signal",
                "params": {
                    "confirm_bars": 2,
                    "rsi": {"timeframe": "base", "period": 14},
                    "long_exit_above": 75.0,
                    "short_exit_below": 25.0,
                },
            },
            {
                "rule_id": "ema-cross",
                "component_id": "ema_cross_loss_exit",
                "activate_when": {"phase_at_least": "initial_risk"},
                "exit_kind": "protective_exit",
                "params": {
                    "confirm_bars": 1,
                    "fast_ema": {"source": "close", "timeframe": "base", "period": 100},
                    "slow_ema": {"source": "close", "timeframe": "base", "period": 200},
                },
            },
        ],
    }


def _managed_spec(**exit_management: Any) -> Spec:
    spec = copy.deepcopy(base_spec())
    spec["trade_management"]["exit_management"] = _exit_management(**exit_management)
    return spec


_SPECS: dict[str, Spec] = {
    "htf_adx_aligned": _managed_spec(
        proven_tf="1h",
        adx_threshold=20.0,
        require_di=True,
        protected_mfe_atr=2.0,
        runner_mfe_pct=0.01,
    ),
    "base_adx_unaligned": _managed_spec(
        proven_tf="base",
        adx_threshold=25.0,
        require_di=False,
        protected_mfe_atr=1.5,
        runner_mfe_pct=0.008,
    ),
}


def managed_cases() -> list[Case]:
    return [
        Case(
            name="managed_atomic_rules",
            group="synthetic",
            description="managed specs with atomic phase rules only (all four atoms)",
            provenance={"change": "composite-managed-phase-condition-v1", "task": "0.1"},
            variants=[_variant(name, spec) for name, spec in _SPECS.items()],
        )
    ]


# -- market data for the single-trade and live paths -------------------------------


class _FixtureSliceMarketData:
    """Serves any aligned sub-range of the parity market fixture (the live
    loader asks for a planned window, not the fixture's full range)."""

    def __init__(self) -> None:
        meta = market_fixture_meta()
        full = _fixture_mds_client(_FAKE_MDS_URL).load_range(
            MarketStream(meta["ticker"], meta["timeframe"]),
            TimeRange(meta["from_ms"], meta["to_ms"]),
        )
        self._full = full

    def load_bounds(self, market: MarketStream) -> StreamBounds:
        bars = self._full.bars
        return StreamBounds(market, "ready", bars[0].open_time_ms, bars[-1].open_time_ms)

    def load_range(
        self,
        market: MarketStream,
        time_range: TimeRange,
        *,
        expected_market_data_hash: str | None = None,
    ) -> MarketFrame:
        bars = tuple(
            bar
            for bar in self._full.bars
            if time_range.from_ms <= bar.open_time_ms < time_range.to_ms
        )
        return MarketFrame(
            market,
            time_range,
            bars,
            f"fixture-slice:{time_range.from_ms}:{time_range.to_ms}",
        )

    def close(self) -> None:
        return None


@functools.lru_cache(maxsize=1)
def _fixture_market() -> _FixtureSliceMarketData:
    return _FixtureSliceMarketData()


@contextlib.contextmanager
def _slice_services() -> Iterator[wiring.ApplicationServices]:
    with _patched(wiring, "MarketDataServiceClient", lambda *_a, **_k: _fixture_market()):
        services = wiring.build_services(Settings(mds_base_url=_FAKE_MDS_URL))
        try:
            yield services
        finally:
            services.close()


def _bar(index: int) -> Any:
    return _fixture_market()._full.bars[index]


def _replay_invariants(services: wiring.ApplicationServices, spec: Spec) -> dict[str, str]:
    meta = market_fixture_meta()
    out: dict[str, str] = {}
    for side in ("long", "short"):
        for index in _ENTRY_INDICES:
            bar = _bar(index)
            model = ManagedReplayRequestModel.model_validate(
                {
                    "market": {
                        "ticker": meta["ticker"],
                        "base_timeframe": meta["timeframe"],
                        "from_ms": meta["from_ms"],
                        "to_ms": meta["to_ms"],
                    },
                    "strategy": {"strategy_id": "ema_pullback", "raw_spec": spec},
                    "trade_id": f"{side}-{index}",
                    "side": side,
                    "entry_time_ms": bar.open_time_ms,
                    "entry_price": float(bar.close),
                }
            )
            wire = strategy_routes.evaluate_managed_replay(model, services)
            out[f"{side}-{index}"] = _digest(json.dumps(wire, sort_keys=True))
    return out


def _open_trade_invariants(services: wiring.ApplicationServices, spec: Spec) -> dict[str, str]:
    meta = market_fixture_meta()
    out: dict[str, str] = {}
    for side in ("long", "short"):
        for index in _ENTRY_INDICES:
            plan_bar, entry_bar = _bar(index - 1), _bar(index)
            entry = Decimal(str(entry_bar.open))
            step = entry * Decimal("0.01")
            stop, take = (
                (entry - step, entry + 2 * step)
                if side == "long"
                else (
                    entry + step,
                    entry - 2 * step,
                )
            )
            model = OpenTradeProjectionRequestModel.model_validate(
                {
                    "strategy_id": "ema_pullback",
                    "raw_spec": spec,
                    "ticker": meta["ticker"],
                    "base_timeframe": meta["timeframe"],
                    "target_bar_open_time_ms": _bar(index + _OPEN_TRADE_TARGET_OFFSET).open_time_ms,
                    "executed_trade_receipt": {
                        "side": side,
                        "source_plan_bar_open_time_ms": plan_bar.open_time_ms,
                        "entry_bar_open_time_ms": entry_bar.open_time_ms,
                        "planned_entry_price": str(entry),
                        "initial_stop_price": str(stop),
                        "initial_take_price": str(take),
                        "locked_exit_profile": "aligned",
                    },
                }
            )
            result = strategy_routes.evaluate_open_trade_projection(model, services)
            out[f"{side}-{index}"] = _digest(json.dumps(result.model_dump(), sort_keys=True))
    return out


def managed_case_invariants(case: Case) -> dict[str, Any]:
    specs = {variant["variant_id"]: variant["strategy"]["raw_spec"] for variant in case.variants}
    with _slice_services() as services:
        replay = {name: _replay_invariants(services, spec) for name, spec in specs.items()}
        open_trade = {name: _open_trade_invariants(services, spec) for name, spec in specs.items()}
    return {"batch": case_invariants(case), "replay": replay, "open_trade": open_trade}
