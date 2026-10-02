"""Declared invariants for `/live-entry` (OpenSpec
`frozen-partial-take-ladder-v1`, tasks 0.1/0.2).

The batch and managed gates do not cover the live entry plan. These cases
pin the exact HTTP `/live-entry` response bytes for fixed target bars of
the parity market fixture (long, short and no-plan bars) for specs without
partial takes -- the `live-entry-projection-v1` scenario "Desired entry
without partial takes" and `batch-computation-reuse` "No compute regression
for specs without partial takes".

Digests only, like `invariants.py`.
"""

from __future__ import annotations

import copy
from typing import Any

from fastapi.testclient import TestClient

from parity.corpus import _exits, base_spec
from parity.harness import market_fixture_meta
from parity.invariants import _digest
from parity.managed_invariants import _bar, _slice_services
from strategy_engine.adapters.http.app import create_app

Spec = dict[str, Any]

# Target bars of the market fixture: long plans 3555/4406, short plans
# 3851/3999, no plan 3000 (found by scanning `base_spec` on pre-change code).
TARGET_INDICES = (3000, 3555, 3851, 3999, 4406)


def _constant_usd_spec() -> Spec:
    return _exits(
        base_spec(),
        [
            {
                "component_id": "constant_usd_stop_loss",
                "exit_kind": "stop_loss",
                "instance_id": "usd-sl",
                "usd_distance": 500,
            },
            {
                "component_id": "constant_usd_take_profit",
                "exit_kind": "take_profit",
                "instance_id": "usd-tp",
                "usd_distance": "1250.5",
            },
        ],
    )


def live_entry_specs() -> dict[str, Spec]:
    return {"base_atr": copy.deepcopy(base_spec()), "constant_usd": _constant_usd_spec()}


def live_entry_response(client: TestClient, spec: Spec, index: int) -> bytes:
    meta = market_fixture_meta()
    response = client.post(
        "/v1/strategy-evaluations/live-entry",
        json={
            "strategy_id": "ema_pullback",
            "raw_spec": spec,
            "ticker": meta["ticker"],
            "base_timeframe": meta["timeframe"],
            "target_bar_open_time_ms": _bar(index).open_time_ms,
        },
    )
    assert response.status_code == 200, response.text
    return response.content


def live_entry_invariants() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    with _slice_services() as services, TestClient(create_app(services=services)) as client:
        for name, spec in live_entry_specs().items():
            out[name] = {
                str(index): _digest(live_entry_response(client, spec, index))
                for index in TARGET_INDICES
            }
    return out
