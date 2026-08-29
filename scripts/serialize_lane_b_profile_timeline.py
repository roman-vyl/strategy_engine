"""I5 Lane B proof-only current-profile timeline
(`compact-strategy-evaluation-boundary-v1`, Master Plan I5.C).

Emits Strategy Engine's native `exit_policy.profile_long`/
`profile_short` per-bar series to a separate, proof-only JSON file --
NEVER added to the `strategy_evaluation_execution.v2` envelope, which
intentionally carries no current-bar-profile timeline
(`strategy-research-execution-contract-v1`: "never a flattened
current-bar-profile series"; `research-historical-execution-parity-v1`:
"Post-entry current-profile evolution is proof-only evidence, not a
HistoricalExecutionProjection field").

This file exists ONLY to let the Lane B harness compute a deliberately
WRONG "current-profile" interpretation for the negative control -- it
is never read by `parse_historical_execution_projection`,
`HistoricalExecutionProjectionIndex`, or `run_projection_execution_
loop`. Written alongside the same in-process native evaluation
`serialize_historical_execution_projection_v2.py` uses, from the same
explicit resolved range, so it lines up bar-for-bar with the v2
envelope produced for the identical request.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from strategy_engine.adapters.market_data_service.client import MarketDataServiceClient
from strategy_engine.domain.market import MarketStream
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.application.evaluate_range import EvaluateIndicatorRange
from strategy_engine.indicators.application.validate_plan import ValidateIndicatorPlan
from strategy_engine.service.registries import IndicatorRegistry
from strategy_engine.strategies.application.build_feature_plan import BuildStrategyFeaturePlan
from strategy_engine.strategies.contracts import LiveStrategySpec, StrategyRangeRequest
from strategy_engine.strategies.ema_pullback.evaluator import EmaPullbackRangeEvaluator


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--strategy-id", default="ema_pullback")
    parser.add_argument("--ticker", default="BTCUSDT.P")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--from-ms", required=True, type=int)
    parser.add_argument("--to-ms", required=True, type=int)
    parser.add_argument("--mds-base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    raw_spec = json.loads(args.spec.read_text())
    market_data_client = MarketDataServiceClient(args.mds_base_url, read_timeout_seconds=600.0)
    try:
        indicator_registry = IndicatorRegistry()
        validate_plan = ValidateIndicatorPlan(indicator_registry)
        evaluate_indicator_range = EvaluateIndicatorRange(
            indicator_registry, market_data_client, validate_plan
        )
        feature_planner = BuildStrategyFeaturePlan()
        evaluator = EmaPullbackRangeEvaluator(feature_planner, evaluate_indicator_range)

        strategy = LiveStrategySpec(strategy_id=args.strategy_id, raw_spec=raw_spec)
        request = StrategyRangeRequest(
            strategy=strategy,
            market=MarketStream(ticker=args.ticker, base_timeframe=args.timeframe),
            time_range=TimeRange(from_ms=args.from_ms, to_ms=args.to_ms),
        )
        frame, evaluation = evaluator._evaluate_frame_native(request)  # noqa: SLF001
    finally:
        market_data_client.close()

    payload = {
        "market_data_hash": frame.market_data_hash,
        "bar_count": len(frame.time_ms),
        "profile_long": list(evaluation.exit_policy.profile_long),
        "profile_short": list(evaluation.exit_policy.profile_short),
    }
    args.out.write_text(json.dumps(payload))
    print(f"wrote proof-only profile timeline: {payload['bar_count']} bars")
    return 0


if __name__ == "__main__":
    sys.exit(main())
