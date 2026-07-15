from __future__ import annotations

from fastapi.testclient import TestClient

from strategy_engine.adapters.http.app import create_app


def strategy_payload() -> dict[str, object]:
    return {
        "market": {
            "ticker": "BTCUSDT.P",
            "base_timeframe": "5m",
            "from_ms": 0,
            "to_ms": 300_000,
        },
        "strategy": {
            "strategy_id": "ema_pullback",
            "strategy_version": "v1",
            "instance_id": "variant-a",
            "raw_spec": {"strategy": {"id": "ema_pullback"}},
            "compatibility_profile": "bbb_v1",
        },
        "options": {
            "include_features": True,
            "include_contexts": True,
            "include_component_evidence": True,
            "include_state_artifact": False,
        },
    }


def test_health_readiness_and_openapi() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/health").json()["status"] == "ok"
        readiness = client.get("/readiness").json()
        assert readiness["status"] == "ready"
        assert readiness["capabilities"]["strategy_evaluation"] == "ready"
        assert "/v1/strategy-evaluations/range" in client.get("/openapi.json").json()["paths"]


def test_catalogs_advertise_only_ported_capabilities() -> None:
    with TestClient(create_app()) as client:
        indicators = client.get("/v1/indicators").json()["items"]
        assert [item["indicator_id"] for item in indicators] == [
            "ema",
            "atr",
            "atr_distance",
            "rsi",
            "adx",
            "di_plus",
            "di_minus",
        ]
        assert client.get("/v1/indicators/ema/schema").status_code == 200
        strategies = client.get("/v1/strategies").json()["items"]
        assert [item["strategy_id"] for item in strategies] == ["ema_pullback"]
        response = client.get("/v1/indicators/atr_distance/schema")
        assert response.status_code == 200
        assert response.json()["derived_from"] == "atr"


def test_unported_indicator_evaluation_returns_501_not_fake_success() -> None:
    payload = {
        "market": {
            "ticker": "BTCUSDT.P",
            "base_timeframe": "5m",
            "from_ms": 0,
            "to_ms": 300_000,
        },
        "plan": {
            "plan_version": "1",
            "features": [
                {
                    "output_id": "macd_5m",
                    "kind": "macd",
                    "timeframe": "5m",
                    "source": "close",
                    "parameters": {"period": 14},
                    "dependencies": [],
                }
            ],
        },
    }
    with TestClient(create_app()) as client:
        response = client.post("/v1/indicator-evaluations/range", json=payload)
        assert response.status_code == 501
        assert response.json()["error"] == "unsupported_capability"
        assert "request_id" in response.json()


def test_unported_strategy_evaluation_returns_501() -> None:
    with TestClient(create_app()) as client:
        response = client.post("/v1/strategy-evaluations/range", json=strategy_payload())
        assert response.status_code == 422
        assert response.json()["error"] == "invalid_request"


def test_batch_preserves_variant_order_and_error_identity() -> None:
    first = strategy_payload()["strategy"]
    assert isinstance(first, dict)
    second = dict(first)
    second["instance_id"] = "variant-b"
    payload = {
        "market": strategy_payload()["market"],
        "variants": [
            {"variant_id": "a", "strategy": first},
            {"variant_id": "b", "strategy": second},
        ],
    }
    with TestClient(create_app()) as client:
        response = client.post("/v1/strategy-evaluations/range-batch", json=payload)
        assert response.status_code == 200
        variants = response.json()["variants"]
        assert [item["variant_id"] for item in variants] == ["a", "b"]
        assert all(item["error"]["error"] == "invalid_request" for item in variants)


def test_invalid_range_uses_stable_error_envelope() -> None:
    payload = strategy_payload()
    market = payload["market"]
    assert isinstance(market, dict)
    market["from_ms"] = 1
    with TestClient(create_app()) as client:
        response = client.post("/v1/strategy-evaluations/range", json=payload)
        assert response.status_code == 422
        body = response.json()
        assert set(body) == {"error", "message", "details", "request_id"}
