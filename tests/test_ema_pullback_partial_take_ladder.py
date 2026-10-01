"""Frozen partial take ladder on the parity market fixture (OpenSpec
`frozen-partial-take-ladder-v1`): memo identities and compute sharing
(task 2.3), untouched open-trade (task 5.1), `/range-batch` and
`/live-entry` end to end (task 5.2)."""

from __future__ import annotations

import copy
import json
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from parity.corpus import _exits, _variant, base_spec
from parity.harness import Recorder, _drain_route, batch_payload, recording_services
from parity.invariants import _capturing_contexts
from parity.live_entry_invariants import live_entry_response
from parity.managed_invariants import _SPECS, _open_trade_invariants, _slice_services

from strategy_engine.adapters.http.app import create_app

Spec = dict[str, Any]

SL = {
    "instance_id": "sl",
    "component_id": "atr_stop_loss",
    "exit_kind": "stop_loss",
    "distance": {"timeframe": "base", "period": 48, "multiplier": 3.0},
}
TP = {
    "instance_id": "tp",
    "component_id": "atr_take_profit",
    "exit_kind": "take_profit",
    "distance": {"timeframe": "base", "period": 48, "multiplier": 6.0},
}


def pct_leg(instance_id: str, pct: float, fraction: float) -> Spec:
    return {
        "instance_id": instance_id,
        "component_id": "pct_partial_take",
        "exit_kind": "partial_take",
        "pct": pct,
        "fraction_of_initial": fraction,
    }


def atr_leg(instance_id: str, multiplier: float, fraction: float) -> Spec:
    return {
        "instance_id": instance_id,
        "component_id": "atr_partial_take",
        "exit_kind": "partial_take",
        "distance": {"timeframe": "base", "period": 48, "multiplier": multiplier},
        "fraction_of_initial": fraction,
    }


def ladder_spec(always_on: list[Spec], **profiles: list[Spec]) -> Spec:
    return _exits(copy.deepcopy(base_spec()), [SL, TP, *always_on], **profiles)


def run(
    variants: list[dict[str, Any]], *, memo_enabled: bool = True
) -> tuple[list[Any], Any, dict[str, Any]]:
    recorder = Recorder()
    with _capturing_contexts() as contexts, recording_services(
        recorder, memo_enabled=memo_enabled
    ) as services:
        ndjson = _drain_route(services, batch_payload(variants))
    assert ndjson["termination"]["kind"] == "complete", ndjson["termination"]
    for capture in recorder.captures:
        assert capture.exception is None, capture.exception
    return (
        [capture.evaluation for capture in recorder.captures],
        contexts[0] if contexts else None,
        ndjson,
    )


# -- memo (task 2.3) -------------------------------------------------------------


def test_fraction_only_differences_share_every_exit_distance_node() -> None:
    variants = [
        _variant("q", ladder_spec([pct_leg("p1", 0.01, 0.25), atr_leg("p2", 2.0, 0.25)])),
        _variant("h", ladder_spec([pct_leg("p1", 0.01, 0.5), atr_leg("p2", 2.0, 0.1)])),
    ]
    _, context, _ = run(variants)
    assert context.stats.unforeseen_consumptions == 0
    distance_calls = {
        identity: count
        for identity, count in context.stats.compute_calls.items()
        if identity.kind.startswith("exit.distance.")
    }
    # sl, tp, the ATR leg and the pct leg: each computed once per batch.
    assert sorted(identity.kind for identity in distance_calls) == [
        "exit.distance.atr",
        "exit.distance.atr",
        "exit.distance.atr",
        "exit.distance.pct",
    ]
    assert set(distance_calls.values()) == {1}


def test_atr_leg_shares_identity_with_an_equal_atr_take() -> None:
    twin = atr_leg("twin", 6.0, 0.25)  # same ATR distance column as TP
    _, context, _ = run([_variant("twin", ladder_spec([twin]))])
    assert context.stats.unforeseen_consumptions == 0
    atr_kinds = [
        identity
        for identity in context.stats.compute_calls
        if identity.kind == "exit.distance.atr"
    ]
    assert len(atr_kinds) == 2  # sl and the shared tp/twin distance


def test_memo_on_and_off_are_bit_identical() -> None:
    variants = [
        _variant(
            "ladder",
            ladder_spec(
                [pct_leg("p1", 0.004, 0.25)],
                aligned=[atr_leg("p2", 2.0, 0.25)],
            ),
        ),
        _variant("plain", ladder_spec([])),
    ]
    on, context, on_ndjson = run(variants, memo_enabled=True)
    off, _, off_ndjson = run(variants, memo_enabled=False)
    assert context.stats.unforeseen_consumptions == 0
    assert on_ndjson["lines"] == off_ndjson["lines"]
    for left, right in zip(on, off, strict=True):
        assert left.exit_policy == right.exit_policy
        assert left.entries == right.entries


# -- untouched surfaces (task 5.1) -----------------------------------------------


def test_open_trade_with_a_ladder_equals_open_trade_without() -> None:
    managed = _SPECS["htf_adx_aligned"]
    laddered = copy.deepcopy(managed)
    policy = laddered["trade_management"]["exit_policy"]
    policy["always_on"]["exits"] += [pct_leg("p1", 0.004, 0.25), atr_leg("p2", 2.0, 0.25)]
    policy["profiles"]["aligned"]["exits"] = [pct_leg("p3", 0.008, 0.25)]
    with _slice_services() as services:
        assert _open_trade_invariants(services, laddered) == _open_trade_invariants(
            services, managed
        )


# -- end to end (task 5.2) -------------------------------------------------------


_LIVE_LONG_TARGET = 3555  # a long `/live-entry` plan bar of `base_spec` (group 0 gate)


def _e2e_spec() -> Spec:
    # SL/TP as in `base_spec` (ATR 48, x3 / x6), so the live plan bar keeps its plan.
    spec = copy.deepcopy(base_spec())
    policy = spec["trade_management"]["exit_policy"]
    policy["always_on"]["exits"] += [pct_leg("p-pct", 0.004, 0.25), atr_leg("p-atr", 2.0, 0.25)]
    policy["profiles"]["aligned"]["exits"] = [pct_leg("p-aligned", 0.008, 0.2)]
    return spec


def _profile_spec() -> Spec:
    # `_e2e_spec` with exit profiles selected by the 1h HTF state.
    spec = _e2e_spec()
    spec["contexts"] = {
        "htf": {
            "component_id": "htf_context",
            "timeframe": "1h",
            "source": "close",
            "fast_period": 20,
            "anchor_period": 50,
            "slow_period": 200,
        }
    }
    spec["trade_management"]["exit_policy"]["context_consumption"] = {
        "context_ref": "htf",
        "policy": {"policy_id": "exit_profile_by_htf_state"},
    }
    return spec


_LEG_COMPONENTS = {
    "p-pct": "pct_partial_take",
    "p-atr": "atr_partial_take",
    "p-aligned": "pct_partial_take",
}


def test_range_batch_opportunities_carry_the_legs_of_their_locked_profile() -> None:
    _, context, ndjson = run([_variant("e2e", _profile_spec())])
    assert context.stats.unforeseen_consumptions == 0
    (line,) = ndjson["lines"]
    opportunities = json.loads(line)["result"]["entry_opportunities"]
    assert opportunities
    profiles = set()
    for opportunity in opportunities:
        profiles.add(opportunity["locked_exit_profile"])
        legs = {leg["take_id"]: leg for leg in opportunity["partial_takes"]}
        expected = {"p-pct", "p-atr"} | (
            {"p-aligned"} if opportunity["locked_exit_profile"] == "aligned" else set()
        )
        assert set(legs) == expected
        ratios = [leg["ratio"] for leg in opportunity["partial_takes"]]
        assert ratios == sorted(ratios)
        assert legs["p-pct"]["ratio"] == 0.004
        assert legs["p-pct"]["fraction_of_initial"] == 0.25
        # Shared ATR(48): the x2 leg is a third of the x6 final take.
        take = opportunity["initial_take"]
        assert legs["p-atr"]["ratio"] == pytest.approx(take["ratio"] / 3, rel=1e-12)
        assert take["attribution"]["exit_kind"] == "take_profit"
        for take_id, leg in legs.items():
            assert leg["attribution"] == {
                "rule_id": take_id,
                "component_id": _LEG_COMPONENTS[take_id],
                "exit_kind": "partial_take",
            }
    assert "aligned" in profiles and len(profiles) > 1


def test_live_entry_legs_follow_the_design_formulas() -> None:
    with _slice_services() as services, TestClient(create_app(services=services)) as client:
        body = live_entry_response(client, _e2e_spec(), _LIVE_LONG_TARGET)
    desired = json.loads(body)["desired_entry"]
    assert desired is not None and desired["side"] == "long"
    entry = Decimal(desired["planned_entry_price"])
    take = Decimal(desired["initial_take_price"])
    legs = {leg["take_id"]: leg for leg in desired["partial_takes"]}
    expected_ids = {"p-pct", "p-atr"} | (
        {"p-aligned"} if desired["locked_exit_profile"] == "aligned" else set()
    )
    assert set(legs) == expected_ids
    assert Decimal(legs["p-pct"]["price"]) == entry * Decimal("1.004")
    assert legs["p-pct"]["fraction_of_initial"] == "0.25"
    atr_distance = Decimal(legs["p-atr"]["price"]) - entry
    assert float(atr_distance) == pytest.approx(float(take - entry) / 3, rel=1e-9)
    prices = [Decimal(leg["price"]) for leg in desired["partial_takes"]]
    assert prices == sorted(prices)
