## Context

See proposal.md for motivation and measured numbers. `EvaluateStrategyRangeBatch.execute` (evaluate_range_batch.py) currently loops variants and calls `EvaluateStrategyRange.execute` per variant, which internally reaches `EmaPullbackRangeEvaluator.evaluate` -> `EvaluateIndicatorRange.execute` -> `MarketDataServiceClient.load_range`, fetching the market dataset independently every time. All variants in one batch request share one `market: MarketStream` and one `time_range: TimeRange` field already (`StrategyRangeBatchRequest`), so the shared-input identity is already expressed in the existing contract -- this change only removes the redundant re-fetch.

## Goals / Non-Goals

**Goals:**
- One market dataset load per batch request, shared bit-for-bit across all variants.
- No change to single-variant `EvaluateStrategyRange.execute` behavior when called outside a batch.
- No change to indicator computation, strategy semantics, or any layer above L0.

**Non-Goals:**
- Indicator-level (L1) reuse across variants.
- Cross-request or cross-batch caching of any kind.
- Changing `StrategyRangeBatchRequest`'s public shape (it already carries one shared `market`/`time_range`).

## Decisions

**Decision 1 -- where the single load happens.**
`EvaluateStrategyRangeBatch.execute` acquires the market dataset once, before iterating `request.variants`, and passes it down to each variant's evaluation instead of letting each variant trigger its own fetch. This requires a narrow seam: the call path from `EvaluateStrategyRangeBatch` down to `MarketDataServiceClient.load_range` (via `EvaluateStrategyRange` -> `EmaPullbackRangeEvaluator` -> `EvaluateIndicatorRange`) currently has no parameter for "use this already-loaded dataset instead of fetching." The minimal seam is an optional pre-loaded `MarketFrame` threaded through `StrategyRangeRequest` (or an equivalent narrow addition), defaulting to `None` (fetch as today) so the single-variant endpoint's behavior is provably unchanged when the field is absent.

**Decision 2 -- batch-wide failure on load error.**
If the shared market dataset fails to load (MDS unavailable, stream not ready, etc.), the whole batch fails -- not per-variant. This is a deliberate behavior change from today's implicit per-variant independence, made explicit in the modified requirement's second scenario. Alternative considered: keep per-variant fetch-and-fail semantics (each variant independently retries/fails) -- rejected because it silently reintroduces N redundant fetches on any transient failure, defeating the purpose of this change, and because a single shared, batch-scoped market dataset failing for one variant necessarily means it would fail identically for every other variant too (same ticker/timeframe/range) -- there is no case where per-variant retry could produce a different outcome.

**Decision 3 -- identity guarantee, not opportunistic reuse.**
The dataset is loaded exactly once per batch unconditionally (not "reuse if variants happen to match") -- `StrategyRangeBatchRequest` already declares one `market`/`time_range` for the whole batch, so there is no per-variant divergence to detect; the single load simply is the batch's market input. This avoids introducing any cache/key-matching logic (out of scope per proposal.md and per explicit user instruction to do L0 only).

## Risks / Trade-offs

- [Batch-wide failure is a semantic change for callers relying on partial-batch success when MDS is flaky] -> Mitigated: this only changes behavior for MDS-load failures specifically (a shared, deterministic failure mode across all variants in the batch); per-variant strategy-evaluation errors (invalid spec, unsupported component, etc.) continue to produce a per-variant error envelope exactly as today, per the existing "Coarse-grained batch API" scenario.
- [Threading a pre-loaded `MarketFrame` through the request/evaluator chain touches several files even though the change is conceptually small] -> Mitigated by keeping the addition optional/additive (default `None`, single-variant path unaffected) and scoping tasks.md to exactly the files on the call path identified in the audit.

## Migration Plan

Single-step, no feature flag: batch execute path always loads once; no caller-visible contract change beyond the modified requirement's guarantee (which strengthens an existing implicit assumption, not a breaking change to `StrategyRangeBatchRequest`'s shape).
