## 1. Implement

- [x] 1.1 Added optional internal-only `market_frame: MarketFrame | None = None` on `StrategyRangeRequest` (strategies/contracts.py) and `IndicatorRangeRequest` (indicators/contracts.py), threaded through `EmaPullbackRangeEvaluator.evaluate`. Defaults to `None` (fetch as today) -- not exposed on any HTTP DTO.
- [x] 1.2 `EvaluateStrategyRangeBatch.__init__` now takes a `MarketDataPort`; `execute` loads the market dataset once via `self._market_data.load_range(request.market, request.time_range)` before the variant loop (after the existing variant-id validation, so malformed batch requests still fail before any load).
- [x] 1.3 `EvaluateIndicatorRange.execute` uses `request.market_frame` when present instead of calling `self._market_data.load_range`; the batch passes the one loaded `MarketFrame` into every variant's `StrategyRangeRequest`.
- [x] 1.4 Shared acquisition failure (uncaught `StrategyEngineError`, e.g. `MarketDataUnavailableError`) propagates out of `EvaluateStrategyRangeBatch.execute` uncaught -- fails the whole batch call, per design.md Decision 2.
- [x] 1.5 Confirmed: `EvaluateStrategyRange.execute` called directly (not via batch) is unaffected -- `market_frame` defaults to `None`, `EvaluateIndicatorRange.execute` falls through to its existing fetch branch.

## 2. Unit/contract tests

New file `tests/test_evaluate_strategy_range_batch.py` (8 tests, all against `EvaluateStrategyRangeBatch`/`EvaluateStrategyRange` directly, not via HTTP):
- [x] 2.1 `test_batch_with_multiple_variants_loads_market_data_exactly_once` (5 variants) + `test_batch_with_one_variant_loads_market_data_exactly_once`.
- [x] 2.2 `test_all_variants_consume_the_exact_same_acquired_market_frame` -- asserts identical `market_data_hash` across all variant results.
- [x] 2.3 `test_shared_market_acquisition_failure_fails_the_whole_batch`, `test_shared_market_acquisition_failure_precedes_per_variant_validation_errors`, `test_per_variant_errors_still_envelope_after_successful_acquisition`.
- [x] 2.4 `test_single_variant_evaluate_strategy_range_still_fetches_its_own_dataset`.
- [x] 2.5 Covered by `test_batch_with_one_variant_loads_market_data_exactly_once`.
- [x] (additional) `test_empty_or_duplicate_variant_ids_still_rejected_before_market_acquisition` -- confirms existing id-validation still runs before the new load, zero market calls on that path.

## 3. Regression

- [x] 3.1 Full existing test suite passes (353 tests).
- [x] 3.2 `tests/test_foundation_api.py::test_batch_preserves_variant_order_and_error_identity` updated: its market range was a placeholder (`BTCUSDT.P`, epoch `0..300000`) that never previously reached MDS because per-variant spec validation failed first -- now that shared acquisition happens before any variant validation (per the approved design), that placeholder range must be real/available. Updated to a real ETHUSDT.P range so the test's original intent (order + per-variant error identity) is preserved; added a new sibling test `test_batch_shared_market_acquisition_failure_fails_whole_batch` using the old placeholder range to explicitly cover the now-intentional whole-batch-failure behavior. All 6 other `EvaluateStrategyRangeBatch`-constructing test files (test_atr_indicator_api.py, test_ema_indicator_api.py, test_adx_dmi_indicator_api.py, test_rsi_indicator_api.py, test_ema_pullback_feature_range_api.py, test_atr_distance_indicator_api.py, test_ema_pullback_managed_api.py, test_live_entry_projection_api.py) updated to pass their existing fake market-data object as the new required constructor argument -- none of them exercise the batch endpoint in their test bodies, so no other behavior changed.

## 4. Repository quality gates

- [x] 4.1 `pytest` (full suite) -- 353 passed.
- [x] 4.2 `ruff check` -- all checks passed.
- [x] 4.3 `mypy` (full `src/`) -- no issues found in 89 source files.
- [x] 4.4 `openspec validate batch-market-dataset-reuse --strict` -- valid.
- [x] 4.5 `git diff --check` -- clean.

## 5. Real acceptance

- [x] 5.1 Real MDS (`http://127.0.0.1:8080`), ETHUSDT.P 5m, pinned deep-in-history immutable window (`TimeRange(1615766400000, 1787513100000)`, same window used in the prior `ema-pullback-setup-vectorization` acceptance) -- 5-variant batch, `EvaluateStrategyRangeBatch.execute`, confirmed a single `market_data_hash` (`fdf59f2a7d...`) and a single bar count (572,489) across all 5 variant results, evidencing the shared `MarketFrame` was loaded once and reused, not re-fetched per variant.
- [x] 5.2 Total batch wall-clock: **AFTER** (batch, shared load) 47.606s for 5 variants (9.521s/variant avg) vs **BEFORE-equivalent** (5 independent `EvaluateStrategyRange.execute` calls, each fetching its own dataset) 167.472s (33.494s/variant avg) -- **3.52x speedup, ~119.9s saved** on this 5-variant batch. This is an L0-only effect: indicator/strategy cost per variant is unchanged by this change, the gain is entirely from eliminating N-1 redundant MDS fetches.
- [x] 5.3 Business-result identity: for every variant, `entries`, `exit_policy`, and `potential_entries` from the batch-shared-load path compared byte-for-byte against the same variant evaluated standalone (its own independent fetch) -- **0 mismatches** across all 5 variants.

## 6. Closeout

- [x] 6.1 Results summarized above (sections 1-5). 353 tests pass, ruff/mypy clean, real pinned-window acceptance confirms single shared acquisition, 3.52x/119.9s saved on a 5-variant batch, exact business-result parity.
- [x] 6.2 Not archived, no PR/merge performed -- awaiting separate explicit instruction per the task.
