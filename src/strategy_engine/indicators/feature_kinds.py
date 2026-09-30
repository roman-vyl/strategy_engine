"""Canonical per-kind feature contract (OpenSpec
`composite-setup-pre-entry-predicates-v1`, design D13).

The single place that knows, per canonical feature kind: its public schema,
default source, whether it can be requested standalone, its validator, its
plan column label and its semantic identity parameters. `IndicatorRegistry`,
the ema_pullback feature planner and `resolve_feature` delegate here; the
predicate layer reaches features only through `plan_feature_request`.

Adding a kind means: its math branch in `evaluate_native`, one contract
entry here, and its warm-up policy. Nothing else.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.indicators.contracts import PlannedFeature
from strategy_engine.indicators.implementations.adx_dmi import validate_adx_dmi_feature
from strategy_engine.indicators.implementations.atr import validate_atr_feature
from strategy_engine.indicators.implementations.atr_distance import (
    validate_atr_distance_feature,
)
from strategy_engine.indicators.implementations.ema import validate_ema_feature
from strategy_engine.indicators.implementations.rsi import validate_rsi_feature

_EMA_SCHEMA: dict[str, Any] = {
    "indicator_id": "ema",
    "title": "Exponential Moving Average",
    "inputs": ["open", "high", "low", "close"],
    "parameters": {
        "period": {"type": "integer", "minimum": 1},
        "source": {"enum": ["open", "high", "low", "close"]},
        "timeframe": {"type": "string"},
    },
    "outputs": ["value"],
    "supports_batch": True,
    "supports_managed_replay": True,
    "supports_incremental": False,
    "compatibility_profile": "bbb_v1",
}


_ATR_SCHEMA: dict[str, Any] = {
    "indicator_id": "atr",
    "title": "Average True Range",
    "inputs": ["high", "low", "close"],
    "parameters": {
        "period": {"type": "integer", "minimum": 1},
        "source": {"const": "close"},
        "timeframe": {"type": "string"},
    },
    "outputs": ["value"],
    "supports_batch": True,
    "supports_managed_replay": True,
    "supports_incremental": False,
    "compatibility_profile": "bbb_v1",
}


_ATR_DISTANCE_SCHEMA: dict[str, Any] = {
    "indicator_id": "atr_distance",
    "title": "ATR Distance",
    "inputs": ["atr"],
    "parameters": {
        "multiplier": {"type": "number", "exclusiveMinimum": 0},
        "timeframe": {"type": "string"},
    },
    "outputs": ["value"],
    "requires_dependencies": 1,
    "supports_batch": True,
    "supports_managed_replay": True,
    "supports_incremental": False,
    "compatibility_profile": "bbb_v1",
    "derived_from": "atr",
}

_RSI_SCHEMA: dict[str, Any] = {
    "indicator_id": "rsi",
    "title": "Relative Strength Index",
    "inputs": ["close"],
    "parameters": {
        "period": {"type": "integer", "minimum": 1},
        "source": {"const": "close"},
        "timeframe": {"type": "string"},
    },
    "outputs": ["value"],
    "supports_batch": True,
    "supports_managed_replay": True,
    "supports_incremental": False,
    "compatibility_profile": "bbb_v1",
}


_ADX_SCHEMA: dict[str, Any] = {
    "indicator_id": "adx",
    "title": "Average Directional Index",
    "inputs": ["high", "low", "close"],
    "parameters": {
        "period": {"type": "integer", "minimum": 1},
        "source": {"const": "close"},
        "timeframe": {"type": "string"},
    },
    "outputs": ["value"],
    "supports_batch": True,
    "supports_managed_replay": True,
    "supports_incremental": False,
    "compatibility_profile": "bbb_v1",
    "calculation_group": "adx_dmi",
}

_DI_PLUS_SCHEMA = {**_ADX_SCHEMA, "indicator_id": "di_plus", "title": "Positive Directional Index"}
_DI_MINUS_SCHEMA = {
    **_ADX_SCHEMA,
    "indicator_id": "di_minus",
    "title": "Negative Directional Index",
}


Label = Callable[[str, str | None, Mapping[str, Any], tuple[str, ...]], str]


@dataclass(frozen=True, slots=True)
class FeatureKindContract:
    kind: str
    schema: Mapping[str, Any]
    default_source: str | None
    validate: Callable[[PlannedFeature], None]
    label: Label
    # Every semantic parameter of an already-validated feature, normalized
    # exactly as the identity has always carried it.
    identity_params: Callable[[PlannedFeature], dict[str, Any]]
    # Upstream role of the single feature dependency, for derived kinds
    # (`atr_distance`). A dependency-bearing kind is not requestable as a
    # standalone operand and its identity carries no `source`.
    dependency_role: str | None = None

    @property
    def requestable(self) -> bool:
        return self.dependency_role is None


def _close_period_label(
    kind: str,
) -> Label:
    # Source-blind: every existing kind labels as `<kind>_close_<tf>_<period>`
    # (pinned legacy EMA collision -- same timeframe/period, different source,
    # share a label; design D7 fails predicate requests closed on it).
    def label(
        timeframe: str, source: str | None, params: Mapping[str, Any], _: tuple[str, ...]
    ) -> str:
        return f"{kind}_close_{timeframe}_{params['period']}"

    return label


def _multiplier_token(multiplier: float) -> str:
    return str(float(multiplier)).replace(".", "_")


def _atr_distance_label(
    timeframe: str, source: str | None, params: Mapping[str, Any], dependencies: tuple[str, ...]
) -> str:
    return f"{dependencies[0]}_x{_multiplier_token(float(params['multiplier']))}"


def _period_identity(feature: PlannedFeature) -> dict[str, Any]:
    return {"period": int(feature.parameters["period"])}


def _multiplier_identity(feature: PlannedFeature) -> dict[str, Any]:
    return {"multiplier": float(feature.parameters["multiplier"])}


def _period_kind(
    kind: str, schema: Mapping[str, Any], validate: Callable[[PlannedFeature], None]
) -> FeatureKindContract:
    return FeatureKindContract(
        kind=kind,
        schema=schema,
        default_source="close",
        validate=validate,
        label=_close_period_label(kind),
        identity_params=_period_identity,
    )


# Declared order is the public `list_definitions` order.
_CONTRACTS: dict[str, FeatureKindContract] = {
    contract.kind: contract
    for contract in (
        _period_kind("ema", _EMA_SCHEMA, validate_ema_feature),
        _period_kind("atr", _ATR_SCHEMA, validate_atr_feature),
        FeatureKindContract(
            kind="atr_distance",
            schema=_ATR_DISTANCE_SCHEMA,
            default_source=None,
            validate=validate_atr_distance_feature,
            label=_atr_distance_label,
            identity_params=_multiplier_identity,
            dependency_role="atr",
        ),
        _period_kind("rsi", _RSI_SCHEMA, validate_rsi_feature),
        _period_kind("adx", _ADX_SCHEMA, validate_adx_dmi_feature),
        _period_kind("di_plus", _DI_PLUS_SCHEMA, validate_adx_dmi_feature),
        _period_kind("di_minus", _DI_MINUS_SCHEMA, validate_adx_dmi_feature),
    )
}


def feature_kinds() -> tuple[FeatureKindContract, ...]:
    return tuple(_CONTRACTS.values())


def find_feature_kind(kind: str) -> FeatureKindContract | None:
    return _CONTRACTS.get(kind)


def feature_kind(kind: str) -> FeatureKindContract:
    contract = _CONTRACTS.get(kind)
    if contract is None:
        raise InvalidRequestError("unsupported feature kind", kind=kind)
    return contract


def plan_feature_request(
    kind: str,
    timeframe: str | None,
    source: str | None,
    params: Mapping[str, Any],
) -> PlannedFeature:
    """Normalize one standalone feature request into the `PlannedFeature`
    the canonical plan holds for it (default timeframe `base`, the kind's
    default source, its label), validated by the kind's own validator."""

    contract = feature_kind(kind)
    if not contract.requestable:
        raise InvalidRequestError("feature kind is not requestable as an operand", kind=kind)
    resolved_timeframe = "base" if timeframe is None else timeframe
    resolved_source = contract.default_source if source is None else source
    unlabeled = PlannedFeature("", kind, resolved_timeframe, resolved_source, dict(params))
    contract.validate(unlabeled)
    return replace(
        unlabeled,
        output_id=contract.label(resolved_timeframe, resolved_source, unlabeled.parameters, ()),
    )
