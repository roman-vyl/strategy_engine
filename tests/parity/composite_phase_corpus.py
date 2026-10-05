"""Composite phase condition specs shared by the composite tests and the
projection parity corpus (OpenSpec `composite-managed-phase-condition-v1`,
design D12)."""

from __future__ import annotations

import copy
from typing import Any

from parity.corpus import _htf_context, base_spec

Spec = dict[str, Any]


def _feature(kind: str, timeframe: str, period: int = 14) -> dict[str, Any]:
    return {"feature": {"kind": kind, "timeframe": timeframe, "params": {"period": period}}}


def _gt(kind: str, timeframe: str, value: float) -> dict[str, Any]:
    return {
        "kind": "compare",
        "left": _feature(kind, timeframe),
        "op": ">",
        "right": {"const": value},
    }


ADX5 = _gt("adx", "5m", 35)
ADX1H = _gt("adx", "1h", 25)
DI1H = {
    "kind": "compare",
    "left": _feature("di_plus", "1h"),
    "op": ">",
    "right": _feature("di_minus", "1h"),
    "short": {"left": _feature("di_minus", "1h"), "right": _feature("di_plus", "1h")},
}
STATE1H = {"kind": "state", "context_ref": "htf_1h", "in": ["aligned"]}
HELD_ADX1H = {"kind": "temporal", "mode": "held_for", "bars": 6, "of": _gt("adx", "1h", 20)}

MFE_ATR = {
    "component_id": "mfe_atr",
    "params": {"threshold": 3.0, "atr": {"timeframe": "base", "period": 14}},
}
MFE_PCT = {"component_id": "mfe_pct", "params": {"threshold": 0.01}}
BARS = {"component_id": "bars_in_trade", "params": {"threshold": 60}}
ADX_DI_1H = {
    "component_id": "adx_di_threshold",
    "params": {
        "timeframe": "1h",
        "period": 14,
        "adx_threshold": 25.0,
        "require_di_alignment": True,
    },
}

# entry-anchored-change-v1: a rise from the operand's value on the entry bar.
RISE_ADX1H = {
    "component_id": "change_since_entry",
    "params": {"operand": _feature("adx", "1h"), "op": ">=", "value": 2.0},
}
RISE_ADX5 = {
    "component_id": "change_since_entry",
    "params": {"operand": _feature("adx", "5m"), "op": ">=", "value": 5.0},
}


def _pred(child_id: str, predicate: dict[str, Any]) -> dict[str, Any]:
    return {"child_id": child_id, "predicate": copy.deepcopy(predicate)}


def _cond(child_id: str, condition: dict[str, Any]) -> dict[str, Any]:
    return {"child_id": child_id, "condition": copy.deepcopy(condition)}


def _composite(children: list[dict[str, Any]], paths: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "component_id": "composite_phase_condition",
        "params": {"children": children, "paths": paths},
    }


def owner_case() -> dict[str, Any]:
    """(ADX 5m > 35 OR (ADX 1h > 25 AND DI 1h)) AND MFE >= 3 ATR."""

    return _composite(
        [_pred("adx5", ADX5), _pred("adx1h", ADX1H), _pred("di1h", DI1H), _cond("mfe", MFE_ATR)],
        [
            {"path_id": "fast", "require": ["adx5", "mfe"]},
            {"path_id": "htf", "require": ["adx1h", "di1h", "mfe"]},
        ],
    )


def mixed_at_least() -> dict[str, Any]:
    return _composite(
        [_pred("adx5", ADX5), _pred("di1h", DI1H), _cond("pct", MFE_PCT), _cond("bars", BARS)],
        [
            {
                "path_id": "vote",
                "require": ["di1h"],
                "at_least": {"k": 2, "of": ["adx5", "pct", "bars"]},
            },
        ],
    )


def trade_only_at_least() -> dict[str, Any]:
    return _composite(
        [_cond("bars", BARS), _cond("pct", MFE_PCT), _cond("mfe", MFE_ATR)],
        [{"path_id": "trade", "at_least": {"k": 2, "of": ["bars", "pct", "mfe"]}}],
    )


def state_temporal() -> dict[str, Any]:
    return _composite(
        [_pred("state", STATE1H), _pred("held", HELD_ADX1H), _cond("adx_di", ADX_DI_1H)],
        [
            {"path_id": "regime", "require": ["state", "held"]},
            {"path_id": "atom", "require": ["adx_di"]},
        ],
    )


def entry_change_case() -> dict[str, Any]:
    """1h ADX up by 2 from its entry value AND DI 1h on the trade side."""

    return _composite(
        [_cond("rise", RISE_ADX1H), _pred("di1h", DI1H)],
        [{"path_id": "rise", "require": ["rise", "di1h"]}],
    )


def entry_change_at_least() -> dict[str, Any]:
    """2 of [5m ADX up by 5 from entry, MFE >= 1%, ADX 1h > 25]."""

    return _composite(
        [_cond("rise", RISE_ADX5), _cond("pct", MFE_PCT), _pred("adx1h", ADX1H)],
        [{"path_id": "vote", "at_least": {"k": 2, "of": ["rise", "pct", "adx1h"]}}],
    )


def _spec(*conditions: dict[str, Any], to_phases: tuple[str, ...] = ("proven",)) -> Spec:
    spec = copy.deepcopy(base_spec())
    spec["contexts"] = {"htf_1h": _htf_context("1h")}
    spec["trade_management"]["exit_management"] = {
        "mode": "managed",
        "phase_rules": [
            {
                "rule_id": f"rule-{index}",
                "to_phase": to_phase,
                "condition": copy.deepcopy(condition),
            }
            for index, (condition, to_phase) in enumerate(zip(conditions, to_phases, strict=True))
        ],
        "stop_management": [],
        "take_management": [],
        "runtime_exits": [],
    }
    return spec
