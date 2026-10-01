"""Frozen partial take ladder through `/range-batch` on the parity market
fixture (OpenSpec `frozen-partial-take-ladder-v1`): memo identities and
compute sharing (task 2.3)."""

from __future__ import annotations

import copy
from typing import Any

from parity.corpus import _exits, _variant, base_spec
from parity.harness import Recorder, _drain_route, batch_payload, recording_services
from parity.invariants import _capturing_contexts

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
