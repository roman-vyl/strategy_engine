from __future__ import annotations

from pathlib import Path

from strategy_engine.adapters.http.app import create_app

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_REMOVED_LIVE_FIELDS = {
    "abi_entry_correlation",
    "compatibility_profile",
    "contract_version",
    "executed_entry_price",
    "market_data_hash",
    "source_config_hash",
    "instance_id",
    "strategy_version",
    "trade_id",
}


def test_source_tree_has_no_stale_generated_package_artifacts() -> None:
    assert not (_REPOSITORY_ROOT / "dist").exists()
    assert not list((_REPOSITORY_ROOT / "src").glob("*.egg-info"))
    assert not list(_REPOSITORY_ROOT.glob("*.whl"))
    assert not list(_REPOSITORY_ROOT.glob("*.tar.gz"))


def test_live_openapi_is_clean_and_research_routes_remain_published() -> None:
    schema = create_app().openapi()
    paths = schema["paths"]
    assert {
        "/v1/strategy-evaluations/range",
        "/v1/strategy-evaluations/range-batch",
        "/v1/strategy-evaluations/managed-replay",
    } <= paths.keys()

    models = schema["components"]["schemas"]
    live_entry_request = set(models["LiveEntryProjectionRequestModel"]["properties"])
    open_trade_request = set(models["OpenTradeProjectionRequestModel"]["properties"])
    receipt = set(models["ExecutedTradeReceiptModel"]["properties"])
    live_entry_response = set(models["LiveEntryProjectionResponseModel"]["properties"])
    open_trade_response = set(models["OpenTradeProjectionResponseModel"]["properties"])

    assert live_entry_request == {
        "strategy_id",
        "raw_spec",
        "ticker",
        "base_timeframe",
        "target_bar_open_time_ms",
    }
    assert open_trade_request == live_entry_request | {"executed_trade_receipt"}
    assert "LiveStrategySpecModel" not in models
    assert "LiveMarketModel" not in models
    assert receipt == {
        "side",
        "source_plan_bar_open_time_ms",
        "entry_bar_open_time_ms",
        "planned_entry_price",
        "initial_stop_price",
        "initial_take_price",
        "locked_exit_profile",
    }
    assert not _REMOVED_LIVE_FIELDS & live_entry_request
    assert not _REMOVED_LIVE_FIELDS & open_trade_request
    assert not _REMOVED_LIVE_FIELDS & receipt
    assert not _REMOVED_LIVE_FIELDS & live_entry_response
    assert not _REMOVED_LIVE_FIELDS & open_trade_response
    assert live_entry_response == {"plans_by_side"}
    assert open_trade_response == {
        "desired_protection",
        "close_signal",
        "diagnostics",
    }
