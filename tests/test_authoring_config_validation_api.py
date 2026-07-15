from fastapi.testclient import TestClient

from strategy_engine.adapters.http.app import create_app


def instance():
    return {
        "instance_id": "x",
        "variant": "x",
        "market": {"symbol": "BTCUSDT", "base_timeframe": "5m"},
        "strategy": {
            "trade_sides": ["long"],
            "anchor_stack": {
                "source": "close",
                "timeframe": "base",
                "fast": 20,
                "anchor": 50,
                "slow": 200,
            },
            "direction": {"component_id": "ema_anchor_stack_trend"},
            "setups": [],
            "trigger": {"component_id": "touch_anchor"},
            "blockers": [],
            "risk": {"component_id": "no_risk_filter"},
            "contexts": {},
            "trade_management": {
                "exit_policy": {
                    "always_on": {"exits": []},
                    "profiles": {
                        "aligned": {"exits": []},
                        "countertrend": {"exits": []},
                        "neutral": {"exits": []},
                    },
                },
                "exit_management": {
                    "mode": "managed",
                    "phase_rules": [],
                    "stop_management": [],
                    "take_management": [],
                    "runtime_exits": [],
                },
            },
        },
    }


def test_validates_workbench_authoring_shape():
    with TestClient(create_app()) as client:
        r = client.post(
            "/v1/strategies/ema_pullback/authoring-config/validate",
            json={"instances": [instance()]},
        )
    assert r.status_code == 200, r.text
    assert r.json()["valid"] is True


def test_returns_path_for_invalid_instance():
    item = instance()
    item["strategy"]["anchor_stack"]["fast"] = 0
    with TestClient(create_app()) as client:
        r = client.post(
            "/v1/strategies/ema_pullback/authoring-config/validate", json={"instances": [item]}
        )
    assert r.status_code == 200
    assert r.json()["valid"] is False and r.json()["errors"][0]["path"] == "instances[0]"


def test_authoring_trade_sides_object_is_normalized_for_execution() -> None:
    from strategy_engine.strategies.ema_pullback.authoring import (
        authoring_instance_to_envelope,
    )

    instance = {
        "instance_id": "draft-object-sides",
        "market": {"symbol": "BTCUSDT", "base_timeframe": "5m"},
        "strategy": {
            "trade_sides": {"long": True, "short": False},
            "anchor_stack": {
                "source": "close",
                "timeframe": "base",
                "fast": 2,
                "anchor": 3,
                "slow": 5,
            },
            "direction": {"component_id": "ema_anchor_stack_trend"},
            "setups": [],
            "trigger": {"component_id": "touch_anchor"},
            "blockers": [],
            "risk": {"component_id": "no_risk_filter"},
            "contexts": {},
            "trade_management": {
                "exit_policy": {
                    "always_on": {"exits": []},
                    "profiles": {
                        "aligned": {"exits": []},
                        "countertrend": {"exits": []},
                        "neutral": {"exits": []},
                    },
                },
                "exit_management": {},
            },
        },
    }

    envelope = authoring_instance_to_envelope(instance)

    assert envelope.raw_spec["trade_sides"] == ["long"]
