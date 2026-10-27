"""EMA slopes end to end (OpenSpec `ema-slope-window-change-v1`): the window_change operand,
parsing and placement, the three EMA values of vote variant 8 through the strategy pipeline on
the BTCUSDT.P 5m fixture against a loop over the EMA column, shared nodes and a spec without the
operand."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest
from parity.corpus import _variant, base_spec
from test_ema_pullback_predicates_a2 import _legs, _parse
from test_ema_pullback_stack_episode_e2e import _calls, _run

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.predicates import parse_predicate

Spec = dict[str, Any]

WINDOW = 12


def _ema(period: int) -> Spec:
    return {"kind": "ema", "source": "close", "params": {"period": period}}


def _wc(period: int, last_n: int, form: str) -> Spec:
    return {
        "window_change": {
            "episode": "trend",
            "of": _ema(period),
            "last_n": last_n,
            "form": form,
        }
    }


def _wave(field: str) -> Spec:
    return {"episode": {"ref": "trend", "entity": "wave", "index": "current", "field": field}}


HEIGHT = {"abs": {"difference": {"left": _wave("peak_price"), "right": _wave("origin_price")}}}
VALUES = {
    "s100": _wc(100, 12, "slope"),
    "s50": _wc(50, 24, "slope"),
    "m50": {"ratio": {"left": _wc(50, 24, "change"), "right": HEIGHT}},
}


def test_window_change_parses_and_nests() -> None:
    operand = _parse(_wc(100, 12, "slope")).long.operand
    assert operand.window_change.last_n == 12 and operand.window_change.form == "slope"
    assert _parse(VALUES["m50"]).long.operand.ratio.left.window_change is not None
    assert _parse({"abs": _wc(50, 24, "change")}).long.operand.absolute.window_change is not None
    at = {"at_point": {"episode": "trend", "point": "peak", "operand": _wc(50, 3, "change")}}
    assert _parse(at).long.operand.at_point.operand.window_change is not None


@pytest.mark.parametrize(
    "payload",
    [
        {"of": _ema(50), "last_n": 24, "form": "slope"},
        {"episode": "trend", "last_n": 24, "form": "slope"},
        {"episode": "trend", "of": _ema(50), "form": "slope"},
        {"episode": "trend", "of": _ema(50), "last_n": 24},
        {"episode": "trend", "of": _ema(50), "last_n": 0, "form": "slope"},
        {"episode": "trend", "of": _ema(50), "last_n": True, "form": "slope"},
        {"episode": "trend", "of": _ema(50), "last_n": 24, "form": "level"},
        {"episode": "other", "of": _ema(50), "last_n": 24, "form": "slope"},
        {"episode": "trend", "of": {**_ema(50), "timeframe": "1h"}, "last_n": 24, "form": "slope"},
        {"episode": "trend", "of": _ema(50), "last_n": 24, "form": "slope", "extra": 1},
    ],
)
def test_malformed_window_change_is_rejected(payload: Spec) -> None:
    with pytest.raises(InvalidRequestError):
        _parse({"window_change": payload})


def test_window_change_is_not_a_change_operand() -> None:
    with pytest.raises(InvalidRequestError):
        parse_predicate(
            {
                "kind": "change",
                "operand": _wc(50, 24, "slope"),
                "lookback": 3,
                "op": ">",
                "value": 0,
            },
            "p",
            episode_refs=["trend"],
        )


def _branch(operand: Spec) -> Spec:
    return {
        "kind": "range",
        "operand": operand,
        "min": None,
        "max": None,
        "bounds": "exclusive",
        "empty": "pass",
    }


def _probe() -> Spec:
    children = [{"child_id": key, "predicate": _branch(op)} for key, op in VALUES.items()]
    children += [
        {
            "child_id": f"e{n}",
            "predicate": _branch(
                {"ratio": {"left": {"feature": _ema(n)}, "right": {"const": 1.0}}}
            ),
        }
        for n in (50, 100)
    ]
    return {
        "component_id": "composite_setup",
        "instance_id": "probe",
        "params": {
            "children": children,
            "paths": [{"path_id": "pass", "require": [c["child_id"] for c in children]}],
        },
    }


def _vote(level: float) -> Spec:
    vote_input = {
        "input_id": "s50",
        "operand": VALUES["s50"],
        "direction": "at_most",
        "steps": [{"level": level, "veto": True}],
    }
    return {
        "component_id": "weighted_vote_setup",
        "instance_id": "vote",
        "params": {
            "threshold": 0.75,
            "voters": [{"voter_id": "s50", "role": "vote", "inputs": [vote_input]}],
        },
    }


def _spec(*setups: Spec) -> Spec:
    spec = base_spec()
    spec["ema_stack_episode"] = {"trend": {"window_bars": WINDOW}}
    spec["setups"] = list(setups)
    return spec


def _mask(capture: Any, side: str) -> Any:
    side_eval = next(item for item in capture.evaluation.setups if item.side == side)
    (mask,) = side_eval.setups
    return mask


def _trace(mask: Any, child: str) -> np.ndarray:
    return np.array([math.nan if v is None else v for v in mask.trace[f"child:{child}:value"]])


def _expected(episode: Any, ema: np.ndarray, last_n: int, form: str, side: str) -> np.ndarray:
    g = 1.0 if side == "long" else -1.0
    out = np.full(len(ema), math.nan)
    for t in range(len(ema)):
        legs = _legs(episode, t)
        if legs is None:
            continue
        origin, peak, _ = legs
        if not (origin <= peak <= t):
            continue
        s0 = max(peak, t - last_n)
        if t <= s0 or not (math.isfinite(ema[s0]) and math.isfinite(ema[t])):
            continue
        move = g * (ema[t] - ema[s0])
        if form == "change":
            out[t] = move
        elif ema[s0] != 0:
            out[t] = move / ema[s0] / (t - s0) * 1e4
    return out


def test_values_match_the_loop() -> None:
    probe, _ = _run([_variant("probe", _spec(_probe()))])
    (capture,) = probe.captures
    for side in ("long", "short"):
        mask = _mask(capture, side)
        episode = capture.evaluation.contexts.episodes.side("trend", side)
        e50, e100 = _trace(mask, "e50"), _trace(mask, "e100")
        expected = {
            "s100": _expected(episode, e100, 12, "slope", side),
            "s50": _expected(episode, e50, 24, "slope", side),
        }
        change = _expected(episode, e50, 24, "change", side)
        height = np.full(len(e50), math.nan)
        for t in range(len(e50)):
            legs = _legs(episode, t)
            if legs is None:
                continue
            row = int(episode.first_row[int(episode.state["episode_id"][t])])
            row += int(episode.state["touch_number"][t]) - 1
            height[t] = abs(
                episode.touches["peak_price"][row] - episode.touches["origin_price"][row]
            )
        with np.errstate(invalid="ignore", divide="ignore"):
            expected["m50"] = np.where(height > 0, change / height, math.nan)
        for key, value in expected.items():
            assert np.isfinite(value).sum() > 20, "fixture must give values"
            np.testing.assert_allclose(
                _trace(mask, key), value, rtol=1e-12, atol=1e-15, equal_nan=True
            )


def test_veto_matches_the_values() -> None:
    probe, _ = _run([_variant("probe", _spec(_probe()))])
    values = {s: _trace(_mask(probe.captures[0], s), "s50") for s in ("long", "short")}
    finite = np.unique(values["long"][np.isfinite(values["long"])])
    level = float((finite[len(finite) // 5] + finite[len(finite) // 5 + 1]) / 2)
    recorder, context = _run([_variant("vote", _spec(_vote(level)))])
    assert context.stats.unforeseen_consumptions == 0
    for side in ("long", "short"):
        blocked = np.isfinite(values[side]) & (values[side] <= level)
        assert blocked.any()
        allowed = _mask(recorder.captures[0], side).local_setup_allowed
        assert list(allowed) == list((~blocked).tolist())


def test_candidates_differing_only_in_a_level_share_the_nodes() -> None:
    variants = [_variant(f"c{i}", _spec(_vote(-1.0 - 0.5 * i))) for i in range(4)]
    recorder, context = _run(variants)
    assert len(recorder.captures) == 4
    assert context.stats.unforeseen_consumptions == 0
    assert _calls(context, "predicate.window_change") == 2  # one per side


def test_a_spec_without_the_operand_adds_no_node() -> None:
    recorder, context = _run([_variant("plain", base_spec())])
    assert len(recorder.captures) == 1
    assert _calls(context, "predicate.window_change") == 0
