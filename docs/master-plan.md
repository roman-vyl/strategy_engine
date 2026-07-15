# Strategy Engine master plan

## 1. Назначение программы

Создать в отдельном репозитории `/Users/mcroma/BBB_project/strategy_engine` независимую работающую систему, которая станет единственным авторитетным владельцем:

- расчёта strategy/research indicators;
- построения feature plan;
- strategy config parsing и validation;
- strategy contexts;
- direction, blockers, setups, triggers и risk semantics;
- entry, exit и protection decisions;
- managed-exit policy semantics;
- strategy/indicator catalog contracts;
- batch evaluation API;
- в дальнейшем — incremental bar-to-bar core, вызываемый отдельным Runtime wrapper.

BBB остаётся работающей legacy-системой до самого конца cutover. Во время создания нового engine код из BBB не удаляется и не заменяется. BBB продолжает выполнять backtests, строить reports и обслуживать Workbench через существующие пути.

## 2. Основной способ переноса

Работа выполняется не переписыванием с нуля, а последовательным semantic port:

1. Сохранить неизменённый physical copy исходного BBB slice.
2. Для каждого переносимого метода определить текущего caller, точную сигнатуру, входные данные, выходные данные и downstream-потребителей.
3. Определить целевой responsibility owner.
4. Скопировать реализацию в чистый модуль нового репозитория.
5. Удалить из копии BBB-only ответственность выше или ниже выбранного шва.
6. Заменить внешние зависимости явными ports.
7. На repository/process seam сразу создать FastAPI contract.
8. Добавить parity test против неизменённого BBB.
9. Только после полной готовности нового engine хирургически переключать BBB с локального вызова на HTTP client.
10. После acceptance удалить старую реализацию из BBB, не оставляя два production-authoritative пути.

## 3. Зафиксированный source slice

Из snapshot `project_snapshot_20260711.zip` скопировано без изменений:

```text
legacy_source/bbb/research/strategies/ema_pullback/
legacy_source/bbb/tests/
legacy_source/bbb/copy_manifest.json
```

Provenance:

- archive SHA-256: `3020cf491a185e495c16b77caddb9e8c06acb7e6577d6b6d9fe5efc9373046e6`;
- 61 strategy package files;
- 23 selected helper/parity test files;
- 84 manifest entries;
- каждый copied file имеет SHA-256.

`legacy_source` является immutable evidence и porting reference. Рабочий код создаётся только под `src/strategy_engine`.

## 4. Текущий естественный шов BBB

В `research/strategies/ema_pullback/execution/backtest.py::run_strategy_spec` текущая последовательность такова:

```text
EmaPullbackStrategySpec + OHLCV
  → build_feature_plan_from_strategy_spec
  → add_feature_columns_from_plan
  → build_context_bundle_for_spec
  → build_signals_from_spec
  → build_exit_outputs_from_spec
──────────────────────────────────────────── primary strategy seam
  → vectorbt or managed execution loop
  → fill/arbitration
  → trade records
  → fees/slippage/PnL/metrics
  → diagnostics/report/Workbench artifacts
```

Целевой Strategy Engine владеет всем до primary seam. BBB владеет всем после него, кроме отдельно оговорённого managed compatibility replay adapter.

Подробный current-call и FastAPI replacement audit находится в:

```text
docs/08_detailed_bbb_contract_and_fastapi_replacement_audit.md
```

## 5. Целевые внутренние модули

```text
src/strategy_engine/
├── domain/
│   ├── market.py
│   ├── ranges.py
│   ├── values.py
│   └── errors.py
├── indicators/
│   ├── domain/
│   ├── planning/
│   ├── batch/
│   ├── incremental/          # зарезервировано, не первый этап
│   ├── catalog/
│   └── application/
├── strategies/
│   ├── contracts/
│   ├── catalog/
│   └── ema_pullback/
│       ├── config/
│       ├── context/
│       ├── components/
│       ├── evaluation/
│       ├── managed/
│       └── application/
├── ports/
│   ├── market_data.py
│   └── evaluation_artifacts.py
├── adapters/
│   ├── market_data_service/
│   └── http/
└── service/
    ├── app.py
    ├── wiring.py
    └── settings.py
```

Indicator Engine и Strategy Engine являются разными application boundaries, но в первой системе живут в одном Python package и одном FastAPI service. Strategy application вызывает Indicator application напрямую, не через loopback HTTP.

## 6. Целевые внешние API boundaries

### 6.1 Strategy config/catalog

```http
GET  /v1/strategies
GET  /v1/strategies/ema_pullback/schema
GET  /v1/strategies/ema_pullback/catalog
POST /v1/strategies/ema_pullback/validate
```

Они заменяют BBB-owned detailed validation и Composer catalog semantics.

### 6.2 Indicator catalog/evaluation

```http
GET  /v1/indicators
GET  /v1/indicators/{indicator_id}/schema
POST /v1/indicator-plans/validate
POST /v1/indicator-evaluations/range
```

Они обслуживают Strategy Engine, BBB research tooling и Workbench через BBB BFF.

### 6.3 Strategy range evaluation

```http
POST /v1/strategy-evaluations/range
POST /v1/strategy-evaluations/range-batch
```

Один coarse-grained call заменяет группу локальных вызовов feature/context/signal/exit. `range-batch` сохраняет текущую семантику BBB «один shared market range — несколько strategy variants».

### 6.4 Managed compatibility replay

```http
POST /v1/strategy-evaluations/managed-replay
```

Это временный compatibility adapter, необходимый потому, что текущий managed path итеративно связывает strategy policy с same-bar execution arbitration. Он переносится отдельно от чистого Strategy Engine core и не становится контрактом live Runtime.

### 6.5 Future runtime boundary

> **Decision under review (Strategy Runtime redesign):** The Runtime wrapper remains outside Strategy Engine and remains the only path toward Abi. The provisional Engine-hosted runtime-instance endpoints and incremental session assumptions below are not approved contracts. They must be replaced or explicitly re-approved after the standalone `strategy_runtime` → Strategy Engine current-point contract is designed.


Концептуально резервируется, но не входит в первые OpenSpec:

```http
POST /v1/runtime/strategy-instances
POST /v1/runtime/strategy-instances/{id}/bars
```

В реальной реализации Runtime wrapper должен вызывать Strategy Engine core внутри процесса или через coarse-grained session protocol. Один HTTP call на каждую внутреннюю component function запрещён.

## 7. Фазы программы

## Phase 0 — source provenance and immutable copy

Статус: выполнено в песочнице.

Результаты:

- полный physical copy;
- selected parity tests;
- file hash manifest;
- классификация direct/mixed/BBB-only;
- исходные audit docs.

Acceptance:

- copied contents byte-identical snapshot;
- BBB не изменён;
- legacy copy не импортируется production package.

## Phase 1 — super-detailed BBB contract audit

Статус: начат; текущая версия зафиксирована в `docs/08_*`.

Для каждого шва обязательно документируются:

- точный caller и его file/function;
- вызываемый method и snapshot line;
- аргументы и их concrete shape;
- возвращаемый type и поля;
- downstream usage каждого поля;
- BBB-only поля;
- target owner;
- целевой FastAPI endpoint;
- request JSON;
- response JSON;
- compatibility adapter в BBB;
- parity fixture и acceptance.

Audit закрывается только после проверки всех direct и mixed файлов из inventory.

## Phase 2 — first OpenSpec: foundation contracts

Первый OpenSpec создаётся после подтверждения Phase 1.

Предлагаемое имя:

```text
strategy-engine-foundation-v1
```

Scope:

- package architecture;
- canonical ticker/timeframe/range;
- `MarketFrame`;
- decimal/numeric policy;
- `IndicatorPlan`, `FeatureFrame`, validity metadata;
- `StrategySpecEnvelope`;
- `StrategyRangeEvaluationRequest/Result`;
- error envelope;
- FastAPI app skeleton;
- health/readiness;
- Market Data Service port/client skeleton;
- запрет semantic implementation до утверждения contracts.

## Phase 3 — config, validation and catalog port

Port source:

- `spec.py`;
- `instance_loader.py`;
- `component_builders.py`;
- `consumer_roles.py`;
- `spec_instances.py`;
- semantic data from BBB component catalog.

Primary seam:

```text
research.experiments.config_loader
  → load_ema_pullback_config_entry(instance)
```

FastAPI replacement:

```http
POST /v1/strategies/ema_pullback/validate
```

Acceptance:

- accepted fixture parity;
- rejected fixture/path/message parity;
- normalized strategy spec parity;
- deterministic config ID parity;
- catalog parity with Composer-required fields.

## Phase 4 — Indicator Engine planning and first EMA vertical slice

Port source:

- `features/plan.py`;
- first clean subset of `features/calculations.py`;
- timeframe contracts replacing `data_engine.contracts`.

First vertical slice:

```text
validated strategy spec
  → feature plan
  → EMA calculation
  → FeatureFrame
  → POST /v1/indicator-evaluations/range
```

Acceptance:

- exact feature IDs/column mappings;
- EMA series parity;
- warmup/index alignment parity;
- base/HTF time boundary tests;
- no dependency on BBB/Data Engine.

## Phase 5 — complete Indicator Engine

Add:

- ATR and distance features;
- RSI;
- ADX/DI;
- HTF OHLCV resampling;
- completed HTF value alignment;
- all setup/context feature requirements;
- catalog schemas;
- output projection for Workbench/research.

Acceptance:

- bar-by-bar numeric parity with BBB for all existing fixtures;
- explicit tolerance policy only where bit equality is impossible;
- stable feature plan hash;
- no hidden future-bar access.

## Phase 6 — static Strategy Engine range evaluation

Port source:

- contexts;
- component registry;
- direction;
- blockers;
- setups;
- triggers;
- risk;
- `execution/signals.py` semantics;
- `execution/exits.py` static/profile-aware semantics.

Primary API:

```http
POST /v1/strategy-evaluations/range
```

Acceptance:

- context state parity;
- long/short entry parity;
- profile selection parity;
- signal exit parity;
- SL/TP ratio and stop-ready parity;
- component counter parity;
- structured evidence sufficient for existing BBB trace adapter.

## Phase 7 — signal-trace and Workbench compatibility projection

Current duplicate path:

```text
research_api.services.signal_trace_service
  → reconstruct spec
  → reload OHLCV
  → build feature plan
  → recalculate features
  → build_signal_trace_from_spec
```

Target:

```text
BBB signal_trace_service
  → StrategyEngineClient.evaluate_range(output_projection=trace)
  → translate engine evidence to unchanged SignalTraceBundle
```

The engine must not implement Workbench Pydantic DTOs. BBB BFF remains presentation owner.

Acceptance:

- existing frontend endpoints unchanged;
- times, masks, internals, contexts and component events parity;
- no second strategy implementation inside BFF.

## Phase 8 — managed policy split and compatibility replay

Port pure policy:

- phase rule conditions;
- stop/take/runtime-exit components;
- runtime state transitions;
- active management snapshot computation.

Split mixed files:

- `managed_exit_provider.py`;
- `managed_bar_open_candidates.py`;
- `exit_policy_candidates.py`;
- `managed_components/snapshot.py`;
- `trade_runtime.py`;
- `managed_execution_loop.py`;
- `exit_arbitration.py`.

Final ownership:

- Strategy Engine core: policy/state transition and decision candidates;
- compatibility replay adapter: deterministic BBB-equivalent same-bar simulation;
- BBB: research metrics/report assembly;
- future Runtime wrapper: exchange feedback/replay/idempotency.

Acceptance:

- managed trade lifecycle parity;
- same-bar candidate winner parity;
- event and attribution parity;
- no per-bar HTTP RPC from BBB;
- compatibility endpoint is explicitly temporary and isolated.

## Phase 9 — complete FastAPI service

Requirements:

- clean routers/application/ports/adapters split;
- OpenAPI schemas;
- stable errors;
- request limits and deterministic ordering;
- health/readiness;
- MDS dependency status;
- API contract tests;
- Docker image and local composition.

## Phase 10 — independent consumer integration

A new consumer service, currently `research_service`, calls Strategy Engine through its public API. The original BBB repository is not modified and does not participate in the new runtime.

Acceptance covers:

- Strategy Engine API contract stability;
- consumer-side adaptation into research execution inputs;
- frozen parity fixtures derived from the immutable BBB reference source;
- no imports or runtime calls from `legacy_source`.

## Phase 11 — BBB cutover

Surgical replacements:

- local config validation → Strategy client;
- local component catalog → catalog client through BFF;
- local feature/strategy calls → range evaluation client;
- signal trace recomputation → evaluation evidence adapter;
- managed legacy call → compatibility replay or approved runtime boundary.

After acceptance:

- delete old BBB calculation implementation;
- retain BBB execution/report/BFF layers;
- prohibit permanent local fallback.

## Phase 12 — Runtime wrapper, separate program

Not part of current extraction OpenSpecs, but target architecture is fixed:

```text
MDS confirmed bars
  → Runtime wrapper
  → Indicator incremental state
  → Strategy incremental state
  → StrategyDecision
  → Abi signal intent
```

Runtime wrapper owns:

- subscriptions/polling;
- confirmed-bar ordering;
- checkpoint/replay;
- strategy instance lifecycle;
- execution feedback;
- signal idempotency;
- delivery to Abi.

Indicator/Strategy core must support future incremental adapters and mandatory batch-vs-incremental parity.

## 8. Global invariants

- The original BBB repository remains independent throughout development and is not a deployment dependency.
- `legacy_source` is never edited to make imports pass.
- New code never imports `research.*`, `research_api.*`, `data_engine.*` or frontend contracts.
- HTTP APIs are coarse-grained; no RPC per indicator function or component function.
- Workbench calls BBB BFF, never Strategy Engine directly during migration.
- Strategy API does not return fees, exchange fills, PnL or Workbench DTOs.
- Indicator API does not know side, blockers, positions or trades.
- One authoritative strategy semantic implementation after cutover.
- Every slice has golden parity fixtures before the next semantic slice.
- Every new and modified file enters the cumulative strategy-engine patch.

### Completed: ATR distance indicator vertical slice v1

The BBB `atr_distance` derived feature is ported with strict dependency ordering/type/timeframe validation, inherited ATR validity, direct legacy golden parity, and no duplicate market-data or ATR work. Indicator formula coverage is now complete for the copied BBB FeaturePlan kinds. The next implementation change is `ema-pullback-feature-plan-v1`: port `StrategySpec → IndicatorPlan` so callers no longer provide indicator plans manually.

## Current implementation status: EMA Pullback Feature Plan v1

The first strategy-owned semantic seam is implemented. Canonical BBB `strategy_spec_to_dict` payloads are converted inside Strategy Engine into the same ordered/deduplicated feature plan and lookup mappings. BBB callers no longer need to construct an IndicatorPlan for this strategy boundary. Full strategy evaluation remains out of scope and returns `501` until contexts and decisions are ported.

## Implemented seam: EMA Pullback feature-range orchestration

`POST /v1/strategy-evaluations/range` now accepts the strategy spec plus market/range, builds the feature plan internally, calls the in-process Indicator Engine, and obtains candles through the Market Data Service port. The result is explicitly a `features_ready` artifact; contexts and trading decisions remain subsequent ports.


## Implemented: ema-pullback-context-bundle-v1

The engine now builds BBB-compatible strategy-level HTF context bundles from the internally calculated FeatureFrame. Context-consumption policies and trading decisions remain subsequent changes.

## Context-consumption status

`ema-pullback-context-consumption-v1` is implemented. The engine now resolves raw HTF state into side-relative `aligned/countertrend/neutral`, evaluates `htf_regime_gate`, and exposes exit-profile selection evidence. Local blocker/setup masks and trading decisions remain the next layer.


## Implemented semantic slice: ema-pullback-setups-v1

The three legacy setup families, setup context gates, AND composition, and `pre_trigger_allowed` evidence are implemented with direct BBB parity. Trigger and risk layers remain next.

### Completed: EMA Pullback triggers v1

The trigger layer now owns reclaim, strong reclaim, and touch semantics and advances range evaluation to `triggers_ready`. The next semantic slice is risk plus final entry composition.

### Completed: EMA Pullback risk and final entries v1

The copied BBB risk boundary and final entry composition are implemented. `no_risk_filter` is resolved explicitly, final long/short entry masks are returned, and range evaluation advances to `entries_ready`. Exit-policy outputs and managed-exit semantics remain the next strategy slices; overall `decisions_ready` therefore remains false.

## Implemented: standard exit policy

The copied BBB standard exit-policy boundary is now implemented. Range evaluation returns profile-aware signal exits, initial stop/take distance ratios, stop-readiness masks, and per-rule evidence. Normal batch evaluation advances to `decisions_ready`; managed exit lifecycle and execution integration remain separate future phases.

## Implemented: EMA Pullback managed policy v1

Managed strategy policy is now available as a coarse-grained replay for one already-open trade. It owns monotonic phase transitions, break-even/lock-profit stop decisions, take-profile switching and phase/RSI/EMA-cross runtime-exit decisions. Decisions calculated on bar N are effective from bar N+1. OHLC hit arbitration, fills, fees, PnL and exchange order state remain outside Strategy Engine.


## Normative cross-service seam

The exact two-sided cut between Strategy Engine and Research Service is defined in `docs/12_unified_strategy_research_seam_contract.md`.

## Current gate: execution-seam contract v1

The Strategy Engine response is now versioned and explicitly exposes bar count, market-data provenance and managed next-bar effective timing for direct consumption by Research Service.
