# Proposal: Strategy live entry and open trade projections v1

## Why

Strategy Engine currently exposes bounded Research-oriented range evaluation and managed replay:

```http
POST /v1/strategy-evaluations/range
POST /v1/strategy-evaluations/range-batch
POST /v1/strategy-evaluations/managed-replay
```

Those contracts are not sufficient for the live Runtime boundary.

Before a fill, Runtime needs one compact target-bar entry plan containing the planned entry, initial stop, initial take, and the exit profile that must remain locked for that plan. Runtime must not download historical vectors and reassemble this strategy result itself.

After a fill, Runtime needs a stateless open-trade projection from an immutable receipt, but only after ABI has confirmed that the correlated exchange position is still open at webhook-processing time. Engine must reproduce the post-target-bar desired stop, desired take, and strategic close signal without receiving Runtime lifecycle state, exchange order state, or persisting a live session.

Both calculations must use the same live market-history policy. Runtime must not calculate indicator warmup, inspect EMA or HTF requirements, choose a left boundary, or send candles. Engine can satisfy this boundary with the existing MDS stream-bounds and bounded-candle contracts.

## What changes

- Add a shared internal live FeatureFrame acquisition path that:
  - reads existing MDS stream bounds;
  - requires a `ready` stream with non-empty committed bounds;
  - loads the exact half-open range from the earliest committed candle through the requested closed target bar;
  - validates the strategy, builds the existing strategy FeaturePlan, and runs the indicator/HTF feature pipeline once to produce a shared FeatureFrame;
  - leaves strategy-family evaluation and projection assembly to the selected Live Projections adapter.
- Add `POST /v1/strategy-evaluations/live-entry`.
  - It returns target-bar `long` and `short` entry plans or explicit `null` values.
  - Each plan contains the planned entry, initial stop, initial take, source-plan bar, and locked exit profile.
  - It returns the Engine-computed config hash and MDS-owned market-data hash.
- Add `POST /v1/strategy-evaluations/open-trade`.
  - It accepts an immutable executed-trade receipt created from the exact filled live-entry plan plus ABI fill facts.
  - It validates strategy, instance, market, config, time ordering, price geometry, and coverage before calculation.
  - It replays management only from the bar after entry through the requested target bar.
  - Runtime may call it only after an ABI operational-state check confirms that the correlated position is still open.
  - It returns post-target-bar desired protection and strategic close-signal state, not exchange commands or simulated fills.
- Add a start-after-entry managed projection helper without changing public `/managed-replay` semantics.
- Add a strategy-family `Live Projections` adaptation boundary with separate live-entry and open-trade protocols and registries. Generic application use cases select an adapter by strategy family and remain free of strategy-specific branching.
- Allow v1 projection adapters to reuse the existing broad strategy evaluator and full strategy FeaturePlan while returning only use-case-specific internal projection results. Exit-only or entry-only FeaturePlan specialization remains deferred.
- Add locked-profile standard-exit selection and expose only the canonical strategic close-signal result for the confirmed-open trade. Preserve existing strategy-level close-signal composition, but do not run backtest execution-fill arbitration between protective levels and close signals.
- Add typed errors, HTTP DTOs, routes, OpenAPI coverage, unit tests, contract tests, integration tests, compatibility tests, and a v1 performance benchmark.

## Non-goals

- Reintroducing a `current-point` endpoint.
- Changing `/range`, `/range-batch`, or `/managed-replay` wire or calculation semantics.
- Adding a new MDS endpoint or changing MDS hash ownership.
- Sending `from_ms`, warmup, indicator periods, HTF requirements, candle arrays, or calculation origin from Runtime.
- Adding a canonical-window, historical-prefix-versioning, or historical-correction subsystem.
- Persisting Runtime lifecycle or open-trade state inside Engine.
- Implementing the mandatory Runtime-to-ABI operational-state check, ABI order reconciliation, quantity calculation, fill handling, or live-market safety inside Engine.
- Implementing missed-bar catch-up, a durable per-bar cursor, terminal historical exit scanning, or retry-until-success.
- Requiring an incremental indicator cache in v1.

## Compatibility

The two dedicated live contracts follow Runtime's breaking cleanup policy and
do not expose redundant payload versions or MDS provenance hashes. Existing
Research and compatibility endpoints remain unchanged. Existing PotentialEntry
vectors, exit-policy vectors, managed replay, error envelope shape, strategy
validation, and Engine-internal MDS-owned `market_data_hash` semantics remain
authoritative.
