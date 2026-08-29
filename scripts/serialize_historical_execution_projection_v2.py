"""I5 proof-only `strategy_evaluation_execution.v2` envelope serializer
(`compact-strategy-evaluation-boundary-v1`, Master Plan checkpoint I5,
task I5.A).

NOT `src/`, NOT route-wired, NOT reachable from any production
endpoint. Exists solely so the cross-repo I5 proof harness can obtain a
real, wire-normative `HistoricalExecutionProjection` JSON envelope from
real production strategy computation, without any `/range` route
change before I7 -- exactly the "minimal proof-only way to get an
exact, spec-normative v2 JSON envelope" `strategy-research-execution-
contract-v1`'s I5 companion requirement calls for.

Pipeline -- real production computation, nothing reimplemented:

    EmaPullbackRangeEvaluator._evaluate_frame_native(request)
        -> (NativeFeatureFrame, EmaPullbackEvaluation)
           the exact native path `evaluate_execution()` already uses
    build_historical_execution_projection(...)   # I1's pure builder
        -> HistoricalExecutionProjection
    _serialize_v2(...)   # mirrors strategy_serialization.py::
                          # serialize_strategy_evaluation_execution's
                          # envelope structure (contract_version,
                          # nested market{ticker, base_timeframe,
                          # from_ms, to_ms, bar_count,
                          # market_data_hash}) for the new payload
                          # shape, per strategy-research-execution-
                          # contract-v1's normative
                          # contract_version = "strategy_evaluation_execution.v2"

Usage:
    python scripts/serialize_historical_execution_projection_v2.py \
        --spec path/to/raw_spec.json \
        --strategy-id ema_pullback \
        --ticker BTCUSDT.P --timeframe 5m \
        --from-ms 0 --to-ms 300000 \
        [--mds-base-url http://127.0.0.1:8080] \
        [--out projection_v2.json]

Prints the envelope to stdout (or writes it to `--out`) as JSON.
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
from strategy_engine.strategies.contracts import (
    ExecutableEntryOpportunity,
    ExitAttribution,
    HistoricalExecutionProjection,
    InitialProtectionLeg,
    LiveStrategySpec,
    SignalExitEvent,
    SignalExitProjection,
    StrategyRangeRequest,
    strategy_config_hash,
)
from strategy_engine.strategies.ema_pullback.evaluator import EmaPullbackRangeEvaluator
from strategy_engine.strategies.historical_execution_projection import (
    build_historical_execution_projection,
)

_CONTRACT_VERSION = "strategy_evaluation_execution.v2"


def _serialize_attribution(attribution: ExitAttribution) -> dict[str, object]:
    return {
        "rule_id": attribution.rule_id,
        "component_id": attribution.component_id,
        "exit_kind": attribution.exit_kind,
    }


def _serialize_leg(leg: InitialProtectionLeg | None) -> dict[str, object] | None:
    if leg is None:
        return None
    return {"ratio": leg.ratio, "attribution": _serialize_attribution(leg.attribution)}


def _serialize_opportunity(opportunity: ExecutableEntryOpportunity) -> dict[str, object]:
    return {
        "bar_index": opportunity.bar_index,
        "side": opportunity.side,
        "locked_exit_profile": opportunity.locked_exit_profile,
        "initial_stop": _serialize_leg(opportunity.initial_stop),
        "initial_take": _serialize_leg(opportunity.initial_take),
    }


def _serialize_events(events: tuple[SignalExitEvent, ...]) -> list[dict[str, object]]:
    return [
        {
            "bar_index": event.bar_index,
            "candidates": [
                {"attribution": _serialize_attribution(candidate.attribution)}
                for candidate in event.candidates
            ],
        }
        for event in events
    ]


def _serialize_signal_projection(projection: SignalExitProjection) -> dict[str, object]:
    return {
        "long": {profile: _serialize_events(events) for profile, events in projection.long.items()},
        "short": {
            profile: _serialize_events(events) for profile, events in projection.short.items()
        },
    }


def serialize_v2(result: HistoricalExecutionProjection) -> dict[str, object]:
    """Mirrors `strategy_serialization.py::serialize_strategy_evaluation_
    execution`'s envelope structure exactly -- `contract_version`,
    `market{ticker, base_timeframe, from_ms, to_ms, bar_count,
    market_data_hash}` nested the same way -- with `.v2`'s new payload
    (`entry_opportunities`/`signal_exit_events`) in place of `.v1`'s
    `decision_events`."""

    return {
        "contract_version": _CONTRACT_VERSION,
        "strategy_id": result.strategy_id,
        "config_hash": result.config_hash,
        "market": {
            "ticker": result.market.ticker,
            "base_timeframe": result.market.base_timeframe,
            "from_ms": result.requested_range.from_ms,
            "to_ms": result.requested_range.to_ms,
            "bar_count": result.bar_count,
            "market_data_hash": result.market_data_hash,
        },
        "entry_opportunities": [
            _serialize_opportunity(opportunity) for opportunity in result.entry_opportunities
        ],
        "signal_exit_events": _serialize_signal_projection(result.signal_exit_events),
        "warnings": list(result.warnings),
    }


def build_projection(
    *,
    raw_spec: dict[str, object],
    strategy_id: str,
    ticker: str,
    timeframe: str,
    from_ms: int,
    to_ms: int,
    mds_base_url: str,
) -> HistoricalExecutionProjection:
    """Real production computation: the same evaluator construction
    `service/wiring.py::build_services` uses, minus the parts (live
    entry/open-trade, catalogs) this proof doesn't need. Calls the
    real, already-shipped `_evaluate_frame_native` -- the exact native
    path `evaluate_execution()` uses -- then I1's pure builder. No
    strategy semantics are reimplemented here."""

    market_data_client = MarketDataServiceClient(mds_base_url)
    try:
        indicator_registry = IndicatorRegistry()
        validate_plan = ValidateIndicatorPlan(indicator_registry)
        evaluate_indicator_range = EvaluateIndicatorRange(
            indicator_registry, market_data_client, validate_plan
        )
        feature_planner = BuildStrategyFeaturePlan()
        evaluator = EmaPullbackRangeEvaluator(feature_planner, evaluate_indicator_range)

        strategy = LiveStrategySpec(strategy_id=strategy_id, raw_spec=raw_spec)
        request = StrategyRangeRequest(
            strategy=strategy,
            market=MarketStream(ticker=ticker, base_timeframe=timeframe),
            time_range=TimeRange(from_ms=from_ms, to_ms=to_ms),
        )

        # Same private entrypoint `evaluate_execution()` itself calls --
        # not a new production surface, just invoked directly here since
        # this proof-only script needs the intermediate EmaPullbackEvaluation
        # (evaluate_execution() only returns the superseded .v1 shape).
        frame, evaluation = evaluator._evaluate_frame_native(request)  # noqa: SLF001

        return build_historical_execution_projection(
            strategy_id=strategy_id,
            config_hash=strategy_config_hash(strategy),
            market=request.market,
            requested_range=request.time_range,
            market_data_hash=frame.market_data_hash,
            bar_count=len(frame.time_ms),
            evaluation=evaluation,
        )
    finally:
        market_data_client.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path, help="Path to raw_spec JSON file")
    parser.add_argument("--strategy-id", default="ema_pullback")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--from-ms", required=True, type=int)
    parser.add_argument("--to-ms", required=True, type=int)
    parser.add_argument("--mds-base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    raw_spec = json.loads(args.spec.read_text())
    projection = build_projection(
        raw_spec=raw_spec,
        strategy_id=args.strategy_id,
        ticker=args.ticker,
        timeframe=args.timeframe,
        from_ms=args.from_ms,
        to_ms=args.to_ms,
        mds_base_url=args.mds_base_url,
    )
    envelope = serialize_v2(projection)
    text = json.dumps(envelope, indent=2)
    if args.out is not None:
        args.out.write_text(text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
