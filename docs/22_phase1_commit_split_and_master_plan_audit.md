# Phase 1 commit split and master-plan conformance audit

## 1. Purpose

This file preserves a recommended future commit decomposition for the Phase 1 package and records the post-implementation audit against:

- `docs/master-plan.md`;
- `docs/21_runtime_open_trade_management_plan.md`;
- `openspec/changes/strategy-live-entry-open-trade-v1/design.md`;
- `openspec/changes/strategy-live-entry-open-trade-v1/specs/live-feature-frame-acquisition-v1/spec.md`;
- the implemented Phase 1 code and tests.

It is not a changelog and does not alter runtime behavior.

## 2. Recommended future commit decomposition

### Commit 1 — Add strict MDS stream-bounds contract

Suggested message:

```text
Add strict MDS stream bounds contract
```

Files:

```text
src/strategy_engine/domain/market_data.py
src/strategy_engine/domain/errors.py
src/strategy_engine/ports/market_data.py
src/strategy_engine/adapters/market_data_service/models.py
```

Responsibility:

- introduce transport-neutral `StreamBounds`;
- add readiness and committed-target errors;
- extend the port without changing `load_range()`;
- define the strict wire DTO.

### Commit 2 — Consume MDS bounds over HTTP

Suggested message:

```text
Consume MDS stream bounds in market data adapter
```

Files:

```text
src/strategy_engine/adapters/market_data_service/client.py
tests/test_market_data_client.py
```

Responsibility:

- call the existing MDS bounds endpoint;
- validate contract version and market identity;
- map 404, transport, malformed, and upstream errors.

### Commit 3 — Add shared live FeatureFrame acquisition

Suggested message:

```text
Add shared live FeatureFrame acquisition
```

Files:

```text
src/strategy_engine/strategies/application/load_live_feature_frame.py
src/strategy_engine/strategies/application/__init__.py
src/strategy_engine/service/wiring.py
tests/test_live_feature_frame.py
```

Responsibility:

- validate target alignment and stream readiness;
- derive earliest-committed-to-target range;
- reuse bounded candle loading and existing feature calculation;
- validate exact target-final-bar semantics;
- propagate the MDS-owned `market_data_hash`.

### Commit 4 — Close Phase 1 OpenSpec and document implementation decisions

Suggested message:

```text
Close live frame Phase 1 OpenSpec tasks
```

Files:

```text
openspec/changes/strategy-live-entry-open-trade-v1/tasks.md
openspec/changes/strategy-live-entry-open-trade-v1/design.md
openspec/changes/strategy-live-entry-open-trade-v1/specs/live-feature-frame-acquisition-v1/spec.md
docs/21_runtime_open_trade_management_plan.md
docs/22_phase1_commit_split_and_master_plan_audit.md
```

Responsibility:

- mark Slice 1 complete;
- align normative wording with the implemented FeatureFrame boundary;
- preserve the commit-splitting and conformance record.

## 3. Master-plan conformance

### 3.1 Conforms without qualification

Phase 1 conforms to the master plan in the following areas:

1. **Engine remains stateless.** No Runtime lifecycle, ABI order state, position quantity, or previous managed state is introduced.
2. **No new MDS endpoint.** The implementation consumes existing bounds and bounded-candle contracts.
3. **Runtime does not own history boundaries.** The internal loader derives `from_ms` from MDS earliest committed coverage and derives `to_ms` from the webhook target.
4. **Research contracts remain unchanged.** `load_range()`, `/range`, `/range-batch`, and `/managed-replay` are not modified.
5. **One bounds read plus one bounded candle read.** The two-read architecture and its race semantics are preserved.
6. **Target need not be absolute latest.** A committed older target is accepted and the frame ends exactly at that target.
7. **MDS provenance remains authoritative.** `market_data_hash` is propagated without recalculation.
8. **Existing calculation code is reused.** Phase 1 does not introduce a second indicator or HTF implementation.
9. **Application boundaries remain direct.** Strategy application calls Indicator application in-process and does not use loopback HTTP.
10. **OpenSpec Slice 1 acceptance is covered by tests.** Ready, non-ready, empty, out-of-range, malformed, mismatched, incomplete, and race cases are exercised.

### 3.2 Intentional implementation refinement

One wording-level divergence was found after implementation:

```text
Earlier wording:
LoadLiveFeatureFrame also runs EMA Pullback strategy evaluation and returns evaluated strategy objects.

Implemented boundary:
LoadLiveFeatureFrame ends at a validated FeatureFrame.
The calling live use case runs EMA Pullback strategy evaluation exactly once.
```

This divergence is intentional and is now reflected in the OpenSpec and maintained plan. Reasons:

- `live-entry` and `open-trade` need different projections from the same FeatureFrame;
- putting strategy interpretation into the shared loader would create an overly broad generic result bundle;
- the cleaner boundary is market-data plus feature acquisition in Phase 1, strategy projection in later slices;
- strategy formulas remain reused, not duplicated;
- the invariant remains one FeaturePlan/FeatureFrame calculation and one strategy evaluation per completed live request.

This is a layering refinement, not a change to external behavior or history policy.

### 3.3 Minor non-semantic ordering difference

The implementation validates target alignment before validating the strategy envelope, while the design listed strategy validation first. Both happen before any MDS call. This difference is intentional only as fail-fast input validation and has no contract or ownership impact. No documentation change is required.

### 3.4 No unresolved master-plan divergence after synchronization

After updating the FeatureFrame-boundary wording, no unresolved Phase 1 divergence remains between implementation, master plan, maintained architecture documents, and the OpenSpec Slice 1 requirements.

## 4. Deferred by design

The following are not Phase 1 omissions; they remain assigned to later slices:

- target-bar PotentialEntry and locked-profile projection;
- `/live-entry` HTTP surface;
- immutable executed-trade receipt;
- receipt/config validation before MDS access;
- start-after-entry managed replay;
- locked-profile target exits and desired-state composition;
- `/open-trade` HTTP surface;
- production performance benchmarking and cache decision.

## 5. Verification record

Phase 1 verification at completion:

```text
pytest: 141 passed
ruff: pass
openspec validate --strict: pass
```

Repository-wide mypy still reports pre-existing baseline errors in legacy/current EMA Pullback and authoring code. Phase 1 introduced no new reported mypy errors in its new files.


## 6. Phase 2 and live-entry HTTP commit decomposition

The Phase 2 package can be split into the following future commits after the Phase 1 commits above.

### Commit 5 — Restore PotentialEntry projection contracts

Suggested message:

```text
Restore EMA Pullback PotentialEntry projection
```

Responsibility:

- preserve the previously approved entry/stop/take vectors;
- keep range evaluation wire compatibility;
- provide the canonical projection input used by live-entry.

### Commit 6 — Add transport-neutral live-entry projection

Suggested message:

```text
Add target-bar live entry projection
```

Files include the live-entry contracts, application use case, shared precomputed-frame evaluator changes, wiring, and application/parity tests.

Responsibility:

- evaluate the existing EMA Pullback strategy over the Phase 1 FeatureFrame;
- project one atomic target-bar plan or `null` per side;
- preserve Engine-owned config and market-data provenance.

### Commit 7 — Expose live-entry HTTP contract

Suggested message:

```text
Expose live entry projection over HTTP
```

Files:

```text
src/strategy_engine/adapters/http/models.py
src/strategy_engine/adapters/http/strategy_routes.py
tests/test_live_entry_projection_api.py
tests/test_live_entry_projection.py
```

Responsibility:

- expose `POST /v1/strategy-evaluations/live-entry`;
- forbid Runtime-owned history fields;
- serialize stable `long` and `short` plan keys;
- publish request and response schemas through OpenAPI;
- preserve the existing typed application error envelope.

### Commit 8 — Close OpenSpec Slice 2

Suggested message:

```text
Close live entry projection OpenSpec slice
```

Files:

```text
openspec/changes/strategy-live-entry-open-trade-v1/tasks.md
docs/22_phase1_commit_split_and_master_plan_audit.md
```

Responsibility:

- mark all Slice 2 tasks complete only after application, parity, HTTP, edge-case, and OpenAPI tests pass;
- retain the future commit decomposition for the cumulative package.

## 7. Post-Phase-2 conformance note

The live-entry HTTP increment introduces no architecture divergence from the master plan:

- the route is a thin adapter over `EvaluateLiveEntryProjection`;
- it does not accept `from_ms`, `to_ms`, warmup, FeaturePlan, indicators, HTF requirements, or candles;
- it does not create ABI commands or Runtime state;
- the existing Phase 1 `bounds + candles` path remains the sole live history acquisition path;
- the existing range endpoints and managed-replay endpoint remain unchanged;
- Engine-owned `source_config_hash` and MDS-owned `market_data_hash` remain authoritative.

No intentional Phase 2 divergence requires a master-plan correction.
