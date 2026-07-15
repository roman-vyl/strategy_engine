# Practical extraction and cutover plan

## Non-destructive migration rule

The original BBB repository remains unchanged and independent. Selected files are copied into `legacy_source/bbb/` only as an immutable reference; they are never connected to the new runtime.

The new repository uses two distinct trees:

```text
legacy_source/
  bbb/research/strategies/ema_pullback/   # untouched copied evidence
  bbb/tests/                              # selected parity references

src/strategy_engine/
  ...                                     # clean working implementation
```

The raw copy is not an importable production package and is never edited except when intentionally replacing it with a newer audited snapshot.

## Step 0 — repository foundation

Create:

```text
strategy_engine/
  docs/
  legacy_source/
  src/strategy_engine/
  tests/
  scripts/
  openspec/changes/
```

Record the source snapshot SHA-256 in every copy manifest.

## Step 1 — exact raw copy

Copy the complete directory:

```text
BBB: research/strategies/ema_pullback/
 -> strategy_engine: legacy_source/bbb/research/strategies/ema_pullback/
```

Also copy selected direct strategy tests into `legacy_source/bbb/tests/`. Do not copy the complete BBB repository, Data Engine, frontend, reports or experiment results.

This copy is intentionally allowed not to import or run in the new repository.

## Step 2 — freeze golden fixtures before refactoring

Create fixtures from the unchanged BBB implementation for:

- `FeaturePlan` serialization;
- enriched indicator series;
- HTF alignment and warmup;
- contexts;
- component masks;
- entry/exit/profile outputs;
- managed policy decisions;
- representative final BBB simulated trades.

Fixtures must include config hash, snapshot hash and exact source ranges.

## Step 3 — create engine-owned foundational contracts

Before porting formulas, create clean contracts:

```text
src/strategy_engine/contracts/
  market.py            # MarketFrame, TimeRange, timeframe identity
  indicators.py        # IndicatorPlan, FeatureFrame, validity metadata
  strategy.py          # StrategySpec identity, evaluation request/result
  state.py             # StrategyState, PositionState
  decisions.py         # EntryDecision, ExitDecision, ProtectionDecision
```

These contracts must not import BBB, Data Engine, research_api or vectorbt.

## Step 4 — port Indicator Engine first

Initial target modules:

```text
src/strategy_engine/indicators/
  catalog.py
  planning.py
  batch/
    calculations.py
    resampling.py
    alignment.py
  api/
```

Port semantics from `features/plan.py` and `features/calculations.py` while replacing Data Engine timeframe imports with engine contracts.

Acceptance: exact plan, value, warmup and HTF-alignment parity.

## Step 5 — add Indicator API at the first seam

Implement:

```text
GET  /v1/indicators
GET  /v1/indicators/{indicator_id}/schema
POST /v1/indicator-plans/validate
POST /v1/indicator-evaluations/range
```

The internal Strategy Engine calls Indicator Engine directly. HTTP is for BBB and external consumers only.

## Step 6 — port strategy specification and pure components

Port:

- spec/config validation;
- component registry;
- contexts;
- setups;
- direction/blockers/triggers;
- signal exits and distance policies;
- entry/exit composition.

Create a batch `StrategyEvaluator` that accepts a strategy spec plus `FeatureFrame` and returns bar-aligned decisions/evidence.

## Step 7 — split managed policy from execution

Do not copy `trade_runtime.py` or managed execution files wholesale into final core.

Create new engine contracts:

```text
PositionState -> ManagedPolicyEvaluator -> Protection/Exit decisions + NextStrategyState
```

Keep OHLC hit detection, fill price, same-bar arbitration and trade accounting in BBB.

## Step 8 — add Strategy API at the second seam

Implement:

```text
GET  /v1/strategies
GET  /v1/strategies/{strategy_id}/schema
POST /v1/strategies/{strategy_id}/validate
POST /v1/strategy-evaluations/range
```

`POST /v1/strategy-evaluations/range` builds the feature plan and calls Indicator Engine internally. BBB should not orchestrate one HTTP request per indicator/component.

## Step 9 — independent consumer integration

- add Strategy Engine API clients to the new consumer service;
- adapt `StrategyEvaluationResult` into consumer-owned execution inputs;
- compare against frozen parity fixtures derived from the immutable BBB reference source;
- keep the original BBB repository completely outside the new runtime and deployment graph.

## Step 10 — BBB cutover

Only after acceptance:

- switch BBB services to API adapters;
- keep Workbench endpoints unchanged;
- make new engine catalogs authoritative;
- remove legacy indicator/strategy calculations from BBB in a separate delete-only phase.

## Step 11 — future bar-to-bar runtime

> **Decision under review (Strategy Runtime redesign):** The Runtime wrapper remains the mandatory mediator between Strategy Engine and Abi; no direct Engine → Abi contract is intended. However, the incremental `evaluate_bar(confirmed_bar, previous_*_state, position_state)` shape and the checkpoint/replay responsibilities below predate the approved standalone `strategy_runtime` orchestration model. They MUST be redesigned before implementation and MUST NOT be treated as an approved runtime contract.


Runtime wrapper is a later program. The engine must reserve contracts for:

```text
evaluate_bar(
  confirmed_bar,
  previous_indicator_state,
  previous_strategy_state,
  position_state
) -> decisions + next states
```

The wrapper, not the strategy, will own:

- MDS subscription;
- deduplication;
- restart/replay;
- checkpoint persistence;
- signal idempotency;
- Abi delivery.

No incremental implementation is accepted until batch versus incremental parity can be proven.


## Normative cross-service seam

The exact two-sided cut between Strategy Engine and Research Service is defined in `docs/12_unified_strategy_research_seam_contract.md`.
