"""ema_pullback-owned strategy-semantic live history requirements.

Pure computation only: reads the canonical raw_spec mapping (same shape
build_feature_plan_from_canonical_spec consumes) and returns HistoryRequirement
values on the base FeatureFrame axis. No MDS, no pandas, no HTTP.

Axis rule (design.md Decision 4b / proposal.md): every resolved bar count here
is on the base FeatureFrame axis -- the axis the existing ema_pullback
evaluator actually iterates over -- never the timeframe axis of whichever
indicator feeds a component. A 1h RSI feeding a blocker with lookback=20 still
means 20 *base* bars for the blocker, not 20 * 1h.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.live_calculation.contracts import HistoryRequirement


# ema_bounce_counter_setup's completed_count trend-episode state lives from
# the start of a trend_active episode until the episode breaks -- there is
# no fixed lookback bound in the abstract (design.md Decision 11/4b). V1
# does NOT introduce persistent/incremental bounce state (explicit
# non-goal); instead this is an ordinary, conditional strategy-semantic
# HistoryRequirement, sized by an empirical V1 policy keyed SOLELY on the
# anchor EMA period -- not a mathematical upper bound (design.md
# Decision 12; see that section for the empirical basis and the real-history
# parity outcome per tier).
@dataclass(frozen=True, slots=True)
class _BounceHistoryTier:
    max_anchor_period: int
    history_bars: int


_BOUNCE_HISTORY_TIERS: tuple[_BounceHistoryTier, ...] = (
    _BounceHistoryTier(max_anchor_period=200, history_bars=2500),
    _BounceHistoryTier(max_anchor_period=500, history_bars=6000),
    _BounceHistoryTier(max_anchor_period=1000, history_bars=15000),
)

_BASE = "base"

_ZERO_LOOKBACK_BLOCKERS = {"no_blockers", "counter_candle_blocker"}
_ZERO_LOOKBACK_TRIGGERS = {"touch_anchor"}
_ZERO_LOOKBACK_EXITS = {
    "no_signal_exit",
    "rsi_signal_exit",
    "atr_stop_loss",
    "atr_take_profit",
    "constant_usd_stop_loss",
    "constant_usd_take_profit",
}
_ZERO_LOOKBACK_PHASE_RULE_COMPONENTS = {
    "mfe_atr",
    "adx_di_threshold",
    "bars_in_trade",
    "mfe_pct",
}
_ZERO_LOOKBACK_STOP_COMPONENTS = {"lock_profit_stop", "break_even_stop"}
# phase_runtime_exit is dispatched in managed.py's runtime-exit condition
# function (component_id == "phase_runtime_exit": checks params.exit_price
# == "close", a current-bar check), not in the phase_rules condition
# dispatch -- it belongs here, not in _ZERO_LOOKBACK_PHASE_RULE_COMPONENTS.
_ZERO_LOOKBACK_RUNTIME_EXIT_COMPONENTS = {
    "phase_runtime_exit",
    "rsi_signal_exit",
    "ema_cross_loss_exit",
}


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise InvalidRequestError(f"{path} must be an object")
    return value


def _sequence(value: Any, path: str) -> Sequence[Any]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise InvalidRequestError(f"{path} must be a list")
    return tuple(value)


def _zero(reason: str) -> HistoryRequirement:
    return HistoryRequirement(timeframe=_BASE, bars=0, reason=reason)


class EmaPullbackLiveCalculationRequirements:
    """Derive strategy-semantic HistoryRequirements for every live-supported
    ema_pullback context, blocker, setup, trigger, risk/entry, and exit
    component. Unrecognized component ids fail closed (raise) rather than
    silently contributing zero required history.

    ema_bounce_counter_setup's history requirement is classified solely by
    the anchor EMA period (root.anchor_stack.anchor.period), via
    _BOUNCE_HISTORY_TIERS -- fast/slow EMA periods do NOT participate in
    tier selection. This is a deliberate V1 simplification, not an
    oversight: a tier keyed on the exact (fast, anchor, slow) tuple would be
    brittle (a spec with anchor=199 instead of the measured anchor=200
    would become "unknown" for no principled reason), while the anchor
    period alone is a stable classifier of the setup's scale -- fast/slow
    still fully participate in the real ema_pullback EMA stack and
    trend_active computation (untouched), just not in this tier lookup."""

    def execute(self, raw_spec: Mapping[str, Any]) -> tuple[HistoryRequirement, ...]:
        root = _mapping(raw_spec, "raw_spec")
        requirements: list[HistoryRequirement] = []
        requirements.extend(self._contexts(root))
        requirements.extend(self._direction(root))
        requirements.extend(self._setups(root))
        requirements.extend(self._blockers(root))
        requirements.extend(self._trigger(root))
        requirements.extend(self._risk(root))
        requirements.extend(self._exits(root))
        requirements.extend(self._exit_management(root))
        return tuple(requirements)

    # -- contexts --------------------------------------------------------

    def _contexts(self, root: Mapping[str, Any]) -> list[HistoryRequirement]:
        out: list[HistoryRequirement] = []
        contexts_raw = root.get("contexts", {})
        contexts = _mapping(contexts_raw, "contexts") if contexts_raw is not None else {}
        for context_ref, provider_raw in contexts.items():
            provider = _mapping(provider_raw, f"contexts.{context_ref}")
            component_id = str(provider.get("component_id", ""))
            if component_id != "htf_context":
                raise InvalidRequestError(
                    "no registered live history policy for context provider",
                    component_id=component_id,
                )
            # htf_context only exposes already-computed HTF fast/anchor/slow
            # EMA values for context-gate comparisons at the current bar; the
            # EMA warm-up itself is already counted via indicator_warmup_span.
            out.append(
                _zero(
                    f"contexts.{context_ref} htf_context: current-bar only, "
                    "indicator warm-up already counted separately"
                )
            )
        return out

    # -- direction ---------------------------------------------------------

    def _direction(self, root: Mapping[str, Any]) -> list[HistoryRequirement]:
        components = _mapping(root.get("components"), "components")
        component_id = str(components.get("direction", "ema_anchor_stack_trend"))
        if component_id != "ema_anchor_stack_trend":
            raise InvalidRequestError(
                "no registered live history policy for direction component",
                component_id=component_id,
            )
        return [
            _zero(
                "components.direction ema_anchor_stack_trend: current-bar "
                "fast/anchor/slow comparison, indicator warm-up already counted separately"
            )
        ]

    # -- risk ---------------------------------------------------------

    def _risk(self, root: Mapping[str, Any]) -> list[HistoryRequirement]:
        components = _mapping(root.get("components"), "components")
        raw = components.get("risk", "no_risk_filter")
        if isinstance(raw, str):
            component_id = raw
        else:
            payload = _mapping(raw, "components.risk")
            component_id = str(payload.get("component_id", "no_risk_filter"))
        if component_id != "no_risk_filter":
            raise InvalidRequestError(
                "no registered live history policy for risk component",
                component_id=component_id,
            )
        return [_zero("components.risk no_risk_filter: always allows, no lookback")]

    # -- setups --------------------------------------------------------

    def _setups(self, root: Mapping[str, Any]) -> list[HistoryRequirement]:
        out: list[HistoryRequirement] = []
        for index, setup_raw in enumerate(_sequence(root.get("setups"), "setups")):
            setup = _mapping(setup_raw, f"setups[{index}]")
            params = _mapping(setup.get("params", {}), f"setups[{index}].params")
            component_id = str(setup.get("component_id", ""))
            if component_id == "untouched_anchor_setup":
                lookback = int(params.get("lookback", 50))
                active_bars = int(params.get("active_bars", 3))
                # touch_active at target can be driven by a first_touch up to
                # (active_bars - 1) bars before target, and that first_touch's
                # own untouched_prior needs `lookback` bars of touch history
                # before *it* -- so the earliest touch data needed precedes
                # target by lookback + active_bars - 1, not just lookback.
                bars = lookback + active_bars - 1
                out.append(
                    HistoryRequirement(
                        timeframe=_BASE,
                        bars=bars,
                        reason=(
                            f"setups[{index}] untouched_anchor_setup lookback={lookback} "
                            f"+ active_bars={active_bars} - 1 (touch_active can be driven by "
                            "a first_touch up to active_bars-1 bars before target, which "
                            "itself needs lookback bars of touch history before it)"
                        ),
                    )
                )
            elif component_id == "anchor_stack_width_setup":
                lookback = int(params.get("width_lookback_bars", 80))
                out.append(
                    HistoryRequirement(
                        timeframe=_BASE,
                        bars=lookback,
                        reason=(
                            f"setups[{index}] anchor_stack_width_setup "
                            f"width_lookback_bars={lookback}"
                        ),
                    )
                )
            elif component_id == "ema_bounce_counter_setup":
                anchor_period = self._anchor_ema_period(root, index)
                tier = self._select_bounce_tier(anchor_period, index)
                out.append(
                    HistoryRequirement(
                        timeframe=_BASE,
                        bars=tier.history_bars,
                        reason=(
                            f"ema_bounce_counter_setup: anchor_period={anchor_period}, "
                            f"selected V1 empirical history tier={tier.history_bars} base bars"
                        ),
                    )
                )
            else:
                raise InvalidRequestError(
                    "no registered live history policy for setup component",
                    component_id=component_id,
                )
        return out

    def _anchor_ema_period(self, root: Mapping[str, Any], index: int) -> int:
        """The anchor EMA period ema_bounce_counter_setup's trend_active
        computation actually uses is the spec-global anchor_stack.anchor
        period (feature_plan.py wires ema_bounce_counter_setup's fast/
        anchor/slow columns to that same top-level anchor_stack, never to a
        per-setup override) -- not something carried on the setup item
        itself."""

        anchor_stack = _mapping(root.get("anchor_stack"), "anchor_stack")
        anchor = _mapping(anchor_stack.get("anchor"), "anchor_stack.anchor")
        period = anchor.get("period")
        if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
            raise InvalidRequestError(
                f"setups[{index}] ema_bounce_counter_setup requires a positive integer "
                "anchor_stack.anchor.period to select its live-history tier",
                anchor_period=period,
            )
        return period

    def _select_bounce_tier(self, anchor_period: int, index: int) -> _BounceHistoryTier:
        for tier in _BOUNCE_HISTORY_TIERS:
            if anchor_period <= tier.max_anchor_period:
                return tier
        raise InvalidRequestError(
            "ema_bounce_counter_setup anchor EMA period exceeds calibrated V1 "
            "live-history envelope",
            setup_index=index,
            anchor_period=anchor_period,
            calibrated_max_anchor_period=_BOUNCE_HISTORY_TIERS[-1].max_anchor_period,
        )

    # -- blockers --------------------------------------------------------

    def _blockers(self, root: Mapping[str, Any]) -> list[HistoryRequirement]:
        out: list[HistoryRequirement] = []
        components = _mapping(root.get("components"), "components")
        blockers = _sequence(components.get("blockers"), "components.blockers")
        for index, blocker_raw in enumerate(blockers):
            item = _mapping(blocker_raw, f"components.blockers[{index}]")
            component_id = str(item.get("component_id", ""))
            if component_id in _ZERO_LOOKBACK_BLOCKERS:
                out.append(
                    _zero(f"components.blockers[{index}] {component_id}: current-bar only")
                )
            elif component_id == "rsi_lookback_extreme_blocker":
                lookback = int(item.get("lookback", 20))
                out.append(
                    HistoryRequirement(
                        timeframe=_BASE,
                        bars=lookback,
                        reason=(
                            f"components.blockers[{index}] rsi_lookback_extreme_blocker "
                            f"lookback={lookback}"
                        ),
                    )
                )
            elif component_id == "trend_strength_episode_blocker":
                trend = _mapping(
                    item.get("trend_strength"), f"components.blockers[{index}].trend_strength"
                )
                lookback = int(trend.get("peak_lookback_bars", 60))
                out.append(
                    HistoryRequirement(
                        timeframe=_BASE,
                        bars=lookback,
                        reason=(
                            f"components.blockers[{index}] trend_strength_episode_blocker "
                            f"peak_lookback_bars={lookback}"
                        ),
                    )
                )
            else:
                raise InvalidRequestError(
                    "no registered live history policy for blocker component",
                    component_id=component_id,
                )
        return out

    # -- trigger --------------------------------------------------------

    def _trigger(self, root: Mapping[str, Any]) -> list[HistoryRequirement]:
        components = _mapping(root.get("components"), "components")
        raw = components.get("trigger", {"component_id": "reclaim_anchor", "lookback": 1})
        # triggers._trigger_rule accepts a bare string shorthand
        # (trigger: "touch_anchor") as well as the object form -- match that
        # here so a spec the real evaluator accepts doesn't fail closed here.
        if isinstance(raw, str):
            rule: Mapping[str, Any] = {"component_id": raw}
        else:
            rule = _mapping(raw, "components.trigger")
        component_id = str(rule.get("component_id", "reclaim_anchor"))
        if component_id in _ZERO_LOOKBACK_TRIGGERS:
            return [_zero(f"components.trigger {component_id}: current-bar only")]
        if component_id in {"reclaim_anchor", "strong_reclaim_anchor"}:
            lookback = int(rule.get("lookback", 1))
            return [
                HistoryRequirement(
                    timeframe=_BASE,
                    bars=lookback,
                    reason=f"components.trigger {component_id} lookback={lookback}",
                )
            ]
        raise InvalidRequestError(
            "no registered live history policy for trigger component",
            component_id=component_id,
        )

    # -- exits (always_on + profiles) ------------------------------------

    def _all_exit_rules(self, root: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        trade_management = _mapping(root.get("trade_management"), "trade_management")
        exit_policy = _mapping(
            trade_management.get("exit_policy"), "trade_management.exit_policy"
        )
        rules: list[Mapping[str, Any]] = []
        always_on = _mapping(exit_policy.get("always_on"), "exit_policy.always_on")
        rules.extend(
            _mapping(item, "exit") for item in _sequence(always_on.get("exits"), "always_on.exits")
        )
        profiles = _mapping(exit_policy.get("profiles"), "exit_policy.profiles")
        for profile_name in ("aligned", "countertrend", "neutral"):
            profile = _mapping(profiles.get(profile_name), f"profiles.{profile_name}")
            rules.extend(
                _mapping(item, f"profiles.{profile_name}.exits[]")
                for item in _sequence(profile.get("exits"), f"profiles.{profile_name}.exits")
            )
        return rules

    def _exits(self, root: Mapping[str, Any]) -> list[HistoryRequirement]:
        out: list[HistoryRequirement] = []
        for index, rule in enumerate(self._all_exit_rules(root)):
            component_id = str(rule.get("component_id", ""))
            if component_id in _ZERO_LOOKBACK_EXITS:
                out.append(_zero(f"exits[{index}] {component_id}: no extra semantic lookback"))
            elif component_id == "ema_close_loss_exit":
                confirm_bars = int(rule.get("confirm_bars", 1))
                out.append(
                    HistoryRequirement(
                        timeframe=_BASE,
                        bars=confirm_bars,
                        reason=f"exits[{index}] ema_close_loss_exit confirm_bars={confirm_bars}",
                    )
                )
            elif component_id == "ema_cross_loss_exit":
                confirm_bars = int(rule.get("confirm_bars", 1))
                # +1 for shift(1) previous-EMA comparison inside the cross check.
                out.append(
                    HistoryRequirement(
                        timeframe=_BASE,
                        bars=confirm_bars + 1,
                        reason=(
                            f"exits[{index}] ema_cross_loss_exit confirm_bars={confirm_bars} "
                            "+ 1 for shift(1) previous-EMA dependency"
                        ),
                    )
                )
            else:
                raise InvalidRequestError(
                    "no registered live history policy for exit component",
                    component_id=component_id,
                )
        return out

    # -- exit_management (phase_rules / stop_management / runtime_exits) --

    def _exit_management(self, root: Mapping[str, Any]) -> list[HistoryRequirement]:
        out: list[HistoryRequirement] = []
        trade_management = _mapping(root.get("trade_management"), "trade_management")
        exit_management = _mapping(
            trade_management.get("exit_management", {}), "trade_management.exit_management"
        )

        for index, phase_rule_raw in enumerate(
            _sequence(exit_management.get("phase_rules"), "exit_management.phase_rules")
        ):
            phase_rule = _mapping(phase_rule_raw, f"phase_rules[{index}]")
            condition = _mapping(phase_rule.get("condition"), f"phase_rules[{index}].condition")
            component_id = str(condition.get("component_id", ""))
            if component_id in _ZERO_LOOKBACK_PHASE_RULE_COMPONENTS:
                out.append(
                    _zero(
                        f"phase_rules[{index}] {component_id}: current-bar-relative-to-entry "
                        "check, indicator warm-up already counted separately"
                    )
                )
            else:
                raise InvalidRequestError(
                    "no registered live history policy for phase_rule component",
                    component_id=component_id,
                )

        for index, stop_raw in enumerate(
            _sequence(exit_management.get("stop_management"), "exit_management.stop_management")
        ):
            stop = _mapping(stop_raw, f"stop_management[{index}]")
            component_id = str(stop.get("component_id", ""))
            if component_id in _ZERO_LOOKBACK_STOP_COMPONENTS:
                out.append(
                    _zero(
                        f"stop_management[{index}] {component_id}: "
                        "current-bar-relative-to-entry check"
                    )
                )
            else:
                raise InvalidRequestError(
                    "no registered live history policy for stop_management component",
                    component_id=component_id,
                )

        for index, runtime_raw in enumerate(
            _sequence(exit_management.get("runtime_exits"), "exit_management.runtime_exits")
        ):
            runtime = _mapping(runtime_raw, f"runtime_exits[{index}]")
            component_id = str(runtime.get("component_id", ""))
            if component_id in _ZERO_LOOKBACK_RUNTIME_EXIT_COMPONENTS:
                out.append(
                    _zero(
                        f"runtime_exits[{index}] {component_id}: indicator warm-up already "
                        "counted separately, no additional semantic lookback in the "
                        "runtime-exit variant"
                    )
                )
            else:
                raise InvalidRequestError(
                    "no registered live history policy for runtime_exit component",
                    component_id=component_id,
                )

        return out
