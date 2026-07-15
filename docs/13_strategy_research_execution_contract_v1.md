# Strategy → Research execution contract v1

This change turns the unified seam audit into a versioned wire contract that the Research Service can consume before any simulator is implemented.

## Range evaluation contract

`POST /v1/strategy-evaluations/range` now exposes:

- `contract_version = strategy_evaluation.v1`;
- top-level strategy identity;
- canonical market identity and half-open range;
- `bar_count`;
- `market_data_hash`;
- one `time_ms` item per market bar in `features.time_ms`;
- long/short entry masks;
- signal-exit, stop-loss, take-profit and readiness series;
- component evidence.

The API still does not return fills, trades, fees or PnL.

## Managed replay contract

`POST /v1/strategy-evaluations/managed-replay` now exposes:

- `contract_version = managed_policy_replay.v1`;
- `decision_timing = end_of_bar_effective_next_bar`;
- explicit `effective_from_time_ms` on every managed bar decision.

The last decision has `effective_from_time_ms = null` because the requested range contains no next bar on which it could become active.

## Ownership

Strategy Engine owns decision and policy semantics. Research Service owns OHLC hit detection, arbitration, fills, fees, position lifecycle, PnL and trade records.
