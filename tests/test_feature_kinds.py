"""Canonical feature-kind contract (design D13, tasks 3.5).

Registry responses, labels and identities of existing kinds are pinned by the
declared-invariant gate (`tests/test_declared_invariants.py`); these tests
cover the contract's own behavior and the extension invariant.
"""

from __future__ import annotations

from typing import Any

import pytest

from strategy_engine.domain.errors import InvalidRequestError, UnsupportedCapabilityError
from strategy_engine.indicators import feature_kinds as feature_kinds_module
from strategy_engine.indicators.contracts import PlannedFeature
from strategy_engine.indicators.feature_kinds import (
    FeatureKindContract,
    feature_kind,
    feature_kinds,
    plan_feature_request,
)
from strategy_engine.indicators.implementations.range_evaluator import resolve_feature
from strategy_engine.service.registries import IndicatorRegistry


def test_existing_kinds_in_public_order() -> None:
    assert [contract.kind for contract in feature_kinds()] == [
        "ema",
        "atr",
        "atr_distance",
        "rsi",
        "adx",
        "di_plus",
        "di_minus",
    ]
    assert [c.kind for c in feature_kinds() if c.requestable] == [
        "ema",
        "atr",
        "rsi",
        "adx",
        "di_plus",
        "di_minus",
    ]


def test_unknown_kind_fails_closed() -> None:
    with pytest.raises(InvalidRequestError):
        feature_kind("bollinger")
    with pytest.raises(InvalidRequestError):
        plan_feature_request("bollinger", "1h", None, {"period": 20})
    with pytest.raises(InvalidRequestError, match="unsupported indicator kind"):
        resolve_feature(
            PlannedFeature("x", "bollinger", "base", "close", {"period": 20}),
            base_timeframe="5m",
            upstream={},
        )
    with pytest.raises(UnsupportedCapabilityError):
        IndicatorRegistry().validate_feature(PlannedFeature("x", "bollinger", "base", "close"))


def test_dependency_bearing_kind_is_not_requestable() -> None:
    with pytest.raises(InvalidRequestError, match="not requestable"):
        plan_feature_request("atr_distance", None, None, {"multiplier": 2.0})


def test_plan_feature_request_matches_planner_features() -> None:
    assert plan_feature_request("ema", "1h", None, {"period": 200}) == PlannedFeature(
        "ema_close_1h_200", "ema", "1h", "close", {"period": 200}
    )
    # Source-blind EMA label (pinned legacy collision, design D7).
    assert plan_feature_request("ema", "1h", "open", {"period": 200}).output_id == (
        "ema_close_1h_200"
    )
    assert plan_feature_request("adx", None, None, {"period": 14}) == PlannedFeature(
        "adx_close_base_14", "adx", "base", "close", {"period": 14}
    )


@pytest.mark.parametrize(
    ("kind", "source", "params"),
    [
        ("ema", "median", {"period": 10}),
        ("rsi", "open", {"period": 14}),
        ("adx", None, {"period": 0}),
        ("atr", None, {}),
        ("rsi", None, {"period": 14, "extra": 1}),
    ],
)
def test_plan_feature_request_uses_the_kind_validator(
    kind: str, source: str | None, params: dict[str, Any]
) -> None:
    with pytest.raises(InvalidRequestError):
        plan_feature_request(kind, None, source, params)


def _validate_fake(feature: PlannedFeature) -> None:
    if set(feature.parameters) != {"period", "std"}:
        raise InvalidRequestError("fake parameters must be period and std")


def test_new_kind_needs_only_a_contract_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Extension invariant: a test-only kind with an extra parameter is
    requestable and gets distinct identities per parameter value, with no
    change outside the contract."""

    fake = FeatureKindContract(
        kind="fake_band",
        schema={"indicator_id": "fake_band"},
        default_source="close",
        validate=_validate_fake,
        label=lambda tf, _src, params, _deps: (
            f"fake_band_{tf}_{params['period']}_{params['std']}"
        ),
        identity_params=lambda f: {
            "period": int(f.parameters["period"]),
            "std": float(f.parameters["std"]),
        },
    )
    monkeypatch.setitem(feature_kinds_module._CONTRACTS, "fake_band", fake)

    narrow = plan_feature_request("fake_band", "1h", None, {"period": 20, "std": 2})
    wide = plan_feature_request("fake_band", "1h", None, {"period": 20, "std": 3})
    assert narrow.output_id != wide.output_id
    identities = {
        resolve_feature(feature, base_timeframe="5m", upstream={}) for feature in (narrow, wide)
    }
    assert len(identities) == 2
    assert IndicatorRegistry().get_schema("fake_band") == {"indicator_id": "fake_band"}
