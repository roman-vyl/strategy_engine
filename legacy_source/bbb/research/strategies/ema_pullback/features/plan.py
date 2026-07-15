"""Feature planning from StrategySpec without touching market data."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from research.strategies.ema_pullback.spec import (
    AnchorStackWidthSetupSpec,
    EmaBounceCounterSetupSpec,
    EmaPullbackStrategySpec,
    EmaSpec,
    ExitRuleSpec,
    SetupRuleSpec,
    TREND_STRENGTH_EPISODE_BLOCKER_COMPONENT,
    TrendStrengthEpisodeBlockerParams,
)


@dataclass(frozen=True)
class PlannedFeature:
    feature_id: str
    kind: str
    source: str | None
    timeframe: str
    period: int | None
    base_feature_id: str | None
    multiplier: float | None

    def __post_init__(self) -> None:
        if self.kind not in {"ema", "atr", "atr_distance", "rsi", "adx", "di_plus", "di_minus"}:
            raise ValueError(
                "planned feature kind must be ema|atr|atr_distance|rsi|adx|di_plus|di_minus"
            )


@dataclass(frozen=True)
class FeaturePlan:
    features: tuple[PlannedFeature, ...]
    anchor_columns: dict[str, str]
    exit_distance_columns: dict[str, str]
    rsi_columns: dict[tuple[str, int], str]
    adx_dmi_columns: dict[tuple[str, int], dict[str, str]] = field(default_factory=dict)
    setup_columns_by_instance_id: dict[str, dict[str, str]] = field(default_factory=dict)
    ema_columns: dict[tuple[str, int], str] = field(default_factory=dict)
    htf_context_columns_by_ref: dict[str, dict[str, str]] = field(default_factory=dict)

    def setup_columns_for(self, instance_id: str) -> dict[str, str]:
        if instance_id not in self.setup_columns_by_instance_id:
            raise KeyError(
                f"setup columns not planned for instance_id={instance_id!r}"
            )
        return self.setup_columns_by_instance_id[instance_id]

    def htf_context_columns_for(self, context_ref: str) -> dict[str, str]:
        if context_ref not in self.htf_context_columns_by_ref:
            raise KeyError(f"HTF context columns not planned for context_ref={context_ref!r}")
        return self.htf_context_columns_by_ref[context_ref]

    @property
    def htf_context_columns(self) -> dict[str, str]:
        """First planned context ref columns (tests); prefer htf_context_columns_for."""
        if not self.htf_context_columns_by_ref:
            return {}
        first_ref = next(iter(self.htf_context_columns_by_ref))
        return self.htf_context_columns_by_ref[first_ref]

    def ema_column(self, ema: EmaSpec) -> str:
        key = (ema.timeframe, ema.period)
        if key not in self.ema_columns:
            raise KeyError(f"EMA column not planned for timeframe={ema.timeframe!r} period={ema.period}")
        return self.ema_columns[key]

    def adx_dmi_columns_for(self, params: TrendStrengthEpisodeBlockerParams) -> dict[str, str]:
        key = (params.timeframe, params.adx_period)
        if key not in self.adx_dmi_columns:
            raise KeyError(
                f"ADX/DMI columns not planned for timeframe={params.timeframe!r} "
                f"period={params.adx_period}"
            )
        return self.adx_dmi_columns[key]


def _ema_feature_id(timeframe: str, period: int) -> str:
    return f"ema_close_{timeframe}_{period}"


def _atr_feature_id(timeframe: str, period: int) -> str:
    return f"atr_close_{timeframe}_{period}"


def _rsi_feature_id(timeframe: str, period: int) -> str:
    return f"rsi_close_{timeframe}_{period}"


def _adx_feature_id(timeframe: str, period: int) -> str:
    return f"adx_close_{timeframe}_{period}"


def _di_plus_feature_id(timeframe: str, period: int) -> str:
    return f"di_plus_close_{timeframe}_{period}"


def _di_minus_feature_id(timeframe: str, period: int) -> str:
    return f"di_minus_close_{timeframe}_{period}"


def _add_adx_dmi_features_for_tf_period(
    add: Callable[[PlannedFeature], None],
    timeframe: str,
    period: int,
    adx_dmi_columns: dict[tuple[str, int], dict[str, str]],
) -> None:
    key = (timeframe, period)
    if key in adx_dmi_columns:
        return
    for kind, feature_id in (
        ("adx", _adx_feature_id(timeframe, period)),
        ("di_plus", _di_plus_feature_id(timeframe, period)),
        ("di_minus", _di_minus_feature_id(timeframe, period)),
    ):
        add(
            PlannedFeature(
                feature_id=feature_id,
                kind=kind,
                source="close",
                timeframe=timeframe,
                period=period,
                base_feature_id=None,
                multiplier=None,
            )
        )
    adx_dmi_columns[key] = {
        "adx": _adx_feature_id(timeframe, period),
        "di_plus": _di_plus_feature_id(timeframe, period),
        "di_minus": _di_minus_feature_id(timeframe, period),
    }


def _add_adx_dmi_features(
    add: Callable[[PlannedFeature], None],
    params: TrendStrengthEpisodeBlockerParams,
    adx_dmi_columns: dict[tuple[str, int], dict[str, str]],
) -> None:
    _add_adx_dmi_features_for_tf_period(
        add,
        params.timeframe,
        params.adx_period,
        adx_dmi_columns,
    )


def _add_atr_feature_for_tf_period(
    add: Callable[[PlannedFeature], None],
    timeframe: str,
    period: int,
) -> None:
    add(
        PlannedFeature(
            feature_id=_atr_feature_id(timeframe, period),
            kind="atr",
            source="close",
            timeframe=timeframe,
            period=period,
            base_feature_id=None,
            multiplier=None,
        )
    )


def _multiplier_token(multiplier: float) -> str:
    return str(float(multiplier)).replace(".", "_")


def _add_ema_feature(
    add: Callable[[PlannedFeature], None],
    ema: EmaSpec,
    ema_columns: dict[tuple[str, int], str],
) -> None:
    add(
        PlannedFeature(
            feature_id=_ema_feature_id(ema.timeframe, ema.period),
            kind="ema",
            source=ema.source,
            timeframe=ema.timeframe,
            period=ema.period,
            base_feature_id=None,
            multiplier=None,
        )
    )
    ema_columns[(ema.timeframe, ema.period)] = _ema_feature_id(ema.timeframe, ema.period)


def _add_setup_features(
    add: Callable[[PlannedFeature], None],
    rule: SetupRuleSpec,
    spec: EmaPullbackStrategySpec,
    ema_columns: dict[tuple[str, int], str],
    setup_columns_by_instance_id: dict[str, dict[str, str]],
) -> None:
    if isinstance(rule.params, AnchorStackWidthSetupSpec):
        params = rule.params
        stack = spec.anchor_stack
        setup_columns_by_instance_id[rule.instance_id] = {
            "fast": _ema_feature_id(stack.fast.timeframe, stack.fast.period),
            "anchor": _ema_feature_id(stack.anchor.timeframe, stack.anchor.period),
            "slow": _ema_feature_id(stack.slow.timeframe, stack.slow.period),
            "atr": _atr_feature_id(params.atr_timeframe, params.atr_period),
        }
        add(
            PlannedFeature(
                feature_id=_atr_feature_id(params.atr_timeframe, params.atr_period),
                kind="atr",
                source="close",
                timeframe=params.atr_timeframe,
                period=params.atr_period,
                base_feature_id=None,
                multiplier=None,
            )
        )
        return
    if isinstance(rule.params, EmaBounceCounterSetupSpec):
        stack = spec.anchor_stack
        setup_columns_by_instance_id[rule.instance_id] = {
            "fast": _ema_feature_id(stack.fast.timeframe, stack.fast.period),
            "anchor": _ema_feature_id(stack.anchor.timeframe, stack.anchor.period),
            "slow": _ema_feature_id(stack.slow.timeframe, stack.slow.period),
        }
        return


def _ema_specs_from_exit_rule(rule: ExitRuleSpec) -> list[EmaSpec]:
    specs: list[EmaSpec] = []
    if rule.ema is not None:
        specs.append(rule.ema)
    if rule.fast_ema is not None:
        specs.append(rule.fast_ema)
    if rule.slow_ema is not None:
        specs.append(rule.slow_ema)
    return specs


def build_feature_plan_from_strategy_spec(spec: EmaPullbackStrategySpec) -> FeaturePlan:
    features: list[PlannedFeature] = []
    seen: set[str] = set()

    def add(feature: PlannedFeature) -> None:
        if feature.feature_id in seen:
            return
        seen.add(feature.feature_id)
        features.append(feature)

    for ema in (spec.anchor_stack.fast, spec.anchor_stack.anchor, spec.anchor_stack.slow):
        add(
            PlannedFeature(
                feature_id=_ema_feature_id(ema.timeframe, ema.period),
                kind="ema",
                source=ema.source,
                timeframe=ema.timeframe,
                period=ema.period,
                base_feature_id=None,
                multiplier=None,
            )
        )
    htf_context_columns_by_ref: dict[str, dict[str, str]] = {}
    for context_ref, provider in spec.contexts:
        for period in (provider.fast_period, provider.anchor_period, provider.slow_period):
            add(
                PlannedFeature(
                    feature_id=_ema_feature_id(provider.timeframe, period),
                    kind="ema",
                    source=provider.source,
                    timeframe=provider.timeframe,
                    period=period,
                    base_feature_id=None,
                    multiplier=None,
                )
            )
        htf_context_columns_by_ref[context_ref] = {
            "fast": _ema_feature_id(provider.timeframe, provider.fast_period),
            "anchor": _ema_feature_id(provider.timeframe, provider.anchor_period),
            "slow": _ema_feature_id(provider.timeframe, provider.slow_period),
        }

    all_exit_rules = (
        spec.trade_management.exit_policy.always_on.exits
        + spec.trade_management.exit_policy.profiles.aligned.exits
        + spec.trade_management.exit_policy.profiles.countertrend.exits
        + spec.trade_management.exit_policy.profiles.neutral.exits
    )

    exit_columns: dict[str, str] = {}
    ema_columns: dict[tuple[str, int], str] = {}
    setup_columns_by_instance_id: dict[str, dict[str, str]] = {}
    for setup_rule in spec.setups:
        _add_setup_features(
            add,
            setup_rule,
            spec,
            ema_columns,
            setup_columns_by_instance_id,
        )

    for rule in all_exit_rules:
        if rule.distance is None:
            continue
        base_id = _atr_feature_id(rule.distance.timeframe, rule.distance.period)
        add(
            PlannedFeature(
                feature_id=base_id,
                kind="atr",
                source="close",
                timeframe=rule.distance.timeframe,
                period=rule.distance.period,
                base_feature_id=None,
                multiplier=None,
            )
        )
        distance_id = f"{base_id}_x{_multiplier_token(rule.distance.multiplier)}"
        add(
            PlannedFeature(
                feature_id=distance_id,
                kind="atr_distance",
                source=None,
                timeframe=rule.distance.timeframe,
                period=None,
                base_feature_id=base_id,
                multiplier=float(rule.distance.multiplier),
            )
        )
        exit_columns[rule.instance_id] = distance_id
        exit_columns.setdefault(rule.exit_kind, distance_id)

    rsi_columns: dict[tuple[str, int], str] = {}
    adx_dmi_columns: dict[tuple[str, int], dict[str, str]] = {}
    rsi_specs = []
    for rule in spec.components.blockers:
        if rule.rsi is not None:
            rsi_specs.append(rule.rsi)
        if (
            rule.component_id == TREND_STRENGTH_EPISODE_BLOCKER_COMPONENT
            and rule.trend_strength is not None
        ):
            _add_adx_dmi_features(add, rule.trend_strength, adx_dmi_columns)
    for rule in all_exit_rules:
        if rule.rsi is not None:
            rsi_specs.append(rule.rsi)
        for ema in _ema_specs_from_exit_rule(rule):
            _add_ema_feature(add, ema, ema_columns)

    for rsi in rsi_specs:
        feature_id = _rsi_feature_id(rsi.timeframe, rsi.period)
        add(
            PlannedFeature(
                feature_id=feature_id,
                kind="rsi",
                source="close",
                timeframe=rsi.timeframe,
                period=rsi.period,
                base_feature_id=None,
                multiplier=None,
            )
        )
        rsi_columns[(rsi.timeframe, rsi.period)] = feature_id

    from research.strategies.ema_pullback.phase_rule_conditions.registry import (
        plan_phase_rule_condition_features,
    )

    for phase_rule in spec.trade_management.exit_management.phase_rules:
        plan_phase_rule_condition_features(
            phase_rule.condition,
            add_atr=lambda tf, period: _add_atr_feature_for_tf_period(add, tf, period),
            add_adx_dmi=lambda tf, period: _add_adx_dmi_features_for_tf_period(
                add,
                tf,
                period,
                adx_dmi_columns,
            ),
        )

    from research.strategies.ema_pullback.spec import (
        EmaCrossRuntimeExitParamsSpec,
        RsiRuntimeExitParamsSpec,
    )

    for runtime_rule in spec.trade_management.exit_management.runtime_exits:
        if isinstance(runtime_rule.params, RsiRuntimeExitParamsSpec):
            rsi = runtime_rule.params.rsi
            feature_id = _rsi_feature_id(rsi.timeframe, rsi.period)
            add(
                PlannedFeature(
                    feature_id=feature_id,
                    kind="rsi",
                    source="close",
                    timeframe=rsi.timeframe,
                    period=rsi.period,
                    base_feature_id=None,
                    multiplier=None,
                )
            )
            rsi_columns[(rsi.timeframe, rsi.period)] = feature_id
        elif isinstance(runtime_rule.params, EmaCrossRuntimeExitParamsSpec):
            for ema in (runtime_rule.params.fast_ema, runtime_rule.params.slow_ema):
                _add_ema_feature(add, ema, ema_columns)

    return FeaturePlan(
        features=tuple(features),
        anchor_columns={
            "fast": _ema_feature_id(spec.anchor_stack.fast.timeframe, spec.anchor_stack.fast.period),
            "anchor": _ema_feature_id(spec.anchor_stack.anchor.timeframe, spec.anchor_stack.anchor.period),
            "slow": _ema_feature_id(spec.anchor_stack.slow.timeframe, spec.anchor_stack.slow.period),
        },
        setup_columns_by_instance_id=setup_columns_by_instance_id,
        htf_context_columns_by_ref=htf_context_columns_by_ref,
        exit_distance_columns=exit_columns,
        rsi_columns=rsi_columns,
        adx_dmi_columns=adx_dmi_columns,
        ema_columns=ema_columns,
    )
