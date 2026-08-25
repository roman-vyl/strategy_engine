## 1. Implement

- [ ] 1.1 Add the minimal seam to pass an already-loaded `MarketFrame` down the call path (`StrategyRangeRequest` or equivalent narrow addition), optional/defaulting to `None` so single-variant behavior is unchanged when absent, per design.md Decision 1.
- [ ] 1.2 `EvaluateStrategyRangeBatch.execute`: load the market dataset once via the market-data port before the variant loop, using `request.market`/`request.time_range`.
- [ ] 1.3 Thread the loaded `MarketFrame` into each variant's evaluation so `EvaluateIndicatorRange`/`MarketDataServiceClient.load_range` is not called again per variant.
- [ ] 1.4 Batch-wide failure: if the single market-dataset load fails, `EvaluateStrategyRangeBatch.execute` raises/fails the whole batch call, per design.md Decision 2 (not caught into a per-variant error envelope).
- [ ] 1.5 Confirm the single-variant `POST /v1/strategy-evaluations/range` path (`EvaluateStrategyRange.execute` called directly, not via batch) is untouched -- no pre-loaded frame passed, fetch happens as today.

## 2. Unit/contract tests

- [ ] 2.1 Batch with 2+ variants sharing market/time_range: assert the market-data port is invoked exactly once (mock/spy on the port), not once per variant.
- [ ] 2.2 All variants in the batch result reflect the same `market_data_hash` and identical bar data.
- [ ] 2.3 Market-dataset load failure (simulate MDS error) fails the whole batch call (raises), not a per-variant error envelope; existing per-variant strategy-evaluation error scenario (invalid spec etc.) still produces its own error envelope per variant, unchanged.
- [ ] 2.4 Single-variant `EvaluateStrategyRange.execute` (outside batch) still fetches its own dataset -- unaffected by the new optional seam.
- [ ] 2.5 Batch with 1 variant: still loads exactly once (no regression for the trivial case).

## 3. Regression

- [ ] 3.1 Full existing test suite passes unchanged.
- [ ] 3.2 Existing `EvaluateStrategyRangeBatch` tests (variant ordering, per-variant identity/error envelope preservation) continue to pass.

## 4. Repository quality gates

- [ ] 4.1 `pytest` (full suite).
- [ ] 4.2 `ruff check`.
- [ ] 4.3 `mypy`.
- [ ] 4.4 `openspec validate batch-market-dataset-reuse --strict`.
- [ ] 4.5 `git diff --check`.

## 5. Real acceptance

- [ ] 5.1 Real MDS, batch of N>=3 variants sharing market/time_range, varying only strategy-level parameters (e.g. SL/TP) -- confirm the market-data port/HTTP call happens once, not N times (e.g. via request count/timing signal).
- [ ] 5.2 Report total batch wall-clock before/after; do not claim per-layer speedup beyond L0 (indicator/strategy cost per variant is expected to be unchanged by this change).
- [ ] 5.3 Business-result identity: each variant's result unchanged versus today's per-variant-fetch behavior (same market_data_hash, same entries/exit_policy/potential_entries per variant).

## 6. Closeout

- [ ] 6.1 Summarize results in tasks.md.
- [ ] 6.2 Do not archive/PR/merge without a separate explicit instruction.
