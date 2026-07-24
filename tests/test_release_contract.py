from __future__ import annotations

from pathlib import Path

from strategy_engine.adapters.http.app import create_app

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_REMOVED_LIVE_FIELDS = {
    "abi_entry_correlation",
    "compatibility_profile",
    "contract_version",
    "market_data_hash",
    "source_config_hash",
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
    live_strategy = set(models["LiveStrategySpecModel"]["properties"])
    receipt = set(models["ExecutedTradeReceiptModel"]["properties"])
    live_entry_response = set(models["LiveEntryProjectionResponseModel"]["properties"])
    open_trade_response = set(models["OpenTradeProjectionResponseModel"]["properties"])

    assert live_strategy == {"strategy_id", "instance_id", "raw_spec"}
    assert receipt == {
        "side",
        "source_plan_bar_open_time_ms",
        "entry_bar_open_time_ms",
        "planned_entry_price",
        "executed_entry_price",
        "initial_stop_price",
        "initial_take_price",
        "locked_exit_profile",
    }
    assert not _REMOVED_LIVE_FIELDS & live_strategy
    assert not _REMOVED_LIVE_FIELDS & receipt
    assert not _REMOVED_LIVE_FIELDS & live_entry_response
    assert not _REMOVED_LIVE_FIELDS & open_trade_response
