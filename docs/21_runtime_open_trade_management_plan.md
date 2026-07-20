# План live-entry и open-trade use case в Strategy Engine

## Цель

Добавить в Strategy Engine один согласованный live vertical slice из двух stateless use case:

```http
POST /v1/strategy-evaluations/live-entry
POST /v1/strategy-evaluations/open-trade
```

Оба use case:

- вызываются Strategy Runtime на конкретный закрытый base-timeframe bar;
- сами получают полную `ready`-историю через существующие MDS bounds и candle-range contracts;
- используют общий FeaturePlan/indicator/HTF/strategy pipeline;
- не принимают Runtime lifecycle state;
- не меняют существующие `/range`, `/range-batch` и `/managed-replay` contracts.

Рабочие имена не нормативны до OpenSpec. Нормативны границы и семантика.

## 1. Scope

### В scope

1. MDS bounds DTO и client method внутри Strategy Engine.
2. Общий `LoadLiveFeatureFrame` application helper/use case.
3. `EvaluateLiveEntryProjection`.
4. `EvaluateOpenTradeProjection`.
5. HTTP request/response DTOs и routes для двух use case.
6. Live pending-plan projection с locked profile и config hash.
7. Immutable executed-trade receipt input.
8. Start-after-entry managed replay variant.
9. Locked-profile standard exit composition.
10. Typed validation/readiness/coverage errors.
11. Unit, contract, parity и integration tests.

### Вне scope

- изменение Research `/range` semantics;
- изменение public `/managed-replay`;
- current-point endpoint;
- новая MDS operation;
- вычисление warmup в Runtime;
- canonical window/origin subsystem;
- Engine persistence или live sessions;
- ABI reconciliation implementation;
- historical correction/versioning protocol;
- catch-up или terminal exit recovery;
- incremental indicator cache как обязательная часть v1.

## 2. Общий live market-data path

### 2.1 Port contracts

Расширить Engine market-data boundary чтением bounds:

```text
StreamBounds
  market
  state
  earliest_committed_open_time_ms
  latest_committed_open_time_ms

MarketDataPort
  load_bounds(market) -> StreamBounds
  load_range(market, time_range, expected_market_data_hash?) -> MarketFrame
```

Это адаптация существующего MDS API, а не новый MDS contract.

### 2.2 LoadLiveFeatureFrame

Концептуальный input:

```text
strategy
market
target_bar_open_time_ms
```

Алгоритм:

1. валидировать strategy envelope и target alignment;
2. вызвать `load_bounds(market)`;
3. потребовать `state == ready`;
4. потребовать непустые earliest/latest;
5. потребовать `target_bar_open_time_ms <= latest_committed_open_time_ms`;
6. построить:

```text
from_ms = earliest_committed_open_time_ms
to_ms   = target_bar_open_time_ms + timeframe_duration
```

7. вызвать existing `load_range`;
8. проверить, что MarketFrame continuous и заканчивается target bar;
9. построить один feature plan;
10. вызвать existing Indicator application один раз;
11. остановиться на общей FeatureFrame boundary — не запускать strategy-family evaluation внутри loader;
12. вернуть typed internal bundle:

```text
LiveFeatureBundle
  validated strategy/config_hash
  market
  target index
  MarketFrame / market_data_hash
  FeaturePlan
  FeatureFrame
```

Shared loader заканчивается на границе FeatureFrame. После этой границы конкретный live use case передаёт bundle в отдельный strategy-family adapter из архитектурной зоны `Live Projections`. `live-entry` и `open-trade` используют разные adapter protocols и отдельные registries, потому что их входы и результаты различаются. Generic application use case не должен знать внутреннюю структуру EMA Pullback pipeline и не должен расширяться через strategy-specific `if` branches.

В v1 оба adapter path используют полный FeatureFrame от earliest committed candle до target bar. Отдельный exit-only FeaturePlan или узкий evaluator пока не вводится: адаптер может переиспользовать существующий широкий evaluator и извлекать только нужную projection. Это осознанный компромисс, сохраняющий одну каноническую реализацию strategy formulas.

High-level boundary зафиксирован в `docs/22_live_projections_architecture.md`. Не вызывать public `/range` через loopback HTTP и не дублировать strategy formulas.

### 2.3 Race semantics

Bounds и candles являются двумя HTTP reads. Если stream теряет `ready` между ними, candle read должен отклонить запрос, и Engine возвращает upstream readiness error.

Если MDS уже содержит bars позднее target, Engine всё равно загружает диапазон только до `target + step`. Target должен быть committed, но не обязан совпадать с absolute latest.

## 3. EvaluateLiveEntryProjection

### 3.1 Request

```text
LiveEntryProjectionRequest
  strategy
    strategy_id
    strategy_version
    instance_id
    raw_spec
    compatibility_profile
  market
    ticker
    base_timeframe
  target_bar_open_time_ms
```

Validation:

- identity fields непустые;
- supported strategy/version/profile;
- target aligned to base timeframe;
- market совпадает с Runtime-configured base stream на уровне Runtime contract, а Engine проверяет внутреннюю request consistency.

### 3.2 Calculation

1. получить `LiveFeatureBundle`;
2. использовать existing `project_potential_entries` result;
3. взять только target index;
4. для каждой стороны получить profile из `exit_policy.profile_{side}[target_index]`;
5. сформировать side plan только если entry/stop/take полностью присутствуют и валидны;
6. не возвращать full historical vectors.

### 3.3 Response

```text
LiveEntryProjectionResult
  strategy_id
  strategy_version
  instance_id
  source_config_hash
  market
  target_bar_open_time_ms
  market_data_hash
  plans_by_side
    long: LiveEntryPlan | null
    short: LiveEntryPlan | null

LiveEntryPlan
  side
  source_plan_bar_open_time_ms
  planned_entry_price
  initial_stop_price
  initial_take_price
  locked_exit_profile
```

Rules:

- `source_plan_bar_open_time_ms == target_bar_open_time_ms`;
- profile берётся на том же target index;
- Runtime не извлекает profile из отдельного vector response;
- neutral result является успешным response с null plans;
- source config hash вычисляется Engine из request strategy envelope.

## 4. Pending plan и fill boundary

Engine не хранит pending plan.

Runtime может заменить plan на следующем base bar и передать ABI новый desired pending entry. ABI correlation определяет, какой именно plan был исполнен.

При fill Runtime создаёт receipt из:

```text
exact filled LiveEntryPlan
+ source strategy identity/config hash
+ market identity
+ ABI fill facts
```

Engine не принимает partially completed receipt и не разрешает дописывать locked profile после первого open-trade request.

## 5. ExecutedTradeReceipt contract

```text
ExecutedTradeReceipt
  trade_id
  instance_id
  strategy_id
  strategy_version
  source_config_hash
  ticker
  base_timeframe

  side
  source_plan_bar_open_time_ms
  entry_bar_open_time_ms

  planned_entry_price
  executed_entry_price
  initial_stop_price
  initial_take_price
  locked_exit_profile

  abi_entry_correlation
```

Invariants:

- IDs непустые;
- side — `long` или `short`;
- prices finite и positive;
- stop/take геометрически соответствуют side;
- locked profile — один из поддерживаемых profile IDs;
- source-plan и entry bars aligned;
- `source_plan_bar_open_time_ms <= entry_bar_open_time_ms`;
- source config hash непустой и canonical.

Receipt не содержит:

- `from_ms`;
- warmup/origin;
- current managed phase;
- current desired или actual stop/take;
- quantity;
- exchange order IDs;
- MFE/MAE;
- historical FeatureFrame.

## 6. EvaluateOpenTradeProjection

### 6.1 Request

```text
OpenTradeProjectionRequest
  strategy
  market
  target_bar_open_time_ms
  executed_trade_receipt
```

### 6.2 Pre-market validation

До MDS calls:

```text
request strategy_id == receipt.strategy_id
request strategy_version == receipt.strategy_version
request instance_id == receipt.instance_id
request market ticker/timeframe == receipt market
request.strategy.config_hash == receipt.source_config_hash
source_plan_bar <= entry_bar <= target_bar
```

Mismatch является contract error. Engine не пытается управлять старой сделкой новой конфигурацией.

### 6.3 Coverage validation

После `LoadLiveFeatureFrame`:

- source-plan bar присутствует;
- entry bar присутствует;
- target bar присутствует и является последним bar frame;
- receipt side/profile поддерживаются текущей strategy implementation.

Отсутствие source/entry bar — typed `trade_history_unavailable`-class error, а не initial state.

### 6.4 Plan-basis managed replay

Canonical strategic basis:

```text
planned_entry_price
```

Он используется для:

- MFE/MAE strategy metrics;
- phase thresholds;
- break-even stop;
- lock-profit stop;
- других entry-relative managed calculations.

`executed_entry_price` сохраняется в receipt как execution fact и не меняет strategy mathematics v1.

Initial stop/take являются абсолютными уровнями исходного live-entry plan.

### 6.5 Start-after-entry replay

Replay interval:

```text
entry_index + 1 ... target_index
```

Entry bar:

- не входит в MFE/MAE;
- не выполняет managed rules;
- не выполняет standard/managed close;
- соответствует `bars_in_trade = 1`.

Первый post-entry bar соответствует `bars_in_trade = 2`.

Нельзя менять public `/managed-replay`; добавить отдельный internal projection/replay mode или чистый helper с явной start index semantics.

### 6.6 ABI gate и strategic close composition

До вызова open-trade Runtime обязан получить от ABI актуальное operational state. Receipt является strategy anchor, но не доказательством существования позиции.

```text
ABI reports position closed
  -> Runtime не вызывает open-trade
  -> Engine не рассчитывает гипотетический signal exit для уже закрытой позиции

ABI reports position open
  -> Runtime вызывает open-trade
```

Для подтверждённо открытой позиции на target bar Engine:

1. выбирает standard signal по `locked_exit_profile` и side;
2. получает target-active managed close signal;
3. применяет только существующую strategy-level composition/attribution между стратегическими close rules;
4. рассчитывает post-target desired protection:
   - initial stop, ужесточённый managed stop;
   - initial take или explicit null после take disable/switch;
5. возвращает desired state, а не ABI command или simulated fill.

Backtest execution arbitration между OHLC stop/take hits и signal exit в live open-trade path не выполняется. В backtest он нужен для симуляции отсутствующих реальных ордеров; в live фактическое закрытие известно ABI до вызова Engine.

Intermediate transient strategic close signals не становятся terminal historical events v1.

### 6.7 Response

```text
OpenTradeProjectionResult
  trade_id
  instance_id
  strategy_id
  strategy_version
  source_config_hash
  market
  target_bar_open_time_ms
  market_data_hash

  desired_protection.stop_price
  desired_protection.take_price | null

  close_signal.active
  close_signal.reason | null
  close_signal.component_id | null
  close_signal.layer | null

  diagnostics.phase
  diagnostics.bars_in_trade
  diagnostics.mfe
  diagnostics.mae
  diagnostics.managed_events
```

Desired protection — состояние после обработки target bar, предназначенное для последующего realtime движения. Оно не утверждает, что уровни были активны или исполнены внутри уже завершившегося target bar.

Engine не возвращает:

```text
fill_price
exit_time
realized_pnl
move_stop
replace_order
cancel_take
close_order
quantity
Bybit parameters
```

## 7. Error model

OpenSpec должен определить typed errors минимум для:

- invalid request/alignment;
- unsupported strategy/profile/side;
- strategy/config/instance mismatch;
- stream not found;
- stream not ready;
- target not committed;
- empty bounds;
- incomplete/gapped MDS range;
- source-plan or entry bar unavailable;
- invalid receipt price geometry;
- upstream MDS unavailable.

Ошибка до calculation не должна возвращать partial desired state.

## 8. Accepted v1 limitations

### 8.1 Missed transient exits

Нет durable cursor, catch-up, terminal scan или retry queue. Одноразовый exit на пропущенном bar может быть потерян. Это accepted trading risk v1.

### 8.2 Full-history recomputation

FeatureFrame может пересчитываться по всей ready-history на каждом webhook. Managed replay ограничен post-entry интервалом.

До production rollout выполнить benchmark:

- максимальный configured history;
- 5m и 1h streams;
- несколько active instances;
- response latency, memory и MDS payload size.

Если требуется cache/incremental optimization, она внедряется внутри Engine без изменения Runtime API.

### 8.3 MDS stability dependency

V1 полагается на существующие MDS ready/continuity/no-automatic-retention semantics. Historical revisions и versioned-prefix validation не входят в этот change.

## 9. Compatibility gates

Обязательные invariants:

- `/range` byte-for-byte compatible для existing fixtures;
- `/range-batch` unchanged;
- `/managed-replay` unchanged;
- PotentialEntry range vectors unchanged;
- live-entry target plan совпадает с target-index PotentialEntry и exit profile на том же full-ready-history fixture;
- open-trade managed outputs сохраняют pure managed formula parity;
- Engine не импортирует Runtime или ABI DTOs.

## 10. Acceptance test matrix

### Live market loader

- ready stream, exact target;
- latest MDS bar позже target;
- target позже latest — reject;
- non-ready stream — reject;
- empty bounds — reject;
- MDS readiness меняется между bounds и range — reject;
- gapped/incomplete candles — reject;
- target frame ends exactly at target.

### Live entry

- long plan;
- short plan;
- neutral/no plan;
- incomplete entry/stop/take yields null plan;
- locked profile from same target index;
- source config hash correctness;
- full-ready-history parity with range evaluator fixture.

### Receipt validation

- config mismatch rejected before MDS read;
- instance/strategy/market mismatch rejected;
- empty IDs rejected;
- invalid side/profile rejected;
- invalid time ordering rejected;
- invalid stop/take geometry rejected.

### Open trade

- entry bar has no management;
- first post-entry bar has `bars_in_trade = 2`;
- planned/executed price differ and managed math uses planned;
- initial stop preserved until tighter managed stop;
- take remains, switches or becomes null;
- locked-profile standard exit;
- managed target-bar exit;
- source-plan/entry missing from frame — coverage error;
- target older than MDS latest still evaluates exact target;
- repeated identical request is deterministic.

### Missed-bar limitation

- transient exit true only on skipped intermediate bar;
- later target false does not recover it;
- test names/documentation identify accepted trading risk.

## 11. Implementation order

1. Add bounds domain model and MDS adapter method.
2. Add `LoadLiveFeatureFrame` and tests.
3. Add live-entry application contracts/use case.
4. Add live-entry HTTP route/DTOs.
5. Add receipt domain contract and validation.
6. Extract start-after-entry managed replay helper without changing public replay.
7. Add locked-profile standard exit selection and desired-state composition.
8. Add open-trade application use case.
9. Add open-trade HTTP route/DTOs.
10. Add compatibility, integration and benchmark tests.
11. Update OpenAPI and architecture docs.
12. Run full verification and strict OpenSpec validation.

## 12. OpenSpec boundary

Один Strategy Engine OpenSpec change должен описывать весь Engine-owned vertical slice:

```text
shared live FeatureFrame acquisition
+ live-entry projection
+ open-trade projection
+ receipt input validation
```

Runtime persistence, lifecycle transitions и ABI reconciliation описываются в Strategy Runtime change, но wire contracts двух Engine endpoints должны быть нормативно определены в Engine OpenSpec.

## 13. Реализационный статус перед HTTP open-trade

Шаги 1–5 реализованы. Фактическая вертикаль сейчас выглядит так:

```text
LoadLiveFeatureFrame
    -> FeatureFrame bundle
    -> separate live-entry/open-trade registry
    -> EMA Pullback Live Projections adapter
    -> strategy-specific internal projection
    -> generic application result
```

Важные реализованные детали:

- receipt/request binding валидируется до MDS reads;
- source-plan и entry bars должны присутствовать в загруженной истории;
- open-trade management начинается с `entry_index + 1`;
- `planned_entry_price`, а не executed fill price, является strategy basis;
- desired stop не ослабляется относительно initial stop;
- locked-profile standard exits читаются только на target index;
- managed runtime exit имеет канонический приоритет над standard signal exit;
- same-layer attribution детерминирована стабильным identifier ordering;
- generic application use cases не разбирают EMA Pullback spec и не содержат strategy-family branching;
- shared loader не запускает EMA Pullback evaluator — это обязанность адаптера;
- текущий feature-plan bundle пока EMA Pullback-specific, несмотря на уже общий registry seam.

Оставшийся Slice 6 должен добавить только transport DTO/route/wiring/error mapping для open-trade и не переносить в HTTP слой какую-либо из перечисленных обязанностей.

HTTP success response должен быть точной сериализацией `OpenTradeProjectionResult`:

- identity и provenance;
- `desired_protection`;
- `close_signal`;
- `diagnostics`.

OpenAPI должен публиковать именованные request/response models и единый typed error
envelope для validation, contract mismatch, readiness, target commitment, history
coverage, unsupported capability и upstream failures. При ошибке частичный desired
state не возвращается.
