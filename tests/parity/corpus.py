"""Parity corpus: real batches (1.2), synthetic structural variety (1.3),
alias/collision probes (1.4).

Every case is one range-batch request (one shared market range, N variants)
over the committed MDS fixture. Real cases are read from `corpus/real_*.json`
(verbatim Research Service raw specs, see `build_real_corpus.py`); synthetic
and probe cases are built here so each variant's intent is documented next
to the spec that exercises it.

Default values referenced by the probes are the ones the current code
applies (checked against source at the time of writing):
- setups.py `_untouched_anchor`: lookback=50, active_bars=3
- setups.py `_anchor_stack_width` / feature_plan.py: min_current_width_atr=2.0,
  min_recent_width_atr=4.0, width_lookback_bars=80, atr_period=14,
  atr_timeframe="base"
- feature_plan.py `_ema`: source="close", timeframe="base"; exit distance
  period=14, timeframe="base"
- raw_spec_identity.py: trigger={"component_id": "reclaim_anchor",
  "lookback": 1}, risk="no_risk_filter", direction="ema_anchor_stack_trend",
  trade_sides=["long"]
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from parity.harness import CORPUS_DIR, Case

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LANE_FIXTURES = _REPO_ROOT / "scripts" / "fixtures"

Spec = dict[str, Any]


def _variant(variant_id: str, raw_spec: Spec, strategy_id: str = "ema_pullback") -> dict[str, Any]:
    return {
        "variant_id": variant_id,
        "strategy": {"strategy_id": strategy_id, "raw_spec": raw_spec},
    }


def _ema(period: int, *, source: str = "close", timeframe: str = "base") -> dict[str, Any]:
    return {"period": period, "source": source, "timeframe": timeframe}


def _atr_exit(
    instance_id: str,
    kind: str,
    multiplier: Any,
    *,
    period: int = 48,
    timeframe: str = "base",
) -> dict[str, Any]:
    return {
        "component_id": "atr_stop_loss" if kind == "stop_loss" else "atr_take_profit",
        "distance": {"multiplier": multiplier, "period": period, "timeframe": timeframe},
        "exit_kind": kind,
        "instance_id": instance_id,
    }


def _width(instance_id: str = "width1", **overrides: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "atr_period": 48,
        "atr_timeframe": "base",
        "min_current_width_atr": 1,
        "min_recent_width_atr": 4.0,
        "width_lookback_bars": 80,
    }
    params.update(overrides)
    return {
        "component_id": "anchor_stack_width_setup",
        "instance_id": instance_id,
        "params": params,
    }


def _untouched(instance_id: str = "untouched1", **params: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {"active_bars": 3, "lookback": 70}
    merged.update(params)
    return {"component_id": "untouched_anchor_setup", "instance_id": instance_id, "params": merged}


def base_spec() -> Spec:
    """Same shape as the real 3D-grid Research Service specs."""

    return {
        "anchor_stack": {"anchor": _ema(200), "fast": _ema(100), "slow": _ema(500)},
        "components": {
            "blockers": [],
            "direction": "ema_anchor_stack_trend",
            "risk": "no_risk_filter",
            "trigger": {"component_id": "touch_anchor"},
        },
        "contexts": {},
        "setups": [_width(), _untouched()],
        "trade_management": {
            "exit_management": {},
            "exit_policy": {
                "always_on": {
                    "exits": [
                        _atr_exit("sl-measurement", "stop_loss", 3.0),
                        _atr_exit("tp-measurement", "take_profit", 6.0),
                    ]
                },
                "profiles": {
                    "aligned": {"exits": []},
                    "countertrend": {"exits": []},
                    "neutral": {"exits": []},
                },
            },
        },
        "trade_sides": ["long", "short"],
    }


def _with(spec: Spec, *path_and_value: Any) -> Spec:
    """Deep-copied spec with `spec[path...] = value` (path of keys/indices)."""

    *path, value = path_and_value
    result = copy.deepcopy(spec)
    target: Any = result
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return result


def _without(spec: Spec, *path: Any) -> Spec:
    result = copy.deepcopy(spec)
    target: Any = result
    for key in path[:-1]:
        target = target[key]
    del target[path[-1]]
    return result


def _exits(spec: Spec, always_on: list[Any], **profiles: list[Any]) -> Spec:
    result = copy.deepcopy(spec)
    policy = result["trade_management"]["exit_policy"]
    policy["always_on"]["exits"] = always_on
    for name, rules in profiles.items():
        policy["profiles"][name]["exits"] = rules
    return result


def _htf_context(timeframe: str = "1h", *, source: str = "close") -> dict[str, Any]:
    return {
        "component_id": "htf_context",
        "timeframe": timeframe,
        "source": source,
        "fast_period": 20,
        "anchor_period": 50,
        "slow_period": 200,
    }


def _gate(context_ref: str, *regimes: str) -> dict[str, Any]:
    return {
        "context_ref": context_ref,
        "policy": {"policy_id": "htf_regime_gate", "params": {"allowed_regimes": list(regimes)}},
    }


_RSI_BLOCKER = {
    "component_id": "rsi_lookback_extreme_blocker",
    "instance_id": "rsi-extreme",
    "rsi": {"timeframe": "base", "period": 14},
    "lookback": 20,
    "long_block_above": 75.0,
    "short_block_below": 25.0,
}
_TREND_BLOCKER = {
    "component_id": "trend_strength_episode_blocker",
    "instance_id": "trend-episode",
    "trend_strength": {"timeframe": "base", "adx_period": 14, "min_adx_peak": 25.0},
}
_COUNTER_BLOCKER = {"component_id": "counter_candle_blocker", "instance_id": "counter-candle"}


# -- 1.2 real ---------------------------------------------------------------------


def real_cases() -> list[Case]:
    cases = []
    for path in sorted(CORPUS_DIR.glob("real_*.json")):
        document = json.loads(path.read_text())
        cases.append(
            Case(
                name=document["case"],
                group="real",
                description=document["description"],
                provenance=document["provenance"],
                variants=document["variants"],
            )
        )
    return cases


# -- 1.3 synthetic structural variety ------------------------------------------------


def _synthetic(name: str, description: str, variants: list[dict[str, Any]]) -> Case:
    return Case(
        name=name,
        group="synthetic",
        description=description,
        provenance={"source": "tests/parity/corpus.py"},
        variants=variants,
    )


def synthetic_cases() -> list[Case]:
    base = base_spec()
    lane_a = json.loads((_LANE_FIXTURES / "lane_a_always_on_ema_pullback_spec.json").read_text())
    lane_b = json.loads(
        (_LANE_FIXTURES / "lane_b_profile_sensitive_ema_pullback_spec.json").read_text()
    )

    def stack(fast: int, anchor: int, slow: int) -> Spec:
        return _with(
            base, "anchor_stack", {"fast": _ema(fast), "anchor": _ema(anchor), "slow": _ema(slow)}
        )

    ema_periods = [
        _variant("stack-100-200-500", stack(100, 200, 500)),
        _variant("stack-50-200-500", stack(50, 200, 500)),
        _variant("stack-20-50-200", stack(20, 50, 200)),
        _variant("stack-9-21-55", stack(9, 21, 55)),
        _variant("stack-200-300-400", stack(200, 300, 400)),
    ]

    atr_config = [
        _variant("width-atr14-base", _with(base, "setups", 0, _width(atr_period=14))),
        _variant("width-atr48-base", base),
        _variant(
            "width-atr14-15m", _with(base, "setups", 0, _width(atr_period=14, atr_timeframe="15m"))
        ),
        _variant(
            "width-atr12-1h", _with(base, "setups", 0, _width(atr_period=12, atr_timeframe="1h"))
        ),
        _variant(
            "exit-atr14-mult2-4",
            _exits(
                base,
                [
                    _atr_exit("sl", "stop_loss", 2.0, period=14),
                    _atr_exit("tp", "take_profit", 4.0, period=14),
                ],
            ),
        ),
        _variant(
            "exit-atr48-15m",
            _exits(
                base,
                [
                    _atr_exit("sl", "stop_loss", 3.0, timeframe="15m"),
                    _atr_exit("tp", "take_profit", 6.0, timeframe="15m"),
                ],
            ),
        ),
        _variant(
            "exit-sl14-tp48",
            _exits(
                base,
                [
                    _atr_exit("sl", "stop_loss", 3.0, period=14),
                    _atr_exit("tp", "take_profit", 6.0, period=48),
                ],
            ),
        ),
    ]

    gated_setups = copy.deepcopy(base)
    gated_setups["contexts"] = {"htf": _htf_context("1h")}
    gated_setups["setups"][1]["context_consumption"] = _gate("htf", "aligned")
    profile_exits = _exits(
        _with(base, "contexts", {"htf": _htf_context("1h")}),
        [_atr_exit("sl-always", "stop_loss", 3.0)],
        aligned=[_atr_exit("tp-aligned", "take_profit", 9.0)],
        countertrend=[_atr_exit("tp-counter", "take_profit", 3.0)],
        neutral=[_atr_exit("tp-neutral", "take_profit", 6.0)],
    )
    profile_exits["trade_management"]["exit_policy"]["context_consumption"] = {
        "context_ref": "htf",
        "policy": {"policy_id": "exit_profile_by_htf_state"},
    }
    gated_blocker = _with(base, "contexts", {"htf": _htf_context("4h")})
    gated_blocker["components"]["blockers"] = [
        {**_COUNTER_BLOCKER, "context_consumption": _gate("htf", "aligned", "neutral")}
    ]
    context_structure = [
        _variant("lane-a-always-on", lane_a),
        _variant("lane-b-profile-sensitive", lane_b),
        _variant("setup-gated-by-1h-context", gated_setups),
        _variant("exit-profiles-by-1h-context", profile_exits),
        _variant("blocker-gated-by-4h-context", gated_blocker),
        _variant("context-declared-unused", _with(base, "contexts", {"htf": _htf_context("1h")})),
    ]

    bounce = {
        "component_id": "ema_bounce_counter_setup",
        "instance_id": "bounce1",
        "params": {"max_bounces": 2, "touch_lookback_bars": 20},
    }
    setup_trigger = [
        _variant("no-setups", _with(base, "setups", [])),
        _variant("bounce-only", _with(base, "setups", [bounce])),
        _variant("bounce-width-untouched", _with(base, "setups", [bounce, _width(), _untouched()])),
        _variant(
            "trigger-reclaim-lb1",
            _with(base, "components", "trigger", {"component_id": "reclaim_anchor", "lookback": 1}),
        ),
        _variant(
            "trigger-reclaim-lb3",
            _with(base, "components", "trigger", {"component_id": "reclaim_anchor", "lookback": 3}),
        ),
        _variant(
            "trigger-strong-reclaim-lb2",
            _with(
                base,
                "components",
                "trigger",
                {"component_id": "strong_reclaim_anchor", "lookback": 2},
            ),
        ),
    ]

    blockers = [
        _variant(
            "blocker-counter-candle", _with(base, "components", "blockers", [_COUNTER_BLOCKER])
        ),
        _variant("blocker-rsi-extreme", _with(base, "components", "blockers", [_RSI_BLOCKER])),
        _variant("blocker-trend-strength", _with(base, "components", "blockers", [_TREND_BLOCKER])),
        _variant(
            "blocker-all-three",
            _with(base, "components", "blockers", [_COUNTER_BLOCKER, _RSI_BLOCKER, _TREND_BLOCKER]),
        ),
        _variant(
            "blocker-explicit-none",
            _with(
                base,
                "components",
                "blockers",
                [{"component_id": "no_blockers", "instance_id": "none"}],
            ),
        ),
    ]

    sl = _atr_exit("sl", "stop_loss", 3.0)
    tp = _atr_exit("tp", "take_profit", 6.0)
    rsi_exit = {
        "component_id": "rsi_signal_exit",
        "exit_kind": "signal",
        "instance_id": "rsi-exit",
        "rsi": {"timeframe": "base", "period": 14},
        "long_exit_above": 70.0,
        "short_exit_below": 30.0,
    }
    close_loss = {
        "component_id": "ema_close_loss_exit",
        "exit_kind": "signal",
        "instance_id": "close-loss",
        "ema": {"timeframe": "base", "period": 100},
        "confirm_bars": 2,
    }

    def cross(instance_id: str, confirm: int) -> dict[str, Any]:
        return {
            "component_id": "ema_cross_loss_exit",
            "exit_kind": "signal",
            "instance_id": instance_id,
            "fast_ema": {"timeframe": "base", "period": 20},
            "slow_ema": {"timeframe": "base", "period": 50},
            "confirm_bars": confirm,
        }

    usd_sl = {
        "component_id": "constant_usd_stop_loss",
        "exit_kind": "stop_loss",
        "instance_id": "usd-sl",
        "usd_distance": 500,
    }
    usd_tp = {
        "component_id": "constant_usd_take_profit",
        "exit_kind": "take_profit",
        "instance_id": "usd-tp",
        "usd_distance": "1250.5",
    }
    exit_structure = [
        _variant("exits-sl-tp-plus-rsi-signal", _exits(base, [sl, tp, rsi_exit])),
        _variant("exits-close-loss-confirm2", _exits(base, [sl, tp, close_loss])),
        _variant("exits-cross-confirm1", _exits(base, [sl, tp, cross("cross1", 1)])),
        _variant("exits-cross-confirm3", _exits(base, [sl, tp, cross("cross3", 3)])),
        _variant("exits-constant-usd", _exits(base, [usd_sl, usd_tp])),
        _variant("exits-min-of-atr-and-usd-stop", _exits(base, [sl, usd_sl, tp])),
        _variant("exits-stop-only", _exits(base, [sl])),
        _variant("exits-take-only", _exits(base, [tp])),
        _variant("exits-none", _exits(base, [])),
        _variant(
            "exits-profile-rules-without-context",
            _exits(base, [sl], aligned=[tp], neutral=[_atr_exit("tp-n", "take_profit", 4.0)]),
        ),
    ]

    failures = [
        _variant("ok-before", base),
        _variant(
            "fail-validate-unsupported-trigger",
            _with(base, "components", "trigger", {"component_id": "no_such_trigger"}),
        ),
        _variant(
            "fail-setups-nonpositive-width",
            _with(base, "setups", 0, _width(min_current_width_atr=-1)),
        ),
        _variant("ok-between", _with(base, "setups", 1, _untouched(lookback=90))),
        _variant(
            "fail-exits-rsi-missing-threshold",
            _exits(base, [sl, tp, {k: v for k, v in rsi_exit.items() if k != "long_exit_above"}]),
        ),
        _variant(
            "fail-indicators-non-integral-timeframe",
            _exits(base, [_atr_exit("sl", "stop_loss", 3.0, timeframe="7m"), tp]),
        ),
        _variant(
            "fail-context-unknown-ref",
            _with(
                base,
                "setups",
                1,
                {**_untouched(), "context_consumption": _gate("missing", "aligned")},
            ),
        ),
        _variant("fail-unknown-strategy", base, strategy_id="no_such_strategy"),
        _variant("ok-after", base),
    ]

    heterogeneous = [
        ema_periods[3],
        failures[2],
        exit_structure[1],
        context_structure[1],
        blockers[3],
        setup_trigger[5],
        atr_config[3],
        _variant("dup-of-stack-9-21-55", ema_periods[3]["strategy"]["raw_spec"]),
        failures[4],
        ema_periods[0],
    ]

    return [
        _synthetic("synthetic_ema_periods", "EMA anchor-stack period variety.", ema_periods),
        _synthetic(
            "synthetic_atr_config", "ATR period/timeframe variety (setup and exits).", atr_config
        ),
        _synthetic(
            "synthetic_context_structure",
            "HTF contexts: setup/blocker gates, exit profile selection, unused context.",
            context_structure,
        ),
        _synthetic(
            "synthetic_setup_trigger_structure",
            "Setup composition (none/bounce/three) and trigger variety.",
            setup_trigger,
        ),
        _synthetic("synthetic_blockers", "Blocker variety.", blockers),
        _synthetic(
            "synthetic_exit_structure",
            "Signal exits, constant-USD, min-aggregation, stop-only/take-only/none, profiles.",
            exit_structure,
        ),
        _synthetic(
            "synthetic_failures_mixed",
            "Per-variant failures at different evaluation stages interleaved with successes "
            "(caught-per-variant category/message/position).",
            failures,
        ),
        _synthetic(
            "synthetic_heterogeneous_shuffled",
            "Fully heterogeneous batch in mixed order, incl. a duplicate spec and failures.",
            heterogeneous,
        ),
    ]


# -- 1.4 alias / collision probes ------------------------------------------------------


def _probe(name: str, description: str, variants: list[dict[str, Any]], **kwargs: Any) -> Case:
    return Case(
        name=name,
        group="probe",
        description=description,
        provenance={"source": "tests/parity/corpus.py"},
        variants=variants,
        **kwargs,
    )


def probe_cases() -> list[Case]:
    base = base_spec()
    width_only = _with(base, "setups", [_width()])
    untouched_only = _with(base, "setups", [_untouched()])

    def untouched_params(params: dict[str, Any]) -> Spec:
        return _with(
            base,
            "setups",
            1,
            {
                "component_id": "untouched_anchor_setup",
                "instance_id": "untouched1",
                "params": params,
            },
        )

    def width_params(params: dict[str, Any]) -> Spec:
        return _with(
            base,
            "setups",
            0,
            {"component_id": "anchor_stack_width_setup", "instance_id": "width1", "params": params},
        )

    default_setup_params = [
        _variant("untouched-lookback-omitted", untouched_params({"active_bars": 3})),
        _variant(
            "untouched-lookback-50-explicit", untouched_params({"active_bars": 3, "lookback": 50})
        ),
        _variant("untouched-lookback-49", untouched_params({"active_bars": 3, "lookback": 49})),
        _variant("untouched-active-bars-omitted", untouched_params({"lookback": 70})),
        _variant(
            "untouched-active-bars-3-explicit", untouched_params({"lookback": 70, "active_bars": 3})
        ),
        _variant(
            "untouched-params-omitted",
            _with(
                base,
                "setups",
                1,
                {"component_id": "untouched_anchor_setup", "instance_id": "untouched1"},
            ),
        ),
        _variant("width-minimal-params", width_params({"min_current_width_atr": 1})),
        _variant(
            "width-explicit-defaults",
            width_params(
                {
                    "min_current_width_atr": 1,
                    "atr_period": 14,
                    "atr_timeframe": "base",
                    "min_recent_width_atr": 4.0,
                    "width_lookback_bars": 80,
                }
            ),
        ),
        _variant("width-all-omitted", width_params({})),
        _variant("width-current-2.0-explicit", width_params({"min_current_width_atr": 2.0})),
    ]

    components = base["components"]
    no_trigger = _without(base, "components", "trigger")
    default_components = [
        _variant("trigger-omitted", no_trigger),
        _variant(
            "trigger-reclaim-explicit-lb1",
            _with(base, "components", "trigger", {"component_id": "reclaim_anchor", "lookback": 1}),
        ),
        _variant(
            "trigger-reclaim-lookback-omitted",
            _with(base, "components", "trigger", {"component_id": "reclaim_anchor"}),
        ),
        _variant("trigger-reclaim-string", _with(base, "components", "trigger", "reclaim_anchor")),
        _variant("trigger-touch-string", _with(base, "components", "trigger", "touch_anchor")),
        _variant("risk-omitted", _without(base, "components", "risk")),
        _variant(
            "risk-object", _with(base, "components", "risk", {"component_id": "no_risk_filter"})
        ),
        _variant("direction-omitted", _without(base, "components", "direction")),
        _variant(
            "blockers-omitted-rejected",
            _with(base, "components", {k: v for k, v in components.items() if k != "blockers"}),
        ),
    ]

    stack_defaults = copy.deepcopy(base)
    stack_defaults["anchor_stack"] = {
        "fast": {"period": 100},
        "anchor": {"period": 200},
        "slow": {"period": 500},
    }
    exit_period_omitted = _exits(
        base,
        [
            {**_atr_exit("sl", "stop_loss", 3.0), "distance": {"multiplier": 3.0}},
            _atr_exit("tp", "take_profit", 6.0, period=14),
        ],
    )
    default_indicator_fields = [
        _variant("ema-source-timeframe-explicit", base),
        _variant("ema-source-timeframe-omitted", stack_defaults),
        _variant(
            "exit-distance-period-timeframe-omitted",
            exit_period_omitted,
        ),
        _variant(
            "exit-distance-period-14-explicit",
            _exits(
                base,
                [
                    _atr_exit("sl", "stop_loss", 3.0, period=14),
                    _atr_exit("tp", "take_profit", 6.0, period=14),
                ],
            ),
        ),
    ]

    sides = [
        _variant("width-sides-omitted", _without(width_only, "trade_sides")),
        _variant("width-long", _with(width_only, "trade_sides", ["long"])),
        _variant(
            "width-long-mapping-form", _with(width_only, "trade_sides", {"enabled": ["long"]})
        ),
        _variant("width-short", _with(width_only, "trade_sides", ["short"])),
        _variant("width-long-short", width_only),
        _variant("width-short-long", _with(width_only, "trade_sides", ["short", "long"])),
        _variant("untouched-long", _with(untouched_only, "trade_sides", ["long"])),
        _variant("untouched-short", _with(untouched_only, "trade_sides", ["short"])),
        _variant("untouched-long-short", untouched_only),
    ]

    def tf_stack(timeframe: str) -> Spec:
        return _with(
            base,
            "anchor_stack",
            {
                "fast": _ema(100, timeframe=timeframe),
                "anchor": _ema(200, timeframe=timeframe),
                "slow": _ema(500, timeframe=timeframe),
            },
        )

    rsi_5m = {**_RSI_BLOCKER, "rsi": {"timeframe": "5m", "period": 14}}
    timeframe_alias = [
        _variant("stack-base", base),
        _variant("stack-5m-literal", tf_stack("5m")),
        _variant("stack-15m-non-equivalent", tf_stack("15m")),
        _variant("width-atr-base", base),
        _variant("width-atr-5m-literal", _with(base, "setups", 0, _width(atr_timeframe="5m"))),
        _variant(
            "exit-distance-5m-literal",
            _exits(
                base,
                [
                    _atr_exit("sl-measurement", "stop_loss", 3.0, timeframe="5m"),
                    _atr_exit("tp-measurement", "take_profit", 6.0, timeframe="5m"),
                ],
            ),
        ),
        _variant("rsi-blocker-base", _with(base, "components", "blockers", [_RSI_BLOCKER])),
        _variant("rsi-blocker-5m-literal", _with(base, "components", "blockers", [rsi_5m])),
        _variant(
            "context-5m-literal-gate",
            _with(
                _with(base, "contexts", {"htf": _htf_context("5m")}),
                "setups",
                1,
                {**_untouched(), "context_consumption": _gate("htf", "aligned", "neutral")},
            ),
        ),
    ]

    def anchor_source(source: str) -> Spec:
        return _with(base, "anchor_stack", "anchor", _ema(200, source=source))

    # Same timeframe/period as the anchor stack, different source: today's
    # feature-plan output_id ignores source, so these collide *within* one
    # spec (first-planned wins). The golden pins that current behaviour.
    context_open = _with(
        base,
        "contexts",
        {
            "htf": {
                "component_id": "htf_context",
                "timeframe": "base",
                "source": "open",
                "fast_period": 100,
                "anchor_period": 200,
                "slow_period": 500,
            }
        },
    )
    context_open["setups"][1]["context_consumption"] = _gate("htf", "aligned")
    exit_ema_open = _exits(
        base,
        [
            _atr_exit("sl-measurement", "stop_loss", 3.0),
            _atr_exit("tp-measurement", "take_profit", 6.0),
            {
                "component_id": "ema_close_loss_exit",
                "exit_kind": "signal",
                "instance_id": "close-loss-open-ema",
                "ema": {"timeframe": "base", "period": 200, "source": "open"},
                "confirm_bars": 1,
            },
        ],
    )
    source_distinct = [
        _variant("anchor-ema200-close", anchor_source("close")),
        _variant("anchor-ema200-open", anchor_source("open")),
        _variant("anchor-ema200-high", anchor_source("high")),
        _variant("anchor-ema200-close-again", anchor_source("close")),
        _variant("within-spec-context-open-vs-stack-close", context_open),
        _variant("within-spec-exit-ema-open-vs-anchor-close", exit_ema_open),
    ]

    sl_a = _atr_exit("sl-a", "stop_loss", 3.0)
    sl_b = _atr_exit("sl-b", "stop_loss", 3.0)
    tp_ = _atr_exit("tp", "take_profit", 6.0)
    rule_order = [
        _variant("exits-original-ids", base),
        _variant(
            "exits-renamed-ids",
            _exits(
                base,
                [_atr_exit("stop", "stop_loss", 3.0), _atr_exit("take", "take_profit", 6.0)],
            ),
        ),
        _variant("exits-tp-declared-first", _exits(base, [tp_, _atr_exit("sl", "stop_loss", 3.0)])),
        _variant("equal-sl-a-then-b", _exits(base, [sl_a, sl_b, tp_])),
        _variant("equal-sl-b-then-a", _exits(base, [sl_b, sl_a, tp_])),
        _variant(
            "equal-sl-always-on-and-neutral-profile",
            _exits(base, [sl_a, tp_], neutral=[sl_b]),
        ),
        _variant("setups-width-then-untouched", base),
        _variant("setups-untouched-then-width", _with(base, "setups", [_untouched(), _width()])),
        _variant(
            "setups-renamed-instance-ids",
            _with(base, "setups", [_width("w"), _untouched("u")]),
        ),
        _variant(
            "two-width-setups-distinct-ids",
            _with(base, "setups", [_width("w-a"), _width("w-b", atr_period=14), _untouched()]),
        ),
        _variant(
            "blockers-order-a",
            _with(base, "components", "blockers", [_COUNTER_BLOCKER, _RSI_BLOCKER]),
        ),
        _variant(
            "blockers-order-b",
            _with(base, "components", "blockers", [_RSI_BLOCKER, _COUNTER_BLOCKER]),
        ),
    ]

    # 6.75 / 6.750 / 6.7500000000000001 are identical after JSON parsing; the
    # string and int/float spellings are distinct raw-spec values (config_hash
    # differs) that may or may not normalize to the same computation.
    tp_texts = {
        "tp-6.75": '{"multiplier": 6.75, "period": 48, "timeframe": "base"}',
        "tp-6.750": '{"multiplier": 6.750, "period": 48, "timeframe": "base"}',
        "tp-6.7500000000000001": (
            '{"multiplier": 6.7500000000000001, "period": 48, "timeframe": "base"}'
        ),
        "tp-string-6.75": '{"multiplier": "6.75", "period": 48, "timeframe": "base"}',
        "tp-int-6": '{"multiplier": 6, "period": 48, "timeframe": "base"}',
        "tp-float-6.0": '{"multiplier": 6.0, "period": 48, "timeframe": "base"}',
    }
    float_normalization = [
        _variant(
            variant_id,
            _exits(
                base,
                [
                    _atr_exit("sl-measurement", "stop_loss", 3.0),
                    {**_atr_exit("tp-measurement", "take_profit", 0), "distance": json.loads(text)},
                ],
            ),
        )
        for variant_id, text in tp_texts.items()
    ] + [
        _variant("width-current-int-1", _with(base, "setups", 0, _width(min_current_width_atr=1))),
        _variant(
            "width-current-float-1.0", _with(base, "setups", 0, _width(min_current_width_atr=1.0))
        ),
        _variant("width-recent-int-4", _with(base, "setups", 0, _width(min_recent_width_atr=4))),
        _variant(
            "untouched-lookback-float-70.0", _with(base, "setups", 1, _untouched(lookback=70.0))
        ),
        _variant("untouched-lookback-int-70", base),
    ]

    real_3d = json.loads((CORPUS_DIR / "real_3d_grid_subset.json").read_text())["variants"]
    duplicate_spec = real_3d[0]["strategy"]["raw_spec"]
    duplicates_and_order = [
        _variant("dup-a", duplicate_spec),
        _variant("dup-b", duplicate_spec),
        *[real_3d[index] for index in (26, 13, 0, 7, 20)],
        _variant("dup-c", duplicate_spec),
    ]

    return [
        _probe(
            "probe_default_setup_params",
            "Missing-default vs explicit-default setup params (untouched lookback/active_bars; "
            "width atr/recent/lookback) plus near-miss controls.",
            default_setup_params,
        ),
        _probe(
            "probe_default_components",
            "Missing vs explicit trigger/risk/direction/blockers component defaults and "
            "string-vs-object component forms.",
            default_components,
        ),
        _probe(
            "probe_default_indicator_fields",
            "EMA source/timeframe omitted vs explicit; exit distance period/timeframe omitted "
            "vs explicit 14/base.",
            default_indicator_fields,
        ),
        _probe(
            "probe_side_only_when_read",
            "Trade-side sets/order/forms for a side-free component (width) and a side-reading "
            "one (untouched).",
            sides,
        ),
        _probe(
            "probe_timeframe_alias",
            "'base' vs literal base timeframe '5m' for stack EMAs, width ATR, exit ATR, RSI and "
            "context; '15m' as the non-equivalent control.",
            timeframe_alias,
        ),
        _probe(
            "probe_source_distinct_same_period",
            "close/open/high EMA(200) across candidates (must not collide) and within-spec "
            "output_id collisions (context/exit EMA with source=open).",
            source_distinct,
        ),
        _probe(
            "probe_rule_order_and_labels",
            "instance_id renames and declared-order swaps: exits (incl. equal-distance "
            "attribution tie-break), setups, blockers.",
            rule_order,
        ),
        _probe(
            "probe_float_normalization",
            "Numeric spelling of multipliers/thresholds/lookbacks (6.75 vs 6.750 vs '6.75', "
            "6 vs 6.0, 1 vs 1.0, 70 vs 70.0).",
            float_normalization,
        ),
        _probe(
            "probe_duplicates_and_order",
            "Duplicated identical specs and real 3D candidates in non-request order.",
            duplicates_and_order,
        ),
        _probe(
            "probe_market_acquisition_without_hash",
            "Same variants without expected_market_data_hash (GET /v1/candles path).",
            [real_3d[0], real_3d[13]],
            expected_market_data_hash=False,
        ),
        _probe(
            "probe_request_level_failure",
            "Duplicate variant_id: whole-request failure before streaming starts.",
            [_variant("same-id", base), _variant("same-id", base)],
        ),
    ]


def all_cases() -> list[Case]:
    cases = real_cases() + synthetic_cases() + probe_cases()
    names = [case.name for case in cases]
    assert len(names) == len(set(names)), "duplicate case name"
    return cases
