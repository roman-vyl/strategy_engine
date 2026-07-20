"""Validation adapter for BBB Workbench authoring instances."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.contracts import StrategySpecEnvelope

_EXIT_KIND = {
    "no_signal_exit": "signal",
    "rsi_signal_exit": "signal",
    "ema_close_loss_exit": "signal",
    "ema_cross_loss_exit": "signal",
    "atr_stop_loss": "stop_loss",
    "constant_usd_stop_loss": "stop_loss",
    "atr_take_profit": "take_profit",
    "constant_usd_take_profit": "take_profit",
}


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidRequestError(f"{path} must be an object")
    return value


def authoring_instance_to_envelope(instance: Mapping[str, Any]) -> StrategySpecEnvelope:
    instance_id = str(instance.get("instance_id", "")).strip()
    if not instance_id:
        raise InvalidRequestError("instance_id must be a non-empty string")
    market = _mapping(instance.get("market"), "market")
    strategy = _mapping(instance.get("strategy"), "strategy")
    stack = _mapping(strategy.get("anchor_stack"), "strategy.anchor_stack")
    source = str(stack.get("source", "close"))
    timeframe = str(stack.get("timeframe", "base"))

    def ema(role: str) -> dict[str, Any]:
        value = stack.get(role)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise InvalidRequestError(f"strategy.anchor_stack.{role} must be > 0")
        return {"source": source, "timeframe": timeframe, "period": value}

    blockers = []
    raw_blockers = strategy.get("blockers", [])
    if not isinstance(raw_blockers, list):
        raise InvalidRequestError("strategy.blockers must be an array")
    for index, raw in enumerate(raw_blockers):
        item = dict(_mapping(raw, f"strategy.blockers[{index}]"))
        cid = str(item.get("component_id", ""))
        blocker_out: dict[str, Any] = {
            "instance_id": str(item.get("instance_id", cid)),
            "component_id": cid,
        }
        if "context_consumption" in item:
            blocker_out["context_consumption"] = item["context_consumption"]
        if cid == "rsi_lookback_extreme_blocker":
            rsi = item.get("rsi") or {
                "timeframe": item.get("timeframe", "base"),
                "period": item.get("period", 14),
            }
            blocker_out.update(
                {
                    "rsi": rsi,
                    "lookback": item.get("lookback", 20),
                    "long_block_above": item.get("long_block_above"),
                    "short_block_below": item.get("short_block_below"),
                }
            )
        elif cid == "trend_strength_episode_blocker":
            params = {
                k: v
                for k, v in item.items()
                if k not in {"instance_id", "component_id", "context_consumption"}
            }
            blocker_out["trend_strength"] = params
        blockers.append(blocker_out)
    setups = []
    raw_setups = strategy.get("setups", [])
    if not isinstance(raw_setups, list):
        raise InvalidRequestError("strategy.setups must be an array")
    for index, raw in enumerate(raw_setups):
        item = dict(_mapping(raw, f"strategy.setups[{index}]"))
        setup_out: dict[str, Any] = {
            "instance_id": str(item.pop("instance_id", "")),
            "component_id": str(item.pop("component_id", "")),
        }
        if "context_consumption" in item:
            setup_out["context_consumption"] = item.pop("context_consumption")
        setup_out["params"] = item
        setups.append(setup_out)
    direction = _mapping(strategy.get("direction"), "strategy.direction")
    trigger = dict(_mapping(strategy.get("trigger"), "strategy.trigger"))
    risk = _mapping(strategy.get("risk"), "strategy.risk")
    tm = dict(_mapping(strategy.get("trade_management"), "strategy.trade_management"))
    exit_policy = dict(_mapping(tm.get("exit_policy"), "strategy.trade_management.exit_policy"))

    def exits_group(group: Any, path: str) -> dict[str, Any]:
        payload = dict(_mapping(group, path))
        raw_exits = payload.get("exits", [])
        if not isinstance(raw_exits, list):
            raise InvalidRequestError(f"{path}.exits must be an array")
        converted = []
        for raw in raw_exits:
            rule = dict(_mapping(raw, f"{path}.exits[]"))
            cid = str(rule.get("component_id", ""))
            rule.setdefault("exit_kind", _EXIT_KIND.get(cid, "signal"))
            converted.append(rule)
        payload["exits"] = converted
        return payload

    exit_policy["always_on"] = exits_group(
        exit_policy.get("always_on", {}), "exit_policy.always_on"
    )
    profiles = dict(_mapping(exit_policy.get("profiles"), "exit_policy.profiles"))
    for name in ("aligned", "countertrend", "neutral"):
        profiles[name] = exits_group(profiles.get(name, {}), f"exit_policy.profiles.{name}")
    exit_policy["profiles"] = profiles
    tm["exit_policy"] = exit_policy
    raw_trade_sides = strategy.get("trade_sides", [])
    if isinstance(raw_trade_sides, Mapping):
        trade_sides = [side for side in ("long", "short") if raw_trade_sides.get(side) is True]
    elif isinstance(raw_trade_sides, list):
        trade_sides = list(raw_trade_sides)
    else:
        raise InvalidRequestError("strategy.trade_sides must be an array or object")

    raw_spec = {
        "variant": instance.get("variant"),
        "symbol": str(market.get("symbol", "")).upper(),
        "base_timeframe": str(market.get("base_timeframe", "")),
        "anchor_stack": {"fast": ema("fast"), "anchor": ema("anchor"), "slow": ema("slow")},
        "components": {
            "direction": str(direction.get("component_id", "")),
            "blockers": blockers,
            "trigger": trigger,
            "risk": str(risk.get("component_id", "")),
        },
        "trade_sides": trade_sides,
        "setups": setups,
        "contexts": strategy.get("contexts", {}),
        "trade_management": tm,
    }
    return StrategySpecEnvelope("ema_pullback", "1", instance_id, raw_spec, "bbb_v1")
