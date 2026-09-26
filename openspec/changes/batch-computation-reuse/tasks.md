## 1. Parity harness and golden corpus

- [x] 1.1 Build a golden-recorder harness (outside production source, or in a clearly separate test-only module) that runs the current evaluator per candidate and captures, per node: indicator series as float64 bytes, context/gate/direction/blocker/setup/trigger masks, entries, every `ExitPolicyEvaluation` field, the projection object, and the exact NDJSON bytes per line.
- [x] 1.2 Assemble the real-batch corpus: width-only sweep, untouched-lookback-only sweep, TP/SL-only sweep, and the combined width×untouched×TP/SL 3D grid, sourced from real Research Service request artifacts.
- [x] 1.3 Assemble a synthetic structurally-different-specs corpus (varying EMA period, ATR configuration, context/setup/exit structure) to exercise scenarios the real corpus doesn't cover.
- [x] 1.4 Assemble alias/collision probes: missing-default vs explicit-default parameter values, timeframe aliasing (`"base"` vs the literal base timeframe string), source-distinct indicators with identical period (close vs open EMA), and any other hidden-dependency category identified by the architecture audit.
- [x] 1.5 Define the comparison rules the harness enforces: bitwise float comparison (`tobytes`), exact boolean comparison, NaN/None-position comparison, and failure comparison (category + message/payload + evaluation-sequence position + caught-vs-propagated behavior, never Python exception object or traceback identity). For downstream Research Service artifacts, define comparison as semantic-content equality after excluding non-deterministic fields (`run_id`, timestamps) — not byte-identical comparison of the full artifact.
- [x] 1.6 Run the harness against the current (pre-change) evaluator on the full corpus and store the golden outputs as the parity baseline for all later stages.

## 2. Shared range-invariant common arrays

- [x] 2.1 Design the per-range-batch common-array bundle (float64 OHLCV, `DatetimeIndex`, `time_ms`) that replaces repeated per-node Decimal→float conversion (`indicators/implementations/frame_ops.py:market_frame_to_dataframe`, and the per-node `_market_values`/`_frame_dataframe` conversions in `setups.py`, `triggers.py`, `exits.py`).
- [x] 2.2 Wire the shared bundle into the batch evaluation path so every node that today re-derives float64 arrays from the `MarketFrame` consumes the shared bundle instead.
- [x] 2.3 Run the golden-corpus harness against this stage; confirm bit-identical output (including at the DataFrame/array level, not just final NDJSON) before proceeding.
- [ ] 2.4 Converge the single-spec (non-batch) entrypoint onto the same shared common-array bundle and, once later stages land, the same `EvaluationContext` mechanism as the batch path — the target architecture has no permanent separate preparation path for single-spec. It is acceptable for the single-spec entrypoint to keep its current implementation temporarily while later groups are still being migrated node family by node family, but this task is not complete until single-spec is running on the shared context as a context-of-one.

## 3. Semantic node identity (`resolve()`/`NodeSpec`), no memoization yet

- [x] 3.1 Define the `NodeSpec` identity representation (frozen, hashable value: node kind + implementation version, normalized effective parameters, upstream identities, side only when read) per design.md D2.
- [x] 3.2 For each node family, add a `resolve()` that derives its `NodeSpec` from the raw spec fragment using the *same* default-normalization logic as the existing `compute()` (shared helper, not duplicated defaults), starting with indicators (`indicators/implementations/range_evaluator.py`, `strategies/ema_pullback/feature_plan.py`).
- [x] 3.3 Extend `resolve()` to context/context-consumption gate, direction, blocker (`strategies/ema_pullback/contexts.py`, `context_consumption.py`, `direction_blockers.py`).
- [x] 3.4 Extend `resolve()` to setup components, including the width-specific side-free prefix/suffix split identified by the audit (`strategies/ema_pullback/setups.py`).
- [x] 3.5 Extend `resolve()` to triggers (`strategies/ema_pullback/triggers.py`).
- [x] 3.6 Extend `resolve()` to exit-rule numeric evaluation, per-profile aggregate, and profile-select nodes (`strategies/ema_pullback/exits.py`).
- [x] 3.7 Add the identity-soundness test suite, checked against normalized inputs and dependency structure (never against output-value equality): (a) assert semantically equivalent normalized inputs/dependencies produce the same identity (e.g. missing-default vs explicit-default parameter values); (b) assert semantically distinct computation never produces the same identity (e.g. close vs open EMA with identical period, timeframe aliasing resolved so equivalent timeframes match and non-equivalent ones don't); (c) assert same identity implies bit-identical computed result. Explicitly include a case where two distinct computations coincidentally produce equal output values and assert they still receive different identities.
- [x] 3.8 Confirm zero behavior change at this stage (memoization is not yet enabled) via the golden-corpus harness.

## 4. Batch-scoped `EvaluationContext` and incremental memoization

- [ ] 4.1 Implement the `EvaluationContext`: per-range-batch object holding the shared common-array bundle (from group 2) and a memo of `identity → immutable result`, scoped to the market/range identity, per design.md D1/D2.
- [ ] 4.2 Implement refcount computation: given all candidates' resolved `NodeSpec`s for a batch, compute per-identity reference counts before streaming begins, and evict a memoized result once its refcount reaches zero (design.md D5).
- [ ] 4.3 Implement failure memoization and replay: a node identity that fails during computation records an immutable failure representation (category, message/payload, propagation behavior — not the Python exception object itself) and reproduces the same observable failure for every later dependent candidate, at the same point in that candidate's evaluation sequence as today (design.md D6). This does not require reusing the same exception object or traceback. Preserve the existing `StrategyEngineError`-only catch boundary in `_stream_variants` and the uncaught `AssertionError` propagation from the projection step unchanged.
- [ ] 4.4 Enable memoization for the indicator node family first (feature-plan indicators). Add a memo-capacity toggle so the same evaluator can run with memoization on or off.
- [ ] 4.5 Run the golden-corpus harness with memo OFF vs memo ON (same code) for the indicator family; confirm bit-identical results including on heterogeneous and shuffled-order batches, before enabling the next family.
- [ ] 4.6 Enable memoization for direction/blocker/trigger/setup-component nodes. Re-run the memo OFF vs ON parity check for this family before proceeding.
- [ ] 4.7 Enable memoization for exit-rule/aggregate/select nodes. Re-run the memo OFF vs ON parity check for this family.
- [ ] 4.8 Run the full golden-corpus harness end to end with all families memoized, across homogeneous, partially-shared, fully heterogeneous, shuffled-order, and duplicated-spec batch shapes.

## 5. Batch integration and end-to-end validation

- [ ] 5.1 Wire `EvaluationContext` into `strategies/application/evaluate_range_batch.py:EvaluateStrategyRangeBatch.execute` so it is constructed once per range-batch call and used by `_stream_variants` for every candidate, without changing NDJSON emission order or per-variant error isolation.
- [ ] 5.2 Confirm the single-spec entrypoint (`strategies/application/evaluate_range.py`) still functions correctly as a context-of-one, per the "one evaluation path" requirement.
- [ ] 5.3 Run the full golden-corpus harness against the fully-integrated evaluator (real + synthetic + alias corpora), including a batch-of-one-candidate scenario compared against the single-spec entrypoint's output for the same input.
- [ ] 5.4 Run an end-to-end Research Service batch (`RunBatchExperiment`) against both the pre-change and post-change Strategy Engine, and compare every persisted run artifact for semantic-content equality (trades, fills, fees, PnL, cumulative R, metrics, provenance-relevant content) after excluding non-deterministic fields (`run_id`, timestamps) — not byte-identical comparison of the full artifact — to confirm downstream parity.

## 6. Benchmark and follow-up decision

- [ ] 6.1 Measure the real computation counts (unique vs total node evaluations) on the representative real batches (width, untouched, TP/SL, combined 3D grid) and compare against the audit's predicted counts.
- [ ] 6.2 Measure actual wall-clock effect on the same representative batches, native (no ARM64/parallelism changes bundled in).
- [ ] 6.3 Document the measured results and use them to decide, as a separate follow-up (not part of this change), whether output-diet, parallelism, or ARM64 migration are worth pursuing next.
