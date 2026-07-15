"""StrategySpec contracts for ema_pullback Stage 10 pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from typing import Any, Literal

from data_engine.contracts import validate_timeframe

from research.strategies.ema_pullback.phase_rule_conditions.params import (
    PHASE_RULE_CONDITION_COMPONENT_IDS,
    PhaseRuleConditionParams,
)

BREAK_EVEN_STOP_COMPONENT = "break_even_stop"
PROFILE_ORDER = ("aligned", "countertrend", "neutral")
TRADE_MANAGEMENT_PHASES = ("initial_risk", "proven", "protected", "runner", "exhaustion")
EXIT_MANAGEMENT_MODES = ("diagnostic_only", "managed")
STOP_MANAGEMENT_COMPONENT_IDS = ("break_even_stop", "lock_profit_stop")
TAKE_MANAGEMENT_COMPONENT_IDS = ("take_profile_switch",)
RUNTIME_EXIT_COMPONENT_IDS = (
    "phase_runtime_exit",
    "rsi_signal_exit",
    "ema_cross_loss_exit",
)
RUNTIME_EXIT_ROLE = "exit_management.runtime_exit"
RUNTIME_EXIT_KINDS = ("take_profit", "protective_exit", "market_close")
RuntimeExitKind = Literal["take_profit", "protective_exit", "market_close"]
TAKE_PROFILE_SWITCH_ACTIONS = ("keep_initial", "disable_initial_tp")
TAKE_PROFILE_SWITCH_DEPRECATED_ACTION_ALIASES = ("disable_fixed_tp",)
PHASE_RUNTIME_EXIT_PRICES = ("close",)
BREAK_EVEN_BUFFER_TYPES = ("none", "atr")
ActivateWhenPhase = Literal[
    "initial_risk", "proven", "protected", "runner", "exhaustion"
]
ExitManagementMode = Literal["diagnostic_only", "managed"]

LEGACY_EXIT_MANAGEMENT_SHAPE_ERROR = (
    "Legacy exit_management shape is no longer supported; "
    "use mode=managed with stop_management/take_management/runtime_exits."
)


@dataclass(frozen=True)
class EmaSpec:
    source: str
    timeframe: str
    period: int

    def __post_init__(self) -> None:
        if self.source != "close":
            raise ValueError("ema source must be 'close'")
        if not self.timeframe.strip():
            raise ValueError("ema timeframe must be non-empty")
        if self.period <= 0:
            raise ValueError("ema period must be > 0")


@dataclass(frozen=True)
class AnchorStackSpec:
    fast: EmaSpec
    anchor: EmaSpec
    slow: EmaSpec

    def __post_init__(self) -> None:
        if not (self.fast.period < self.anchor.period < self.slow.period):
            raise ValueError("anchor stack must satisfy fast < anchor < slow periods")


@dataclass(frozen=True)
class ComponentStackSpec:
    direction: str
    blockers: tuple["BlockerRuleSpec", ...]
    trigger: "TriggerSpec"
    risk: str

    def __post_init__(self) -> None:
        for field_name in ("direction", "risk"):
            value = getattr(self, field_name)
            if not value.strip():
                raise ValueError(f"components.{field_name} must be non-empty")
        if not self.blockers:
            raise ValueError("components.blockers must contain at least one rule")
        _validate_unique_instance_ids("components.blockers", self.blockers)


@dataclass(frozen=True)
class TriggerSpec:
    component_id: str

    def __post_init__(self) -> None:
        if not self.component_id.strip():
            raise ValueError("trigger component_id must be non-empty")


def _validate_unique_instance_ids(
    collection_name: str,
    rules: tuple["BlockerRuleSpec", ...] | tuple["ExitRuleSpec", ...],
) -> None:
    seen: set[str] = set()
    for rule in rules:
        instance_id = rule.instance_id
        if not instance_id.strip():
            raise ValueError(f"{collection_name} instance_id must be non-empty")
        if instance_id in seen:
            raise ValueError(f"{collection_name} instance_id must be unique: {instance_id!r}")
        seen.add(instance_id)


@dataclass(frozen=True)
class RsiFeatureSpec:
    timeframe: str = "base"
    period: int = 14

    def __post_init__(self) -> None:
        if not self.timeframe.strip():
            raise ValueError("rsi timeframe must be non-empty")
        if self.period <= 0:
            raise ValueError("rsi period must be > 0")


TREND_STRENGTH_EPISODE_BLOCKER_COMPONENT = "trend_strength_episode_blocker"


@dataclass(frozen=True)
class TrendStrengthEpisodeBlockerParams:
    timeframe: str = "base"
    adx_period: int = 14
    min_adx_peak: float = 25.0
    peak_lookback_bars: int = 60
    max_bars_since_peak: int = 40
    min_current_adx: float = 12.0
    require_di_alignment_on_peak: bool = True
    block_on_opposite_di_flip: bool = True
    opposite_di_margin: float = 5.0

    def __post_init__(self) -> None:
        if self.timeframe.strip() != "base":
            raise ValueError(
                "trend_strength_episode_blocker MVP requires timeframe='base'"
            )
        if self.adx_period <= 0:
            raise ValueError("adx_period must be > 0")
        if self.peak_lookback_bars <= 0:
            raise ValueError("peak_lookback_bars must be > 0")
        if self.max_bars_since_peak <= 0:
            raise ValueError("max_bars_since_peak must be > 0")
        if self.min_adx_peak <= 0:
            raise ValueError("min_adx_peak must be > 0")
        if self.min_current_adx < 0:
            raise ValueError("min_current_adx must be >= 0")
        if self.opposite_di_margin < 0:
            raise ValueError("opposite_di_margin must be >= 0")


@dataclass(frozen=True)
class BlockerRuleSpec:
    instance_id: str
    component_id: str
    rsi: RsiFeatureSpec | None = None
    lookback: int = 20
    long_block_above: float | None = None
    short_block_below: float | None = None
    trend_strength: TrendStrengthEpisodeBlockerParams | None = None
    context_consumption: ContextConsumptionSpec | None = None

    def __post_init__(self) -> None:
        if not self.instance_id.strip():
            raise ValueError("blocker instance_id must be non-empty")
        if not self.component_id.strip():
            raise ValueError("blocker component_id must be non-empty")
        if self.lookback <= 0:
            raise ValueError("blocker lookback must be > 0")
        if self.component_id == TREND_STRENGTH_EPISODE_BLOCKER_COMPONENT:
            if self.trend_strength is None:
                raise ValueError(
                    "trend_strength_episode_blocker requires trend_strength params"
                )
            if self.rsi is not None:
                raise ValueError(
                    "trend_strength_episode_blocker must not set rsi params"
                )
        elif self.component_id == "rsi_lookback_extreme_blocker":
            for field_name in ("long_block_above", "short_block_below"):
                value = getattr(self, field_name)
                if value is not None and not (0 <= value <= 100):
                    raise ValueError(f"blocker {field_name} must be between 0 and 100")
        if self.trend_strength is not None and self.component_id != TREND_STRENGTH_EPISODE_BLOCKER_COMPONENT:
            raise ValueError(
                "trend_strength params only allowed for trend_strength_episode_blocker"
            )
        from research.strategies.ema_pullback.context.consumption_validation import (
            validate_blocker_context_consumption,
        )

        validate_blocker_context_consumption(self)


TradeSide = Literal["long", "short"]
ExitKind = Literal["signal", "stop_loss", "take_profit"]

_EXIT_COMPONENT_KINDS: dict[str, ExitKind] = {
    "no_signal_exit": "signal",
    "rsi_signal_exit": "signal",
    "ema_close_loss_exit": "signal",
    "ema_cross_loss_exit": "signal",
    "atr_stop_loss": "stop_loss",
    "atr_take_profit": "take_profit",
    "constant_usd_stop_loss": "stop_loss",
    "constant_usd_take_profit": "take_profit",
}

EMA_CLOSE_LOSS_EXIT_COMPONENT = "ema_close_loss_exit"
EMA_CROSS_LOSS_EXIT_COMPONENT = "ema_cross_loss_exit"


@dataclass(frozen=True)
class TradeSideSpec:
    enabled: tuple[TradeSide, ...] = ("long",)

    def __post_init__(self) -> None:
        if not self.enabled:
            raise ValueError("trade_sides.enabled must be non-empty")
        allowed = {"long", "short"}
        seen: set[str] = set()
        for side in self.enabled:
            if side not in allowed:
                raise ValueError(f"trade side must be one of {sorted(allowed)}")
            if side in seen:
                raise ValueError("trade_sides.enabled must not contain duplicates")
            seen.add(side)

    def includes(self, side: TradeSide) -> bool:
        return side in self.enabled


@dataclass(frozen=True)
class UntouchedAnchorSetupSpec:
    lookback: int = 50
    active_bars: int = 3

    def __post_init__(self) -> None:
        if self.lookback <= 0:
            raise ValueError("setup.lookback must be > 0")
        if self.active_bars <= 0:
            raise ValueError("setup.active_bars must be > 0")


@dataclass(frozen=True)
class EmaBounceCounterSetupSpec:
    max_bounces: int = 3
    raw_touch_mode: str = "range_cross"
    touch_lookback_bars: int = 10
    trend_start_confirmation_bars: int = 1
    trend_break_confirmation_bars: int = 1

    def __post_init__(self) -> None:
        if self.max_bounces <= 0:
            raise ValueError("setup.max_bounces must be > 0")
        if self.raw_touch_mode != "range_cross":
            raise ValueError("setup.raw_touch_mode must be 'range_cross'")
        if self.touch_lookback_bars <= 0:
            raise ValueError("setup.touch_lookback_bars must be > 0")
        if self.trend_start_confirmation_bars <= 0:
            raise ValueError("setup.trend_start_confirmation_bars must be > 0")
        if self.trend_break_confirmation_bars <= 0:
            raise ValueError("setup.trend_break_confirmation_bars must be > 0")


ANCHOR_STACK_WIDTH_SETUP_COMPONENT = "anchor_stack_width_setup"


@dataclass(frozen=True)
class AnchorStackWidthSetupSpec:
    atr_timeframe: str = "base"
    atr_period: int = 14
    min_current_width_atr: float = 2.0
    min_recent_width_atr: float = 4.0
    width_lookback_bars: int = 80

    def __post_init__(self) -> None:
        tf = self.atr_timeframe.strip()
        if not tf:
            raise ValueError("atr_timeframe must be non-empty")
        if tf != "base":
            validate_timeframe(tf)
        if self.atr_period <= 0:
            raise ValueError("atr_period must be > 0")
        if self.min_current_width_atr <= 0:
            raise ValueError("min_current_width_atr must be > 0")
        if self.min_recent_width_atr <= 0:
            raise ValueError("min_recent_width_atr must be > 0")
        if self.width_lookback_bars <= 0:
            raise ValueError("width_lookback_bars must be > 0")


SetupSpec = (
    UntouchedAnchorSetupSpec | EmaBounceCounterSetupSpec | AnchorStackWidthSetupSpec
)


@dataclass(frozen=True)
class SetupRuleSpec:
    instance_id: str
    component_id: str
    params: SetupSpec
    context_consumption: ContextConsumptionSpec | None = None

    def __post_init__(self) -> None:
        if not self.instance_id.strip():
            raise ValueError("setup instance_id must be non-empty")
        if not self.component_id.strip():
            raise ValueError("setup component_id must be non-empty")
        if self.component_id == "ema_bounce_counter_setup" and not isinstance(
            self.params, EmaBounceCounterSetupSpec
        ):
            raise ValueError(
                "setup params must be EmaBounceCounterSetupSpec for ema_bounce_counter_setup"
            )
        if self.component_id == "untouched_anchor_setup" and not isinstance(
            self.params, UntouchedAnchorSetupSpec
        ):
            raise ValueError(
                "setup params must be UntouchedAnchorSetupSpec for untouched_anchor_setup"
            )
        if self.component_id == ANCHOR_STACK_WIDTH_SETUP_COMPONENT and not isinstance(
            self.params, AnchorStackWidthSetupSpec
        ):
            raise ValueError(
                "setup params must be AnchorStackWidthSetupSpec for anchor_stack_width_setup"
            )
        from research.strategies.ema_pullback.context.consumption_validation import (
            validate_setup_context_consumption,
        )

        validate_setup_context_consumption(self)


@dataclass(frozen=True)
class ReclaimTriggerSpec(TriggerSpec):
    component_id: str = "reclaim_anchor"
    lookback: int = 1

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.lookback <= 0:
            raise ValueError("trigger.lookback must be > 0")


@dataclass(frozen=True)
class StrongReclaimTriggerSpec(TriggerSpec):
    component_id: str = "strong_reclaim_anchor"
    lookback: int = 1

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.lookback <= 0:
            raise ValueError("trigger.lookback must be > 0")


@dataclass(frozen=True)
class AtrDistanceSpec:
    timeframe: str
    period: int
    multiplier: float

    def __post_init__(self) -> None:
        if not self.timeframe.strip():
            raise ValueError("atr distance timeframe must be non-empty")
        if self.period <= 0:
            raise ValueError("atr distance period must be > 0")
        if self.multiplier <= 0:
            raise ValueError("atr distance multiplier must be > 0")


def _validate_ema_exit_rule_fields(rule: "ExitRuleSpec") -> None:
    if rule.component_id == EMA_CLOSE_LOSS_EXIT_COMPONENT:
        if rule.ema is None:
            raise ValueError("ema_close_loss_exit requires ema")
        if rule.fast_ema is not None or rule.slow_ema is not None:
            raise ValueError("ema_close_loss_exit must not define fast_ema or slow_ema")
        forbidden = (
            ("rsi", rule.rsi),
            ("long_exit_above", rule.long_exit_above),
            ("short_exit_below", rule.short_exit_below),
        )
        for name, value in forbidden:
            if value is not None:
                raise ValueError(f"ema_close_loss_exit must not define {name}")
        if rule.confirm_bars < 1:
            raise ValueError("ema_close_loss_exit requires confirm_bars >= 1")
        return
    if rule.component_id == EMA_CROSS_LOSS_EXIT_COMPONENT:
        if rule.ema is not None:
            raise ValueError("ema_cross_loss_exit must not define ema")
        if rule.fast_ema is None or rule.slow_ema is None:
            raise ValueError("ema_cross_loss_exit requires fast_ema and slow_ema")
        if rule.fast_ema.timeframe != rule.slow_ema.timeframe:
            raise ValueError("ema_cross_loss_exit requires fast_ema and slow_ema on the same timeframe")
        if rule.fast_ema.source != "close" or rule.slow_ema.source != "close":
            raise ValueError("ema_cross_loss_exit requires fast_ema and slow_ema source 'close'")
        if rule.fast_ema.period >= rule.slow_ema.period:
            raise ValueError("ema_cross_loss_exit requires fast_ema.period < slow_ema.period")
        forbidden = (
            ("rsi", rule.rsi),
            ("long_exit_above", rule.long_exit_above),
            ("short_exit_below", rule.short_exit_below),
        )
        for name, value in forbidden:
            if value is not None:
                raise ValueError(f"ema_cross_loss_exit must not define {name}")
        if rule.confirm_bars < 1:
            raise ValueError("ema_cross_loss_exit requires confirm_bars >= 1")


@dataclass(frozen=True)
class ExitRuleSpec:
    instance_id: str
    component_id: str
    exit_kind: ExitKind = "signal"
    rsi: RsiFeatureSpec | None = None
    ema: EmaSpec | None = None
    fast_ema: EmaSpec | None = None
    slow_ema: EmaSpec | None = None
    confirm_bars: int = 1
    long_exit_above: float | None = None
    short_exit_below: float | None = None
    distance: AtrDistanceSpec | None = None
    usd_distance: float | None = None

    def __post_init__(self) -> None:
        if not self.instance_id.strip():
            raise ValueError("exit instance_id must be non-empty")
        if not self.component_id.strip():
            raise ValueError("exit component_id must be non-empty")
        allowed = {"signal", "stop_loss", "take_profit"}
        if self.exit_kind not in allowed:
            raise ValueError(f"exit_kind must be one of {sorted(allowed)}")
        expected_kind = _EXIT_COMPONENT_KINDS.get(self.component_id)
        if expected_kind is not None and self.exit_kind != expected_kind:
            raise ValueError(
                f"exit component {self.component_id!r} requires exit_kind {expected_kind!r}"
            )
        if self.exit_kind == "signal":
            if self.distance is not None or self.usd_distance is not None:
                raise ValueError("signal exit must not define distance or usd_distance")
        elif self.component_id in {"atr_stop_loss", "atr_take_profit"}:
            if self.distance is None:
                raise ValueError(f"{self.component_id} exit requires distance")
            if self.usd_distance is not None:
                raise ValueError(f"{self.component_id} exit must not define usd_distance")
        elif self.component_id in {"constant_usd_stop_loss", "constant_usd_take_profit"}:
            if self.usd_distance is None or self.usd_distance <= 0:
                raise ValueError(f"{self.component_id} exit requires positive usd_distance")
            if self.distance is not None:
                raise ValueError(f"{self.component_id} exit must not define distance")
        elif self.exit_kind in {"stop_loss", "take_profit"}:
            raise ValueError(f"unsupported distance exit component_id {self.component_id!r}")
        if self.exit_kind in {"stop_loss", "take_profit"}:
            if self.rsi is not None or self.long_exit_above is not None or self.short_exit_below is not None:
                raise ValueError(f"{self.exit_kind} exit must not define signal thresholds")
        for field_name in ("long_exit_above", "short_exit_below"):
            value = getattr(self, field_name)
            if value is not None and not (0 <= value <= 100):
                raise ValueError(f"exit {field_name} must be between 0 and 100")
        if self.component_id in {EMA_CLOSE_LOSS_EXIT_COMPONENT, EMA_CROSS_LOSS_EXIT_COMPONENT}:
            _validate_ema_exit_rule_fields(self)


@dataclass(frozen=True)
class ContextProviderSpec:
    component_id: str
    timeframe: str
    source: str
    fast_period: int
    anchor_period: int
    slow_period: int

    def __post_init__(self) -> None:
        path = "strategy.contexts"
        if self.component_id != "htf_context":
            raise ValueError(f"{path} provider component_id must be 'htf_context'")
        if not self.timeframe.strip():
            raise ValueError(f"{path} provider timeframe must be non-empty")
        if self.source != "close":
            raise ValueError(f"{path} provider source must be 'close'")
        if self.fast_period <= 0 or self.anchor_period <= 0 or self.slow_period <= 0:
            raise ValueError(f"{path} provider periods must be > 0")
        if not (self.fast_period < self.anchor_period < self.slow_period):
            raise ValueError(f"{path} provider must satisfy fast < anchor < slow periods")


@dataclass(frozen=True)
class ContextConsumptionPolicySpec:
    policy_id: str
    params: tuple[tuple[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if not self.policy_id.strip():
            raise ValueError("context_consumption.policy.policy_id must be non-empty")


@dataclass(frozen=True)
class ContextConsumptionSpec:
    context_ref: str
    policy: ContextConsumptionPolicySpec

    def __post_init__(self) -> None:
        if not self.context_ref.strip():
            raise ValueError("context_consumption.context_ref must be non-empty")


@dataclass(frozen=True)
class ExitPolicyGroupSpec:
    exits: tuple[ExitRuleSpec, ...]


@dataclass(frozen=True)
class ExitPolicyProfilesSpec:
    aligned: ExitPolicyGroupSpec
    countertrend: ExitPolicyGroupSpec
    neutral: ExitPolicyGroupSpec


def _exit_policy_has_profile_exits(profiles: ExitPolicyProfilesSpec) -> bool:
    return any(
        len(group.exits) > 0
        for group in (profiles.aligned, profiles.countertrend, profiles.neutral)
    )


@dataclass(frozen=True)
class ExitPolicySpec:
    always_on: ExitPolicyGroupSpec
    profiles: ExitPolicyProfilesSpec
    context_consumption: ContextConsumptionSpec | None = None

    def __post_init__(self) -> None:
        if _exit_policy_has_profile_exits(self.profiles) and self.context_consumption is None:
            raise ValueError(
                "trade_management.exit_policy.context_consumption is required when "
                "profile-scoped exits are non-empty"
            )
        rules_with_scope: list[tuple[str, tuple[ExitRuleSpec, ...]]] = [
            ("trade_management.exit_policy.always_on.exits", self.always_on.exits),
            ("trade_management.exit_policy.profiles.aligned.exits", self.profiles.aligned.exits),
            ("trade_management.exit_policy.profiles.countertrend.exits", self.profiles.countertrend.exits),
            ("trade_management.exit_policy.profiles.neutral.exits", self.profiles.neutral.exits),
        ]
        seen: set[str] = set()
        total = 0
        for scope, rules in rules_with_scope:
            total += len(rules)
            for rule in rules:
                instance_id = rule.instance_id
                if not instance_id.strip():
                    raise ValueError(f"{scope} instance_id must be non-empty")
                if instance_id in seen:
                    raise ValueError(
                        "trade_management.exit_policy instance_id must be globally unique: "
                        f"{instance_id!r}"
                    )
                seen.add(instance_id)
        if total == 0:
            raise ValueError("trade_management.exit_policy must contain at least one exit rule")


@dataclass(frozen=True)
class PhaseRuleConditionSpec:
    component_id: str
    params: PhaseRuleConditionParams

    def __post_init__(self) -> None:
        if self.component_id not in PHASE_RULE_CONDITION_COMPONENT_IDS:
            allowed = ", ".join(repr(item) for item in PHASE_RULE_CONDITION_COMPONENT_IDS)
            raise ValueError(
                f"phase_rules condition.component_id must be one of: {allowed}; "
                f"got {self.component_id!r}"
            )


@dataclass(frozen=True)
class PhaseRuleSpec:
    rule_id: str
    to_phase: Literal["proven", "protected", "runner", "exhaustion"]
    condition: PhaseRuleConditionSpec

    def __post_init__(self) -> None:
        if not self.rule_id.strip():
            raise ValueError("phase_rules rule_id must be non-empty")
        allowed = TRADE_MANAGEMENT_PHASES[1:]
        if self.to_phase not in allowed:
            allowed_text = ", ".join(repr(item) for item in allowed)
            raise ValueError(f"phase_rules to_phase must be one of: {allowed_text}")


@dataclass(frozen=True)
class ManagementAtrRefSpec:
    timeframe: str = "base"
    period: int = 14

    def __post_init__(self) -> None:
        if not self.timeframe.strip():
            raise ValueError("management rule params atr.timeframe must be non-empty")
        if self.period <= 0:
            raise ValueError("management rule params atr.period must be > 0")


@dataclass(frozen=True)
class ManagementActivateWhenSpec:
    phase_at_least: ActivateWhenPhase

    def __post_init__(self) -> None:
        if self.phase_at_least not in TRADE_MANAGEMENT_PHASES:
            allowed = ", ".join(repr(item) for item in TRADE_MANAGEMENT_PHASES)
            raise ValueError(f"activate_when.phase_at_least must be one of: {allowed}")


@dataclass(frozen=True)
class BreakEvenStopParamsSpec:
    buffer_type: Literal["none", "atr"] = "none"
    buffer: float = 0.0
    buffer_atr: float = 0.0
    atr_period: int = 14
    atr: ManagementAtrRefSpec | None = None

    def __post_init__(self) -> None:
        if self.buffer_type not in BREAK_EVEN_BUFFER_TYPES:
            allowed = ", ".join(repr(item) for item in BREAK_EVEN_BUFFER_TYPES)
            raise ValueError(f"break_even_stop params.buffer_type must be one of: {allowed}")
        if self.buffer < 0:
            raise ValueError("break_even_stop params.buffer must be >= 0")
        if self.buffer_atr < 0:
            raise ValueError("break_even_stop params.buffer_atr must be >= 0")
        effective_period = self.atr.period if self.atr is not None else self.atr_period
        if effective_period <= 0:
            raise ValueError("break_even_stop params atr_period must be > 0")


@dataclass(frozen=True)
class LockProfitStopParamsSpec:
    lock_atr: float
    atr_period: int = 14
    atr: ManagementAtrRefSpec | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.lock_atr) or self.lock_atr <= 0:
            raise ValueError("lock_profit_stop params.lock_atr must be a finite number > 0")
        effective_period = self.atr.period if self.atr is not None else self.atr_period
        if effective_period <= 0:
            raise ValueError("lock_profit_stop params atr_period must be > 0")


@dataclass(frozen=True)
class StopManagementRuleSpec:
    rule_id: str
    component_id: Literal["break_even_stop", "lock_profit_stop"]
    activate_when: ManagementActivateWhenSpec
    params: BreakEvenStopParamsSpec | LockProfitStopParamsSpec

    def __post_init__(self) -> None:
        if not self.rule_id.strip():
            raise ValueError("stop_management rule_id must be non-empty")
        if self.component_id not in STOP_MANAGEMENT_COMPONENT_IDS:
            allowed = ", ".join(repr(item) for item in STOP_MANAGEMENT_COMPONENT_IDS)
            raise ValueError(f"stop_management component_id must be one of: {allowed}")
        if self.component_id == "break_even_stop" and not isinstance(
            self.params, BreakEvenStopParamsSpec
        ):
            raise ValueError("break_even_stop rule requires break_even_stop params")
        if self.component_id == "lock_profit_stop" and not isinstance(
            self.params, LockProfitStopParamsSpec
        ):
            raise ValueError("lock_profit_stop rule requires lock_profit_stop params")


@dataclass(frozen=True)
class TakeProfileSwitchParamsSpec:
    action: Literal["keep_initial", "disable_initial_tp"]

    def __post_init__(self) -> None:
        if self.action not in TAKE_PROFILE_SWITCH_ACTIONS:
            allowed = ", ".join(repr(item) for item in TAKE_PROFILE_SWITCH_ACTIONS)
            raise ValueError(f"take_profile_switch params.action must be one of: {allowed}")


@dataclass(frozen=True)
class TakeManagementRuleSpec:
    rule_id: str
    component_id: Literal["take_profile_switch"]
    activate_when: ManagementActivateWhenSpec
    params: TakeProfileSwitchParamsSpec

    def __post_init__(self) -> None:
        if not self.rule_id.strip():
            raise ValueError("take_management rule_id must be non-empty")
        if self.component_id not in TAKE_MANAGEMENT_COMPONENT_IDS:
            allowed = ", ".join(repr(item) for item in TAKE_MANAGEMENT_COMPONENT_IDS)
            raise ValueError(f"take_management component_id must be one of: {allowed}")


@dataclass(frozen=True)
class PhaseRuntimeExitParamsSpec:
    exit_price: Literal["close"]

    def __post_init__(self) -> None:
        if self.exit_price not in PHASE_RUNTIME_EXIT_PRICES:
            allowed = ", ".join(repr(item) for item in PHASE_RUNTIME_EXIT_PRICES)
            raise ValueError(f"phase_runtime_exit params.exit_price must be one of: {allowed}")


@dataclass(frozen=True)
class RsiRuntimeExitParamsSpec:
    rsi: RsiFeatureSpec
    long_exit_above: float | None = None
    short_exit_below: float | None = None
    confirm_bars: int = 1

    def __post_init__(self) -> None:
        if self.confirm_bars < 1:
            raise ValueError("runtime rsi_signal_exit params.confirm_bars must be >= 1")
        for field_name in ("long_exit_above", "short_exit_below"):
            value = getattr(self, field_name)
            if value is not None and not (0 <= value <= 100):
                raise ValueError(f"runtime rsi_signal_exit {field_name} must be between 0 and 100")


@dataclass(frozen=True)
class EmaCrossRuntimeExitParamsSpec:
    fast_ema: EmaSpec
    slow_ema: EmaSpec
    confirm_bars: int = 1

    def __post_init__(self) -> None:
        if self.fast_ema.timeframe != self.slow_ema.timeframe:
            raise ValueError("runtime ema_cross_loss_exit fast_ema and slow_ema must share timeframe")
        if self.fast_ema.period >= self.slow_ema.period:
            raise ValueError("runtime ema_cross_loss_exit requires fast_ema.period < slow_ema.period")
        if self.confirm_bars < 1:
            raise ValueError("runtime ema_cross_loss_exit params.confirm_bars must be >= 1")


RuntimeExitParamsSpec = (
    PhaseRuntimeExitParamsSpec
    | RsiRuntimeExitParamsSpec
    | EmaCrossRuntimeExitParamsSpec
)


@dataclass(frozen=True)
class RuntimeExitRuleSpec:
    rule_id: str
    component_id: str
    role: str
    activate_when: ManagementActivateWhenSpec
    exit_kind: RuntimeExitKind
    params: RuntimeExitParamsSpec

    def __post_init__(self) -> None:
        if not self.rule_id.strip():
            raise ValueError("runtime_exits rule_id must be non-empty")
        if self.component_id not in RUNTIME_EXIT_COMPONENT_IDS:
            allowed = ", ".join(repr(item) for item in RUNTIME_EXIT_COMPONENT_IDS)
            raise ValueError(f"runtime_exits component_id must be one of: {allowed}")
        if self.role != RUNTIME_EXIT_ROLE:
            raise ValueError(
                f"runtime_exits role must be {RUNTIME_EXIT_ROLE!r}; got {self.role!r}"
            )
        if self.exit_kind not in RUNTIME_EXIT_KINDS:
            allowed = ", ".join(repr(item) for item in RUNTIME_EXIT_KINDS)
            raise ValueError(f"runtime_exits exit_kind must be one of: {allowed}")
        if self.exit_kind == "signal":
            raise ValueError(
                "runtime_exits exit_kind 'signal' is not allowed; "
                "use take_profit, protective_exit, or market_close"
            )
        from research.strategies.ema_pullback.consumer_roles import validate_consumer_role

        validate_consumer_role(component_id=self.component_id, role=self.role)
        if self.component_id == "phase_runtime_exit":
            if not isinstance(self.params, PhaseRuntimeExitParamsSpec):
                raise ValueError("phase_runtime_exit requires params.exit_price")
            if self.exit_kind != "market_close":
                raise ValueError("phase_runtime_exit requires exit_kind market_close")
        elif self.component_id == "rsi_signal_exit":
            if not isinstance(self.params, RsiRuntimeExitParamsSpec):
                raise ValueError("rsi_signal_exit runtime rule requires rsi params")
        elif self.component_id == "ema_cross_loss_exit":
            if not isinstance(self.params, EmaCrossRuntimeExitParamsSpec):
                raise ValueError("ema_cross_loss_exit runtime rule requires fast_ema/slow_ema params")


def empty_exit_management() -> "ExitManagementSpec":
    return ExitManagementSpec()


@dataclass(frozen=True)
class ExitManagementSpec:
    mode: ExitManagementMode | None = None
    phase_rules: tuple[PhaseRuleSpec, ...] = ()
    stop_management: tuple[StopManagementRuleSpec, ...] = ()
    take_management: tuple[TakeManagementRuleSpec, ...] = ()
    runtime_exits: tuple[RuntimeExitRuleSpec, ...] = ()

    def __post_init__(self) -> None:
        if self.mode is not None and self.mode not in EXIT_MANAGEMENT_MODES:
            allowed = ", ".join(repr(item) for item in EXIT_MANAGEMENT_MODES)
            raise ValueError(
                f"trade_management.exit_management.mode must be one of: {allowed}"
            )
        has_management_rules = bool(
            self.stop_management or self.take_management or self.runtime_exits
        )
        if self.phase_rules and self.mode not in ("diagnostic_only", "managed"):
            raise ValueError(
                "trade_management.exit_management.phase_rules require "
                "mode='diagnostic_only' or mode='managed'"
            )
        if self.mode == "diagnostic_only":
            if self.stop_management:
                raise ValueError(
                    "trade_management.exit_management.stop_management is not allowed in "
                    "diagnostic-only mode"
                )
            if self.take_management:
                raise ValueError(
                    "trade_management.exit_management.take_management is not allowed in "
                    "diagnostic-only mode"
                )
            if self.runtime_exits:
                raise ValueError(
                    "trade_management.exit_management.runtime_exits is not allowed in "
                    "diagnostic-only mode"
                )
        elif self.mode != "managed" and has_management_rules:
            raise ValueError(
                "trade_management.exit_management stop_management, take_management, and "
                "runtime_exits require mode='managed'"
            )
        seen_phase_rules: set[str] = set()
        last_phase_rank = 0
        for rule in self.phase_rules:
            if rule.rule_id in seen_phase_rules:
                raise ValueError(
                    "trade_management.exit_management.phase_rules rule_id must be unique: "
                    f"{rule.rule_id!r}"
                )
            seen_phase_rules.add(rule.rule_id)
            phase_rank = TRADE_MANAGEMENT_PHASES.index(rule.to_phase)
            if phase_rank < last_phase_rank:
                raise ValueError(
                    "trade_management.exit_management.phase_rules must be ordered by "
                    "non-decreasing phase progression"
                )
            last_phase_rank = phase_rank
        seen_management_rule_ids: set[str] = set()
        for rule in (
            *self.stop_management,
            *self.take_management,
            *self.runtime_exits,
        ):
            if rule.rule_id in seen_management_rule_ids:
                raise ValueError(
                    "trade_management.exit_management management rule_id must be unique "
                    "across stop_management, take_management, and runtime_exits: "
                    f"{rule.rule_id!r}"
                )
            seen_management_rule_ids.add(rule.rule_id)


@dataclass(frozen=True)
class TradeManagementSpec:
    exit_policy: ExitPolicySpec
    exit_management: ExitManagementSpec = field(default_factory=empty_exit_management)

    def __post_init__(self) -> None:
        exit_ids: set[str] = set()
        for rules in (
            self.exit_policy.always_on.exits,
            self.exit_policy.profiles.aligned.exits,
            self.exit_policy.profiles.countertrend.exits,
            self.exit_policy.profiles.neutral.exits,
        ):
            for rule in rules:
                if rule.instance_id in exit_ids:
                    raise ValueError(
                        "trade_management.exit_policy instance_id must be globally unique: "
                        f"{rule.instance_id!r}"
                    )
                exit_ids.add(rule.instance_id)


@dataclass(frozen=True)
class EmaPullbackStrategySpec:
    variant: str
    symbol: str
    base_timeframe: str
    anchor_stack: AnchorStackSpec
    components: ComponentStackSpec
    trade_sides: TradeSideSpec
    setups: tuple[SetupRuleSpec, ...]
    trade_management: TradeManagementSpec
    contexts: tuple[tuple[str, ContextProviderSpec], ...] = ()

    def contexts_by_ref(self) -> dict[str, ContextProviderSpec]:
        return dict(self.contexts)

    def __post_init__(self) -> None:
        if not self.variant.strip():
            raise ValueError("variant must be non-empty")
        if not self.symbol.strip():
            raise ValueError("symbol must be non-empty")
        if not self.base_timeframe.strip():
            raise ValueError("base_timeframe must be non-empty")
        if not self.setups:
            raise ValueError("setups must contain at least one rule")
        _validate_unique_instance_ids("setups", self.setups)
        seen_refs: set[str] = set()
        for context_ref, _provider in self.contexts:
            if context_ref in seen_refs:
                raise ValueError(f"strategy.contexts has duplicate context_ref: {context_ref!r}")
            seen_refs.add(context_ref)
        consumption = self.trade_management.exit_policy.context_consumption
        if consumption is not None and consumption.context_ref not in seen_refs:
            raise ValueError(
                "trade_management.exit_policy.context_consumption.context_ref "
                f"{consumption.context_ref!r} is not defined in strategy.contexts"
            )
        for rule in self.components.blockers:
            blocker_consumption = rule.context_consumption
            if blocker_consumption is None:
                continue
            if blocker_consumption.context_ref not in seen_refs:
                raise ValueError(
                    f"blockers[{rule.instance_id!r}].context_consumption.context_ref "
                    f"{blocker_consumption.context_ref!r} is not defined in strategy.contexts"
                )
        for rule in self.setups:
            setup_consumption = rule.context_consumption
            if setup_consumption is None:
                continue
            if setup_consumption.context_ref not in seen_refs:
                raise ValueError(
                    f"setups[{rule.instance_id!r}].context_consumption.context_ref "
                    f"{setup_consumption.context_ref!r} is not defined in strategy.contexts"
                )


def _normalize_policy_params_wire(params: Any) -> dict[str, Any]:
    if params is None:
        return {}
    if isinstance(params, dict):
        return params
    if isinstance(params, (list, tuple)):
        return dict(params)
    return {}


def _normalize_context_consumption_wire(block: Any) -> None:
    if not isinstance(block, dict):
        return
    policy = block.get("policy")
    if isinstance(policy, dict) and "params" in policy:
        policy["params"] = _normalize_policy_params_wire(policy["params"])


def strategy_spec_to_dict(spec: EmaPullbackStrategySpec) -> dict[str, Any]:
    payload = asdict(spec)
    # Wire format for reports / API: contexts as {ref: provider}, not asdict's tuple-of-tuples.
    if spec.contexts:
        payload["contexts"] = {
            context_ref: asdict(provider) for context_ref, provider in spec.contexts
        }
    else:
        payload.pop("contexts", None)
    components = payload.get("components")
    if isinstance(components, dict):
        blockers = components.get("blockers")
        if isinstance(blockers, (list, tuple)):
            for blocker in blockers:
                if isinstance(blocker, dict):
                    _normalize_context_consumption_wire(blocker.get("context_consumption"))
    trade_management = payload.get("trade_management")
    if isinstance(trade_management, dict):
        exit_policy = trade_management.get("exit_policy")
        if isinstance(exit_policy, dict):
            _normalize_context_consumption_wire(exit_policy.get("context_consumption"))
        exit_management = trade_management.get("exit_management")
        if isinstance(exit_management, dict):
            if exit_management.get("mode") is None:
                exit_management.pop("mode", None)
            for key in ("phase_rules", "stop_management", "take_management", "runtime_exits"):
                value = exit_management.get(key)
                if value in ((), [], None):
                    exit_management.pop(key, None)
                elif isinstance(value, tuple):
                    exit_management[key] = list(value)
    setups = payload.get("setups")
    if isinstance(setups, (list, tuple)):
        for setup in setups:
            if isinstance(setup, dict):
                _normalize_context_consumption_wire(setup.get("context_consumption"))
    return payload


def strategy_spec_config_id(spec: EmaPullbackStrategySpec) -> str:
    payload = json.dumps(strategy_spec_to_dict(spec), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
