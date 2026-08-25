## Why

Real-infra profiling of the Research/Backtest path showed that `EvaluateStrategyRangeBatch` -- the coarse-grained endpoint whose entire purpose is "multiple strategy evaluations sharing one market range" -- fetches the market dataset independently for every variant, even though all variants in one batch request share the exact same `ticker`/`timeframe`/`from_ms`/`to_ms`. Empirically: 5 variants differing only in SL/TP cost 33.2s/variant (166s total) against a single-variant baseline of ~30s -- i.e. the ~21s MDS fetch is paid in full for every variant instead of once per batch. This is pure repeated work: the market dataset (L0) is immutable and identical for all variants in a batch by construction, and does not depend on any strategy-level parameter (indicators, setups, exits, risk management).

## What Changes

- The canonical batch requirement is amended to guarantee that a batch request loads its shared market dataset **once**, and every variant in that batch consumes that same `MarketFrame`/`market_data_hash` -- removing the current explicit disclaimer that "the foundation need not implement shared calculation reuse or scheduling" (narrowed to cover only calculation reuse above L0; the L0 dataset-sharing guarantee becomes a real requirement).
- `EvaluateStrategyRangeBatch.execute` loads the market range once via the market-data port before iterating variants, and passes the resulting `MarketFrame` into each variant's evaluation instead of each variant independently triggering its own MDS fetch.
- Scope is limited to L0 (market dataset) reuse only. No indicator-level (L1), context/setup-level (L2), or any other calculation reuse is introduced by this change -- explicitly out of scope, per the user's directive.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `strategy-engine-foundation-v1`: the "Coarse-grained batch API" requirement changes from "the foundation need not implement shared calculation reuse or scheduling" to a positive guarantee that the market dataset is loaded once per batch and shared identically (same `MarketFrame`, same `market_data_hash`) across all variants in that batch.

## Impact

- Code: `src/strategy_engine/strategies/application/evaluate_range_batch.py` (batch orchestration), and the minimum surface needed in `evaluate_range.py` / `EmaPullbackRangeEvaluator` / `EvaluateIndicatorRange` to accept an already-loaded `MarketFrame` instead of re-fetching it per variant. Exact code-level design is deferred to design.md.
- No change to `FeatureFrame`/`IndicatorPlan` contracts, indicator computation, strategy semantics (contexts/blockers/setups/triggers/entries/exit_policy), the single-variant `POST /v1/strategy-evaluations/range` endpoint, or the live/OpenTrade path.
- No new dependency, no persistent cache, no cross-request state -- the shared `MarketFrame` lives only for the duration of one `EvaluateStrategyRangeBatch.execute()` call.
