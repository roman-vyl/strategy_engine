# Tasks: Strategy live entry and open trade projections v1

## Slice 1 — MDS bounds consumer and shared live frame

- [x] Add strict `StreamBounds` domain/adapter models for `market_stream_bounds.v1`.
- [x] Extend `MarketDataPort` with `load_bounds(market)` while preserving `load_range()`.
- [x] Implement MDS bounds HTTP consumption and typed mapping for unknown, non-ready, unavailable, and malformed responses.
- [x] Add `LoadLiveFeatureFrame` with target alignment, ready-state, bound, range, and target-final-bar validation.
- [x] Reuse the existing feature-plan, indicator, and HTF feature pipeline exactly once per live request, leaving EMA Pullback strategy evaluation to the calling live use case.
- [x] Preserve the exact MDS-owned `market_data_hash` inside the shared live-frame bundle without recalculation.
- [x] Test a target equal to latest and a target older than latest.
- [x] Test empty bounds, non-ready state, target outside bounds, identity mismatch, gapped/incomplete candles, and the bounds/candles race.

## Slice 2 — Live-entry projection

- [x] Add transport-neutral `LiveEntryProjectionRequest`, `LiveEntryPlan`, and `LiveEntryProjectionResult` contracts.
- [x] Implement `EvaluateLiveEntryProjection` over `LoadLiveFeatureFrame`.
- [x] Read PotentialEntry and locked profile from the same target index.
- [x] Return stable `long` and `short` keys with complete plans or `null`.
- [x] Enforce normalized decimal serialization, supported profiles, and side-relative price geometry.
- [x] Add `POST /v1/strategy-evaluations/live-entry` request/response models, route, wiring, and OpenAPI contract.
- [x] Test long, short, neutral, disabled-side, incomplete-triple, invalid-geometry, and config-hash behavior.
- [x] Add parity tests proving the live plan matches target-index range evaluation on the same full-ready-history fixture.

## Slice 3 — Receipt contract and pre-market validation

- [x] Add immutable `ExecutedTradeReceipt` domain and HTTP models with the specified identity, time, price, and profile fields.
- [x] Validate IDs, enums, alignment, time ordering, normalized decimal text, and side-relative stop/entry/take geometry.
- [x] Validate request strategy, instance, and market against the receipt before any MDS call.
- [x] Add typed `trade_contract_mismatch` and `trade_history_unavailable` application errors and stable HTTP mappings.
- [x] Test that all pre-market validation failures perform zero MDS reads.

## Slice 4 — Start-after-entry managed projection

- [x] Extract or add a pure internal managed replay helper with explicit `entry_index + 1` start semantics.
- [x] Keep public `/managed-replay` behavior and fixtures unchanged.
- [x] Exclude entry-bar OHLC from MFE/MAE and all managed/close rules.
- [x] Preserve `bars_in_trade = 1` on entry and `bars_in_trade = 2` on the first post-entry bar.
- [x] Use `planned_entry_price` for all entry-relative managed mathematics while retaining executed price only as receipt provenance.
- [x] Seed desired stop/take from exact receipt Decimal levels, avoid no-op float round trips, and enforce tighten-only stop composition.
- [x] Test entry-target, first-post-entry, planned/executed divergence, phase, MFE/MAE, stop, and take semantics.

## Slice 5 — Confirmed-open desired protection and close signal

- [x] Add locked-profile standard signal selection for receipt side at target index.
- [x] Reuse canonical strategy-level composition/attribution only among target-active strategic close rules.
- [x] Do not run backtest execution-fill arbitration between protective-level hits and strategic close signals in the live open-trade path.
- [x] Build `OpenTradeProjectionResult` around `desired_protection`, `close_signal`, provenance, and diagnostics.
- [x] Define desired stop/take as post-target-bar levels effective after target processing, not as inferred fills inside target.
- [x] Confirm that intermediate transient strategic exits are not recovered and document the accepted v1 trading risk in tests.
- [x] Test multiple simultaneous strategic close rules and preserve existing canonical strategy attribution.
- [x] Test that the result contains no simulated fill, exit price/time, PnL, ABI commands, quantity, order IDs, or exchange-specific parameters.
- [x] Create a dedicated strategy-family `Live Projections` package or equivalent physical boundary.
- [x] Define separate live-entry and open-trade adapter protocols with separate registries.
- [x] Register EMA Pullback in both registries and remove strategy-family branching from generic live application use cases.
- [x] Move EMA Pullback-specific live-entry projection assembly behind the live-entry adapter.
- [x] Move EMA Pullback-specific open-trade projection, locked-profile close selection, and managed-result composition behind the open-trade adapter.
- [x] Introduce internal strategy-specific projection result types and keep public generic result composition in the application layer.
- [x] Preserve the v1 full-history FeatureFrame and broad evaluator reuse; do not introduce entry-only or exit-only FeaturePlan specialization in this slice.
- [x] Add architecture tests proving unsupported strategy families fail through registry lookup and that generic use cases contain no EMA Pullback-specific branches.
- [x] Re-run live-entry parity, open-trade composition, managed replay compatibility, and the full repository suite after the refactor.
- [x] Treat missing, `diagnostic_only`, and `managed` mode identically in the live open-trade adapter while preserving public `/managed-replay` compatibility.
- [x] Map unknown MDS streams to `market_stream_not_found`, publish HTTP 404 for both live endpoints, and add inverted-bounds regression coverage.

## Slice 6 — Open-trade HTTP surface

- [x] Add `POST /v1/strategy-evaluations/open-trade` request/response models, route, wiring, serialization, and OpenAPI contract.
- [x] Validate source-plan, entry, and target coverage after live frame acquisition.
- [x] Return exact typed errors without partial desired state.
- [x] Test deterministic identical retries over the same market-data hash.

## Slice 7 — Compatibility integration and performance gates

- [x] Remove the redundant payload-level `contract_version` from both Runtime-facing live projection responses while preserving MDS and Research endpoint version fields.
- [x] Remove `market_data_hash` from both Runtime-facing live projection results and HTTP schemas while preserving internal MDS/FeatureFrame and Research provenance.
- [x] Remove `source_config_hash` from both live responses and the open-trade receipt, including its syntax and mismatch validation, while preserving Research `config_hash`.
- [x] Remove the unused `abi_entry_correlation` echo from the open-trade receipt and reject the retired field at the strict HTTP boundary.
- [x] Remove Runtime-owned `trade_id` from open-trade receipt/result and split the identity-free managed core from the unchanged Research `/managed-replay` attribution wrapper.
- [ ] Prove `/range`, `/range-batch`, PotentialEntry vectors, exit-policy vectors, and `/managed-replay` remain unchanged.
- [ ] Add an opt-in sibling-repository Engine-to-MDS HTTP smoke harness as a temporary bridge; keep it outside normal `make verify`.
- [ ] Design and create a dedicated multi-repository integration/system-test service, then add Engine-to-MDS integration tests using real bounds and bounded-candle wire DTOs.
- [ ] Add end-to-end Engine HTTP tests for live-entry and open-trade.
- [ ] Verify Engine does not import Runtime or ABI packages.
- [ ] Benchmark maximum configured ready history on 5m and 1h, multiple active instances, latency, memory, and MDS payload size.
- [ ] Record whether internal caching is needed before production without changing the public v1 contracts.
- [ ] Update maintained architecture and API documentation.
- [ ] Run the full repository verification suite.
- [x] Run strict OpenSpec validation for `strategy-live-entry-open-trade-v1`.

## Acceptance

- [ ] Both new endpoints use one shared earliest-ready-to-target history policy.
- [ ] Runtime supplies no history boundary, warmup, FeaturePlan, or candle array.
- [ ] Live-entry returns a complete target-bar plan or `null` per side.
- [ ] Runtime calls open-trade only after ABI reports the correlated position is currently open.
- [ ] Open-trade accepts an immutable receipt and returns only post-target-bar desired protection plus target-active strategic close signal.
- [ ] Management starts after the entry bar and uses planned-price basis.
- [ ] Receipt config binding is validated before MDS access.
- [ ] Source-plan and entry coverage failures are explicit errors.
- [ ] Missed transient exits remain an explicitly tested accepted trading risk v1.
- [ ] Protective-order fills are ABI/exchange facts and are never inferred by the live open-trade path from OHLC.
- [ ] Generic live application use cases resolve strategy-family adapters through separate live-entry and open-trade registries.
- [ ] Strategy-specific evaluator parsing is encapsulated inside the corresponding Live Projections adapter.
- [ ] V1 continues to use the shared full-history FeatureFrame and may reuse the broad evaluator without introducing specialized FeaturePlans.
- [ ] Existing public evaluation endpoints remain compatible.
