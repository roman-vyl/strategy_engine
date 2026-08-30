"""I5 Lane A proof-only dual serializer (`compact-strategy-evaluation-
boundary-v1`, Master Plan I5.B).

Resolves one BTCUSDT.P/5m window ONCE (a single MDS bounds call), then
runs BOTH Engine computations against that identical explicit
`from_ms`/`to_ms` range:

  1. `EmaPullbackRangeEvaluator.evaluate()` (legacy dense
     `StrategyRangeResult`) -- Lane A's reference path, per
     `research-historical-execution-parity-v1`'s corrected "Lane A
     reference" requirement: proof-only, in-process, never through
     Engine's live `/range` route (which already serves the superseded
     sparse `.v1` contract Research's legacy client cannot parse).
  2. `EmaPullbackRangeEvaluator._evaluate_frame_native` +
     `build_historical_execution_projection` (I1) -- the new path,
     serialized to the normative `strategy_evaluation_execution.v2`
     envelope (same serializer as
     `serialize_historical_execution_projection_v2.py`).

Both calls use the SAME explicit `TimeRange`, so even though each is a
separate MDS fetch, resolving the range once (not "full_available"
twice) means both see the same committed historical window regardless
of any bar that closes between the two calls. Both results' own
`market_data_hash`/`bar_count` are printed so the harness can verify
they agree -- this script does not assume they do.

Writes two JSON files: `--dense-out` (legacy `StrategyRangeResult`,
`strategy_evaluation.v1` envelope) and `--v2-out` (the new
`HistoricalExecutionProjection`, `strategy_evaluation_execution.v2`
envelope).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

import httpx

from strategy_engine.adapters.http.strategy_serialization import serialize_strategy_result
from strategy_engine.adapters.market_data_service.client import MarketDataServiceClient
from strategy_engine.domain.market import MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.application.evaluate_range import EvaluateIndicatorRange
from strategy_engine.indicators.application.validate_plan import ValidateIndicatorPlan
from strategy_engine.service.registries import IndicatorRegistry
from strategy_engine.strategies.application.build_feature_plan import BuildStrategyFeaturePlan
from strategy_engine.strategies.contracts import LiveStrategySpec, StrategyRangeRequest
from strategy_engine.strategies.ema_pullback.evaluator import EmaPullbackRangeEvaluator

sys.path.insert(0, str(Path(__file__).resolve().parent))
from serialize_historical_execution_projection_v2 import (  # noqa: E402
    build_projection,
    serialize_v2,
)


def _evaluator() -> EmaPullbackRangeEvaluator:
    indicator_registry = IndicatorRegistry()
    market_data_client = MarketDataServiceClient(
        "http://127.0.0.1:8080", read_timeout_seconds=600.0
    )
    validate_plan = ValidateIndicatorPlan(indicator_registry)
    evaluate_indicator_range = EvaluateIndicatorRange(
        indicator_registry, market_data_client, validate_plan
    )
    feature_planner = BuildStrategyFeaturePlan()
    return EmaPullbackRangeEvaluator(feature_planner, evaluate_indicator_range)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--strategy-id", default="ema_pullback")
    parser.add_argument("--ticker", default="BTCUSDT.P")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--from-ms", type=int, default=None, help="Omit for full_available")
    parser.add_argument("--to-ms", type=int, default=None, help="Omit for full_available")
    parser.add_argument("--mds-base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--dense-out", required=True, type=Path)
    parser.add_argument("--v2-out", required=True, type=Path)
    args = parser.parse_args(argv)

    if args.from_ms is None or args.to_ms is None:
        bounds = httpx.get(
            f"{args.mds_base_url}/v1/streams/{args.ticker}/{args.timeframe}/bounds"
        ).json()
        from_ms = bounds["earliest_committed_open_time_ms"]
        to_ms = bounds["latest_committed_open_time_ms"] + _timeframe_ms(args.timeframe)
    else:
        from_ms, to_ms = args.from_ms, args.to_ms
    print(f"resolved range: {from_ms} .. {to_ms}", flush=True)

    raw_spec = json.loads(args.spec.read_text())
    strategy = LiveStrategySpec(strategy_id=args.strategy_id, raw_spec=raw_spec)
    market = MarketStream(ticker=args.ticker, base_timeframe=args.timeframe)
    time_range = TimeRange(from_ms=from_ms, to_ms=to_ms)

    evaluator = _evaluator()

    print("=== legacy dense evaluate() (Lane A reference) ===", flush=True)
    dense_request = StrategyRangeRequest(strategy=strategy, market=market, time_range=time_range)
    dense_result = evaluator.evaluate(dense_request)
    dense_envelope = serialize_strategy_result(dense_result)
    dense_features = cast("dict[str, Any]", dense_envelope["features"])
    dense_entries = cast("dict[str, Any]", dense_envelope["entries"])
    dense_hash = dense_features["market_data_hash"]
    dense_bar_count = len(dense_entries["long"])
    print(f"dense: market_data_hash={dense_hash} bar_count={dense_bar_count}", flush=True)
    args.dense_out.write_text(json.dumps(dense_envelope, indent=2))

    print("=== native evaluate_execution() + I1 builder (new path) ===", flush=True)
    projection = build_projection(
        raw_spec=raw_spec,
        strategy_id=args.strategy_id,
        ticker=args.ticker,
        timeframe=args.timeframe,
        from_ms=from_ms,
        to_ms=to_ms,
        mds_base_url=args.mds_base_url,
    )
    v2_envelope = serialize_v2(projection)
    print(
        f"v2: market_data_hash={projection.market_data_hash} bar_count={projection.bar_count}",
        flush=True,
    )
    args.v2_out.write_text(json.dumps(v2_envelope, indent=2))

    if dense_hash != projection.market_data_hash:
        print(
            "WARNING: dense and v2 market_data_hash differ -- the two Engine "
            "calls did not see the same committed dataset",
            flush=True,
        )
        return 1
    if dense_bar_count != projection.bar_count:
        print("WARNING: dense and v2 bar_count differ", flush=True)
        return 1
    print("frozen-input check: OK (both calls report the same market_data_hash/bar_count)")
    return 0


def _timeframe_ms(timeframe: str) -> int:
    table = {
        "1m": 60_000,
        "5m": 300_000,
        "15m": 900_000,
        "1h": 3_600_000,
        "4h": 14_400_000,
        "1d": 86_400_000,
    }
    return table[timeframe]


if __name__ == "__main__":
    sys.exit(main())
