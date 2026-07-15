"""Component catalog for Workbench Composer (ema_pullback MVP stub)."""

from __future__ import annotations

from strategy_engine.strategies.composer.contracts import (
    ComponentCatalog,
    ComponentSchema,
    ComposerSectionSchema,
    ContextConsumptionPolicySchema,
    ContextConsumptionRoleSchema,
    ContextProviderSchema,
    ParamFieldSchema,
)

_TF_ENUM = ["base", "5m", "15m", "1h", "4h"]


def _tf_param(key: str, *, default: str = "base") -> ParamFieldSchema:
    return ParamFieldSchema(type="string", label=key, enum=_TF_ENUM, default=default)


def _int_param(label: str, *, default: int, min_val: int = 1) -> ParamFieldSchema:
    return ParamFieldSchema(type="integer", label=label, min=float(min_val), default=default)


def _num_param(label: str, *, default: float) -> ParamFieldSchema:
    return ParamFieldSchema(type="number", label=label, default=default)


def _bool_param(label: str, *, default: bool) -> ParamFieldSchema:
    return ParamFieldSchema(type="boolean", label=label, default=default)


_BLOCKER_CONTEXT_POLICIES = [
    ContextConsumptionPolicySchema(
        policy_id="htf_regime_gate",
        label="HTF regime gate",
        params_schema={
            "allowed_regimes": ParamFieldSchema(
                type="array",
                label="Allowed regimes",
                enum=["aligned", "countertrend", "neutral"],
            ),
        },
    ),
]
_SETUP_CONTEXT_POLICIES = [
    ContextConsumptionPolicySchema(
        policy_id="htf_regime_gate",
        label="HTF regime gate",
        params_schema={
            "allowed_regimes": ParamFieldSchema(
                type="array",
                label="Allowed regimes",
                enum=["aligned", "countertrend", "neutral"],
            ),
        },
    ),
]


def get_component_catalog(*, family: str = "ema_pullback") -> ComponentCatalog:
    if family != "ema_pullback":
        raise ValueError(f"unsupported family {family!r}; supported: ema_pullback")

    sections = [
        ComposerSectionSchema(section_id="envelope", label="Experiment"),
        ComposerSectionSchema(section_id="instances", label="Instances"),
        ComposerSectionSchema(section_id="market", label="Market"),
        ComposerSectionSchema(section_id="anchor_stack", label="Anchor stack"),
        ComposerSectionSchema(section_id="trade_sides", label="Trade sides"),
        ComposerSectionSchema(section_id="direction", label="Direction", role="direction"),
        ComposerSectionSchema(section_id="setup", label="Setup", role="setup"),
        ComposerSectionSchema(section_id="trigger", label="Trigger", role="trigger"),
        ComposerSectionSchema(
            section_id="blockers",
            label="Blockers",
            role="blockers",
            list_slot=True,
        ),
        ComposerSectionSchema(section_id="risk", label="Risk", role="risk"),
        ComposerSectionSchema(
            section_id="trade_management",
            label="Trade management",
        ),
        ComposerSectionSchema(
            section_id="strategy_contexts",
            label="Strategy contexts",
        ),
        ComposerSectionSchema(
            section_id="exit_policy_consumption",
            label="Exit policy context consumption",
        ),
        ComposerSectionSchema(
            section_id="exit_policy_always_on",
            label="Exit policy always-on exits",
            role="exits",
            list_slot=True,
        ),
        ComposerSectionSchema(
            section_id="exit_policy_profiles",
            label="Exit policy profiles",
        ),
        ComposerSectionSchema(
            section_id="exit_policy_profile_aligned",
            label="Profile aligned exits",
            role="exits",
            list_slot=True,
        ),
        ComposerSectionSchema(
            section_id="exit_policy_profile_countertrend",
            label="Profile countertrend exits",
            role="exits",
            list_slot=True,
        ),
        ComposerSectionSchema(
            section_id="exit_policy_profile_neutral",
            label="Profile neutral exits",
            role="exits",
            list_slot=True,
        ),
        ComposerSectionSchema(
            section_id="exit_management_always_on",
            label="Exit management runtime (legacy always-on rules deprecated)",
            role="exit_management",
            list_slot=True,
        ),
        ComposerSectionSchema(
            section_id="exit_management_profiles",
            label="Exit management runtime profiles (legacy rules deprecated)",
        ),
        ComposerSectionSchema(
            section_id="exit_management_profile_aligned",
            label="Profile aligned runtime (legacy rules deprecated)",
            role="exit_management",
            list_slot=True,
        ),
        ComposerSectionSchema(
            section_id="exit_management_profile_countertrend",
            label="Profile countertrend runtime (legacy rules deprecated)",
            role="exit_management",
            list_slot=True,
        ),
        ComposerSectionSchema(
            section_id="exit_management_profile_neutral",
            label="Profile neutral runtime (legacy rules deprecated)",
            role="exit_management",
            list_slot=True,
        ),
    ]

    components = [
        ComponentSchema(
            component_id="ema_anchor_stack_trend",
            role="direction",
            label="EMA anchor stack trend",
            description="Long when fast > anchor > slow; short mirrors.",
        ),
        ComponentSchema(
            component_id="untouched_anchor_setup",
            role="setup",
            label="Untouched anchor setup",
            description=(
                "Armed regime: anchor untouched for lookback bars, "
                "then active through first touch and active_bars window."
            ),
            params_schema={
                "lookback": _int_param("Untouched lookback bars", default=50),
                "active_bars": _int_param("Active bars after first touch", default=3),
            },
            supports_context_consumption=True,
            context_consumption_policies=_SETUP_CONTEXT_POLICIES,
        ),
        ComponentSchema(
            component_id="ema_bounce_counter_setup",
            role="setup",
            label="EMA bounce counter setup",
            description=(
                "Market-state gate: allow entries until anchor EMA bounce interactions "
                "exhaust max_bounces. Uses strategy.anchor_stack EMAs; does not define "
                "its own EMA periods."
            ),
            params_storage="nested",
            params_schema={
                "max_bounces": _int_param("Max completed bounces", default=3),
                "raw_touch_mode": ParamFieldSchema(
                    type="string",
                    label="Raw touch mode",
                    enum=["range_cross"],
                    default="range_cross",
                ),
                "touch_lookback_bars": _int_param("Touch lookback bars", default=10),
                "trend_start_confirmation_bars": _int_param(
                    "Trend start confirmation bars", default=1
                ),
                "trend_break_confirmation_bars": _int_param(
                    "Trend break confirmation bars", default=1
                ),
            },
            supports_context_consumption=True,
            context_consumption_policies=_SETUP_CONTEXT_POLICIES,
        ),
        ComponentSchema(
            component_id="anchor_stack_width_setup",
            role="setup",
            label="Anchor stack width setup",
            description=(
                "Checks whether the anchor EMA stack is wide enough for an EMA-pullback "
                "setup. Does not count touches or create an entry trigger; verifies fast "
                "and slow EMA are sufficiently separated relative to ATR. Current width "
                "checks the stack on the entry bar; recent width checks expansion within "
                "the lookback window."
            ),
            params_storage="nested",
            params_schema={
                "atr_timeframe": _tf_param("ATR timeframe"),
                "atr_period": _int_param("ATR period", default=14),
                "min_current_width_atr": _num_param("Min current width (ATR)", default=2.0),
                "min_recent_width_atr": _num_param("Min recent width (ATR)", default=4.0),
                "width_lookback_bars": _int_param("Width lookback bars", default=80),
            },
            supports_context_consumption=True,
            context_consumption_policies=_SETUP_CONTEXT_POLICIES,
        ),
        ComponentSchema(
            component_id="reclaim_anchor",
            role="trigger",
            label="Reclaim anchor",
            description=("Wick probed anchor within prior lookback bars; entry on close reclaim."),
            params_schema={
                "lookback": _int_param("Wick probe lookback bars", default=1),
            },
        ),
        ComponentSchema(
            component_id="strong_reclaim_anchor",
            role="trigger",
            label="Strong reclaim anchor",
            description=("Close lost anchor within prior lookback bars; entry on close reclaim."),
            params_schema={
                "lookback": _int_param("Close probe lookback bars", default=1),
            },
        ),
        ComponentSchema(
            component_id="touch_anchor",
            role="trigger",
            label="Touch anchor",
        ),
        ComponentSchema(
            component_id="no_blockers",
            role="blockers",
            label="No blockers",
            list_slot=True,
        ),
        ComponentSchema(
            component_id="counter_candle_blocker",
            role="blockers",
            label="Counter candle blocker",
            list_slot=True,
            supports_context_consumption=True,
            context_consumption_policies=_BLOCKER_CONTEXT_POLICIES,
        ),
        ComponentSchema(
            component_id="rsi_lookback_extreme_blocker",
            role="blockers",
            label="RSI lookback extreme blocker",
            list_slot=True,
            supports_context_consumption=True,
            context_consumption_policies=_BLOCKER_CONTEXT_POLICIES,
            params_schema={
                "rsi.timeframe": _tf_param("RSI timeframe", default="5m"),
                "rsi.period": _int_param("RSI period", default=14),
                "lookback": _int_param("Lookback", default=20),
                "long_block_above": _num_param("Long block above RSI", default=80.0),
                "short_block_below": _num_param("Short block below RSI", default=20.0),
            },
        ),
        ComponentSchema(
            component_id="trend_strength_episode_blocker",
            role="blockers",
            label="Trend strength episode blocker",
            description=(
                "Episode-style ADX/DMI gate for pullback entries: requires a recent "
                "strength confirmation, not high ADX on the entry bar. "
                "Peak = most recent qualifying bar in lookback (ADX ≥ min_adx_peak), "
                "not the ADX local maximum.\n\n"
                "timeframe — ADX/DMI series (MVP: base only).\n"
                "adx_period — Wilder ADX/DMI period.\n"
                "min_adx_peak — minimum ADX on the strength confirmation bar.\n"
                "peak_lookback_bars — how far back to search for that bar.\n"
                "max_bars_since_peak — episode expires after this many bars since peak.\n"
                "min_current_adx — floor for current ADX (may be below peak after fade).\n"
                "require_di_alignment_on_peak — peak counts only when DI favors the side.\n"
                "block_on_opposite_di_flip — block when opposite DI dominates.\n"
                "opposite_di_margin — minimum opposite-DI lead for a flip block."
            ),
            list_slot=True,
            supports_context_consumption=True,
            context_consumption_policies=_BLOCKER_CONTEXT_POLICIES,
            params_schema={
                "timeframe": _tf_param("ADX/DMI timeframe", default="base"),
                "adx_period": _int_param("ADX period", default=14),
                "min_adx_peak": _num_param("Min ADX at strength confirmation", default=25.0),
                "peak_lookback_bars": _int_param("Peak lookback bars", default=60),
                "max_bars_since_peak": _int_param("Max bars since peak", default=40),
                "min_current_adx": _num_param("Min current ADX", default=12.0),
                "opposite_di_margin": _num_param("Opposite DI margin", default=5.0),
                "require_di_alignment_on_peak": _bool_param(
                    "Require DI alignment at confirmation", default=True
                ),
                "block_on_opposite_di_flip": _bool_param("Block on opposite DI flip", default=True),
            },
        ),
        ComponentSchema(
            component_id="no_risk_filter",
            role="risk",
            label="No risk filter",
        ),
        ComponentSchema(
            component_id="no_signal_exit",
            role="exits",
            label="No signal exit",
            list_slot=True,
        ),
        ComponentSchema(
            component_id="rsi_signal_exit",
            role="exits",
            allowed_roles=[
                "exit_policy.signal_exit",
                "exit_management.runtime_exit",
            ],
            label="RSI signal exit",
            list_slot=True,
            params_schema={
                "rsi.timeframe": _tf_param("RSI timeframe", default="5m"),
                "rsi.period": _int_param("RSI period", default=14),
                "long_exit_above": _num_param("Long exit above", default=70.0),
                "short_exit_below": _num_param("Short exit below", default=30.0),
            },
        ),
        ComponentSchema(
            component_id="ema_close_loss_exit",
            role="exits",
            label="EMA close loss (trend)",
            list_slot=True,
            params_schema={
                "ema.timeframe": _tf_param("EMA timeframe", default="base"),
                "ema.period": _int_param("EMA period", default=200),
                "confirm_bars": _int_param("Confirm bars (base)", default=1),
            },
        ),
        ComponentSchema(
            component_id="ema_cross_loss_exit",
            role="exits",
            allowed_roles=[
                "exit_policy.signal_exit",
                "exit_management.runtime_exit",
            ],
            label="EMA cross loss (trend)",
            list_slot=True,
            params_schema={
                "fast_ema.timeframe": _tf_param("Fast EMA timeframe", default="base"),
                "fast_ema.period": _int_param("Fast EMA period", default=100),
                "slow_ema.timeframe": _tf_param("Slow EMA timeframe", default="base"),
                "slow_ema.period": _int_param("Slow EMA period", default=200),
                "confirm_bars": _int_param("Confirm bars (base)", default=1),
            },
        ),
        ComponentSchema(
            component_id="atr_stop_loss",
            role="exits",
            allowed_roles=["exit_policy.stop_loss"],
            label="ATR stop loss",
            list_slot=True,
            params_schema={
                "distance.timeframe": _tf_param("ATR timeframe", default="5m"),
                "distance.period": _int_param("ATR period", default=14),
                "distance.multiplier": _num_param("ATR multiplier", default=2.0),
            },
        ),
        ComponentSchema(
            component_id="atr_take_profit",
            role="exits",
            allowed_roles=["exit_policy.take_profit"],
            label="ATR take profit",
            list_slot=True,
            params_schema={
                "distance.timeframe": _tf_param("ATR timeframe", default="base"),
                "distance.period": _int_param("ATR period", default=14),
                "distance.multiplier": _num_param("ATR multiplier", default=4.0),
            },
        ),
        ComponentSchema(
            component_id="constant_usd_stop_loss",
            role="exits",
            label="Constant USD stop loss",
            list_slot=True,
            params_schema={
                "usd_distance": _num_param("USD distance", default=100.0),
            },
        ),
        ComponentSchema(
            component_id="constant_usd_take_profit",
            role="exits",
            label="Constant USD take profit",
            list_slot=True,
            params_schema={
                "usd_distance": _num_param("USD distance", default=200.0),
            },
        ),
        ComponentSchema(
            component_id="phase_runtime_exit",
            role="exit_management",
            allowed_roles=["exit_management.runtime_exit"],
            label="Phase runtime exit (market close)",
            params_schema={
                "exit_price": ParamFieldSchema(
                    type="string",
                    label="exit_price",
                    enum=["close"],
                    default="close",
                ),
            },
        ),
        # break_even_stop removed from authoring catalog (Slice 9): legacy managed combiner only.
        # Runtime/parser compatibility remains in research layer for existing artifacts.
    ]

    context_providers = [
        ContextProviderSchema(
            component_id="htf_context",
            label="HTF EMA stack context",
            description="Higher-timeframe EMA stack state (up / down / neutral).",
            params_schema={
                "timeframe": _tf_param("timeframe", default="4h"),
                "source": ParamFieldSchema(
                    type="string",
                    label="source",
                    enum=["close"],
                    default="close",
                ),
                "fast_period": _int_param("fast_period", default=100),
                "anchor_period": _int_param("anchor_period", default=200),
                "slow_period": _int_param("slow_period", default=1000),
            },
        ),
    ]

    context_consumption_roles = [
        ContextConsumptionRoleSchema(
            role="exit_policy",
            label="Exit policy",
            policies=[
                ContextConsumptionPolicySchema(
                    policy_id="exit_profile_by_htf_state",
                    label="Profile by HTF state",
                ),
            ],
        ),
        ContextConsumptionRoleSchema(
            role="blockers",
            label="Blockers",
            policies=[
                ContextConsumptionPolicySchema(
                    policy_id="htf_regime_gate",
                    label="HTF regime gate",
                ),
            ],
        ),
        ContextConsumptionRoleSchema(
            role="setup",
            label="Setup",
            policies=[
                ContextConsumptionPolicySchema(
                    policy_id="htf_regime_gate",
                    label="HTF regime gate",
                ),
            ],
        ),
    ]

    return ComponentCatalog(
        family=family,
        schema_version=1,
        sections=sections,
        components=components,
        context_providers=context_providers,
        context_consumption_roles=context_consumption_roles,
    )
