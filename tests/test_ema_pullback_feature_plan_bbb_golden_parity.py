from __future__ import annotations

import importlib.util
import sys
import types
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest

from strategy_engine.strategies.ema_pullback import build_feature_plan_from_canonical_spec


@dataclass(frozen=True)
class EmaSpec:
    source: str
    timeframe: str
    period: int


@dataclass(frozen=True)
class AnchorStackWidthSetupSpec:
    atr_timeframe: str = "base"
    atr_period: int = 14


@dataclass(frozen=True)
class EmaBounceCounterSetupSpec:
    max_bounces: int = 3


@dataclass(frozen=True)
class RsiRuntimeExitParamsSpec:
    rsi: object


@dataclass(frozen=True)
class EmaCrossRuntimeExitParamsSpec:
    fast_ema: EmaSpec
    slow_ema: EmaSpec


@dataclass(frozen=True)
class TrendStrengthEpisodeBlockerParams:
    timeframe: str = "base"
    adx_period: int = 14


class EmaPullbackStrategySpec:
    pass


@dataclass(frozen=True)
class LegacyFeature:
    feature_id: str
    kind: str
    source: str | None
    timeframe: str
    period: int | None
    base_feature_id: str | None
    multiplier: float | None


@dataclass(frozen=True)
class LegacyPlan:
    features: tuple[LegacyFeature, ...]
    anchor_columns: dict[str, str]
    exit_distance_columns: dict[str, str]
    rsi_columns: dict[tuple[str, int], str]
    adx_dmi_columns: dict[tuple[str, int], dict[str, str]] = field(default_factory=dict)
    setup_columns_by_instance_id: dict[str, dict[str, str]] = field(default_factory=dict)
    ema_columns: dict[tuple[str, int], str] = field(default_factory=dict)
    htf_context_columns_by_ref: dict[str, dict[str, str]] = field(default_factory=dict)


def _legacy_builder(monkeypatch: pytest.MonkeyPatch):
    spec_module = types.ModuleType("research.strategies.ema_pullback.spec")
    for name, value in {
        "AnchorStackWidthSetupSpec": AnchorStackWidthSetupSpec,
        "EmaBounceCounterSetupSpec": EmaBounceCounterSetupSpec,
        "EmaPullbackStrategySpec": EmaPullbackStrategySpec,
        "EmaSpec": EmaSpec,
        "ExitRuleSpec": object,
        "SetupRuleSpec": object,
        "TREND_STRENGTH_EPISODE_BLOCKER_COMPONENT": "trend_strength_episode_blocker",
        "TrendStrengthEpisodeBlockerParams": TrendStrengthEpisodeBlockerParams,
        "EmaCrossRuntimeExitParamsSpec": EmaCrossRuntimeExitParamsSpec,
        "RsiRuntimeExitParamsSpec": RsiRuntimeExitParamsSpec,
    }.items():
        setattr(spec_module, name, value)
    registry = types.ModuleType("research.strategies.ema_pullback.phase_rule_conditions.registry")
    registry.plan_phase_rule_condition_features = lambda condition, add_atr, add_adx_dmi: (
        add_atr(condition.params.atr.timeframe, condition.params.atr.period)
        if getattr(condition.params, "atr", None) is not None
        else None
    )
    monkeypatch.setitem(sys.modules, "research.strategies.ema_pullback.spec", spec_module)
    monkeypatch.setitem(
        sys.modules,
        "research.strategies.ema_pullback.phase_rule_conditions.registry",
        registry,
    )
    path = (
        Path(__file__).parents[1]
        / "legacy_source/bbb/research/strategies/ema_pullback/features/plan.py"
    )
    module_spec = importlib.util.spec_from_file_location("bbb_feature_plan", path)
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_spec.name] = module
    module_spec.loader.exec_module(module)
    return module


def _spec_and_wire() -> tuple[object, dict[str, object]]:
    fast = EmaSpec("close", "base", 20)
    anchor = EmaSpec("close", "base", 50)
    slow = EmaSpec("close", "base", 200)
    rsi = SimpleNamespace(timeframe="1h", period=14)
    distance = SimpleNamespace(timeframe="base", period=14, multiplier=1.5)
    exits = (
        SimpleNamespace(
            instance_id="sl",
            exit_kind="stop_loss",
            distance=distance,
            rsi=None,
            ema=None,
            fast_ema=None,
            slow_ema=None,
        ),
        SimpleNamespace(
            instance_id="rsi-exit",
            exit_kind="signal",
            distance=None,
            rsi=rsi,
            ema=None,
            fast_ema=None,
            slow_ema=None,
        ),
    )
    empty = SimpleNamespace(exits=())
    spec = SimpleNamespace(
        anchor_stack=SimpleNamespace(fast=fast, anchor=anchor, slow=slow),
        contexts=(
            (
                "htf",
                SimpleNamespace(
                    timeframe="4h",
                    source="close",
                    fast_period=20,
                    anchor_period=50,
                    slow_period=200,
                ),
            ),
        ),
        setups=(SimpleNamespace(instance_id="width", params=AnchorStackWidthSetupSpec("1h", 10)),),
        components=SimpleNamespace(
            blockers=(
                SimpleNamespace(component_id="rsi", rsi=rsi, trend_strength=None),
                SimpleNamespace(
                    component_id="trend_strength_episode_blocker",
                    rsi=None,
                    trend_strength=TrendStrengthEpisodeBlockerParams(),
                ),
            )
        ),
        trade_management=SimpleNamespace(
            exit_policy=SimpleNamespace(
                always_on=SimpleNamespace(exits=exits),
                profiles=SimpleNamespace(aligned=empty, countertrend=empty, neutral=empty),
            ),
            exit_management=SimpleNamespace(phase_rules=(), runtime_exits=()),
        ),
    )
    wire = {
        "anchor_stack": {"fast": asdict(fast), "anchor": asdict(anchor), "slow": asdict(slow)},
        "contexts": {
            "htf": {
                "component_id": "htf_context",
                "timeframe": "4h",
                "source": "close",
                "fast_period": 20,
                "anchor_period": 50,
                "slow_period": 200,
            }
        },
        "setups": [
            {
                "instance_id": "width",
                "component_id": "anchor_stack_width_setup",
                "params": {"atr_timeframe": "1h", "atr_period": 10},
            }
        ],
        "components": {
            "blockers": [
                {"component_id": "rsi", "rsi": {"timeframe": "1h", "period": 14}},
                {
                    "component_id": "trend_strength_episode_blocker",
                    "trend_strength": {"timeframe": "base", "adx_period": 14},
                },
            ]
        },
        "trade_management": {
            "exit_policy": {
                "always_on": {
                    "exits": [
                        {
                            "instance_id": "sl",
                            "exit_kind": "stop_loss",
                            "distance": {"timeframe": "base", "period": 14, "multiplier": 1.5},
                        },
                        {
                            "instance_id": "rsi-exit",
                            "exit_kind": "signal",
                            "rsi": {"timeframe": "1h", "period": 14},
                        },
                    ]
                },
                "profiles": {
                    "aligned": {"exits": []},
                    "countertrend": {"exits": []},
                    "neutral": {"exits": []},
                },
            },
            "exit_management": {},
        },
    }
    return spec, wire


def test_new_planner_matches_copied_bbb_builder(monkeypatch: pytest.MonkeyPatch) -> None:
    legacy = _legacy_builder(monkeypatch)
    spec, wire = _spec_and_wire()
    expected = legacy.build_feature_plan_from_strategy_spec(spec)
    actual = build_feature_plan_from_canonical_spec(wire)
    assert [feature.output_id for feature in actual.indicator_plan.features] == [
        feature.feature_id for feature in expected.features
    ]
    assert actual.anchor_columns == expected.anchor_columns
    assert actual.exit_distance_columns == expected.exit_distance_columns
    assert actual.rsi_columns == expected.rsi_columns
    assert actual.adx_dmi_columns == expected.adx_dmi_columns
    assert actual.setup_columns_by_instance_id == expected.setup_columns_by_instance_id
    assert actual.htf_context_columns_by_ref == expected.htf_context_columns_by_ref
