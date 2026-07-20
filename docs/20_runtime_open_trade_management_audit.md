# Аудит live-границы Strategy Engine: план входа и управление открытой сделкой

## Статус

Документ фиксирует фактическую текущую точку Strategy Engine и согласованную целевую границу для live-интеграции со Strategy Runtime.

В актуальном Engine существуют только:

```http
POST /v1/strategy-evaluations/range
POST /v1/strategy-evaluations/range-batch
POST /v1/strategy-evaluations/managed-replay
```

Endpoint `current-point` отсутствует и не является частью целевой архитектуры.

Согласованная live-граница добавляет два отдельных Runtime-facing use case:

```http
POST /v1/strategy-evaluations/live-entry
POST /v1/strategy-evaluations/open-trade
```

Оба use case остаются stateless, получают target bar от Runtime и используют один общий внутренний путь построения live FeatureFrame по полной `ready`-истории MDS до target bar.

## 1. Фактическая текущая реализация

### 1.1 Research range evaluation

`/range` и `/range-batch` принимают явный caller-owned `TimeRange`:

```text
strategy spec
market identity
from_ms
to_ms
```

Они предназначены для Research/Workbench и других bounded consumers. Caller сознательно выбирает исследовательское окно. Этот контракт остаётся неизменным.

Он не должен использоваться как live Runtime contract, потому что Runtime не владеет indicator warmup, HTF alignment или выбором левой границы.

### 1.2 PotentialEntry

Текущий `PotentialEntry` уже реализован как минимальная side-aware проекция:

```text
side
entry_price[]
stop_price[]
take_price[]
```

Он строится из уже рассчитанного range pipeline:

```text
pre_trigger_allowed
+ touch_anchor.close_ok
+ anchor vector
+ initial stop/take distances
→ PotentialEntry vectors
```

`PotentialEntry`:

- не принимает Runtime lifecycle;
- не знает об ABI или exchange state;
- не рассчитывает индикаторы повторно;
- не меняет final entry masks и exit-policy vectors;
- остаётся внутренней/Research range-проекцией и не расширяется lifecycle-полями.

### 1.3 Managed replay

`/managed-replay` принимает externally seeded trade и явный range:

```text
strategy spec
market identity
from_ms / to_ms
trade_id
side
entry_time_ms
entry_price
```

Он уже умеет воспроизводить:

- phase и `bars_in_trade`;
- MFE/MAE;
- tighten-only managed stop;
- take-profile switching;
- managed runtime-exit candidates;
- ordered managed events и final managed state.

Public `/managed-replay` остаётся Research/compatibility contract и не меняет wire-семантику.

## 2. Почему одного существующего endpoint недостаточно

### 2.1 Live pending entry требует компактного target-bar плана

Runtime не должен получать полный исторический vector result и самостоятельно совмещать:

```text
PotentialEntry[target_index]
exit_policy.profile_{side}[target_index]
config_hash
source bar identity
```

Эта target-bar сборка относится к Strategy Engine. Новый live-entry use case должен возвращать готовый side-keyed план входа, пригодный для сохранения Runtime и передачи ABI.

### 2.2 Open trade требует immutable receipt

После fill Engine не должен получать `in_position=true` или предыдущий managed state. Он получает immutable executed-trade receipt конкретной сделки и stateless воспроизводит управление до target bar.

### 2.3 Entry bar не является management bar

Для live fill внутри свечи полный OHLC entry bar содержит движение до исполнения. Поэтому:

```text
entry bar N
  initial stop/take уже действуют
  standard и managed close не применяются
  entry-bar OHLC не входит в MFE/MAE

bar N+1
  первый management bar
  bars_in_trade = 2
```

Новый open-trade use case должен применять эту семантику отдельно от неизменяемого public `/managed-replay`.

## 3. Общий live FeatureFrame path

### 3.1 Runtime не определяет окно

Runtime передаёт:

```text
strategy spec
market identity
target_bar_open_time_ms
```

Runtime не передаёт:

```text
from_ms
warmup length
indicator periods
HTF requirements
candle arrays
calculation origin
```

### 3.2 Engine использует существующие MDS contracts

Новый MDS endpoint не требуется. Engine использует уже существующие операции:

```http
GET /v1/streams/{ticker}/{timeframe}/bounds
GET /v1/candles?ticker=...&timeframe=...&from_ms=...&to_ms=...
```

Общий внутренний use case, рабочее имя `LoadLiveFeatureFrame`, выполняет:

1. проверку base-timeframe alignment target bar;
2. чтение MDS stream bounds;
3. проверку `state == ready`;
4. проверку непустых earliest/latest bounds;
5. проверку, что target bar уже committed и `target <= latest_committed_open_time_ms`;
6. построение диапазона:

```text
from_ms = earliest_committed_open_time_ms
to_ms   = target_bar_open_time_ms + base_timeframe_duration
```

7. чтение bounded candles через существующий candle-range contract;
8. построение одного FeaturePlan и одного FeatureFrame обычным Engine pipeline.

Target bar не обязан быть абсолютным latest bar MDS. Из-за задержки обработки MDS может уже иметь более поздние свечи. Загруженный frame обязан заканчиваться ровно запрошенным target bar.

### 3.3 Это не canonical-window subsystem

В v1 не вводятся:

- отдельный warmup resolver;
- calculation origin в Runtime или receipt;
- HTF-origin protocol;
- indicator-window policy, вычисляемая вне Engine;
- versioned historical prefix;
- новый MDS ready-history endpoint.

Правило v1 проще: для обоих live use case Engine использует всю доступную непрерывную `ready`-историю потока от текущего MDS earliest bound до target bar.

Это обеспечивает одинаковую history policy до и после fill.

### 3.4 Cross-service предпосылка v1

Live v1 опирается на действующие MDS semantics:

- `ready` range является непрерывным;
- обычный consumer read отклоняет non-ready, incomplete и out-of-bounds range;
- MDS не выполняет автоматическое retention active history;
- historical correction/revision protocol не является частью v1.

Если source-plan bar или entry bar отсутствуют в полученном frame, Engine не создаёт initial state и не угадывает историю. Он возвращает typed coverage error, а Runtime переводит instance в recovery/suspended path.

## 4. Live-entry projection до fill

Рабочий endpoint:

```http
POST /v1/strategy-evaluations/live-entry
```

Концептуальный request:

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

Engine строит live FeatureFrame и возвращает только target-bar проекцию:

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
    long | short
      side
      source_plan_bar_open_time_ms
      planned_entry_price
      initial_stop_price
      initial_take_price
      locked_exit_profile
```

Для стороны без полного entry/stop/take plan возвращается явное отсутствие плана. Runtime не достраивает plan из отдельных vectors.

`locked_exit_profile` фиксируется на source-plan bar и берётся из того же FeatureFrame и target index, что и PotentialEntry. Разрешённые profile IDs соответствуют Engine exit-policy contract (`always_on`, `aligned`, `countertrend`, `neutral`).

Runtime может bar-to-bar заменять mutable pending-entry snapshot. Это Runtime lifecycle, а не Engine state.

## 5. Executed-trade receipt после fill

Когда ABI подтверждает fill конкретного pending plan, Runtime создаёт immutable receipt:

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

Семантика:

- `source_config_hash` находится внутри receipt;
- `planned_entry_price`, initial stop/take и profile копируются из исполнившегося live-entry plan;
- `executed_entry_price` добавляется из подтверждённого ABI fill;
- receipt создаётся один раз и не дописывается последующими managed outputs;
- current ABI stop/take, quantity и order IDs не становятся strategy inputs.

## 6. Open-trade projection после fill

Рабочий endpoint:

```http
POST /v1/strategy-evaluations/open-trade
```

Концептуальный request:

```text
OpenTradeProjectionRequest
  strategy
  market
  target_bar_open_time_ms
  executed_trade_receipt
```

До MDS read Engine проверяет:

```text
request strategy_id/version/instance_id == receipt identity
request market == receipt ticker/timeframe
recomputed request.strategy.config_hash == receipt.source_config_hash
trade_id и instance_id непустые
side ∈ {long, short}
locked_exit_profile входит в разрешённый contract
source_plan_bar <= entry_bar <= target_bar
```

После построения FeatureFrame Engine проверяет:

```text
source_plan_bar присутствует в frame
entry_bar присутствует в frame
target_bar является последним bar загруженного frame
```

Затем:

1. standard signal exits выбираются по immutable `locked_exit_profile`;
2. managed state воспроизводится только от `entry_index + 1` до target index;
3. MFE/MAE, phase, break-even и lock-profit используют `planned_entry_price`;
4. initial stop/take остаются абсолютными уровнями исходного Engine plan;
5. target-bar desired state формируется без exchange-native команд.

Концептуальный response:

```text
OpenTradeProjectionResult
  trade_id
  instance_id
  target_bar_open_time_ms
  desired_stop_price
  desired_take_price | null
  close_position
  close_reasons
  phase
  bars_in_trade
  mfe
  mae
  managed_events
  market_data_hash
```

`break_even_stop` является plan-basis стратегическим уровнем, а не гарантией фактического PnL `0.00` после slippage, commissions и funding.

## 7. Пропущенные transient exits

Open-trade v1 возвращает close state, активный на текущем target bar.

Management state воспроизводится по post-entry bars, но transient close candidate с пропущенного промежуточного бара не превращается в terminal historical event.

В v1 намеренно отсутствуют:

- durable per-bar cursor;
- catch-up workflow;
- retry-until-success queue;
- terminal/absorbing historical close scan.

Потеря одноразового close signal на пропущенном баре является явно принятым trading risk v1.

## 8. Производительность v1

Полная ready-history нужна для обычного индикаторного pipeline. Bar-to-bar management одной сделки выполняется только на участке `entry+1 ... target`, а не на всей истории.

На один live request допускаются:

```text
one MDS bounds read
+ one bounded candle read
+ one FeaturePlan
+ one FeatureFrame
+ one strategy evaluation
```

Фраза `one MDS read` больше не является инвариантом.

V1 является correctness-first и может заново рассчитывать FeatureFrame на каждом webhook. Cache, incremental indicators и shared frame reuse являются внутренними будущими оптимизациями, которые не должны менять HTTP contract или стратегическую семантику.

Перед production rollout требуется benchmark на фактической максимальной configured history и числе active instances. Hard latency SLA не придумывается до измерения.

## 9. Итог аудита

### Сохраняется без изменения

- `/range` и `/range-batch` Research contracts;
- `/managed-replay` compatibility contract;
- `PotentialEntry` dataclass и range vectors;
- existing FeaturePlan/indicator/HTF/FeatureFrame pipeline;
- pure managed policy formulas;
- Engine statelessness.

### Добавляется

- MDS bounds model/client method в Engine adapter;
- общий внутренний `LoadLiveFeatureFrame`;
- `EvaluateLiveEntryProjection`;
- `EvaluateOpenTradeProjection`;
- live-entry и open-trade HTTP DTOs/routes;
- typed identity, readiness, coverage и config-mismatch errors;
- contract и parity tests двух live paths.

### Не добавляется

- Runtime lifecycle state в Engine;
- current-point endpoint;
- Runtime-owned calculation window;
- new MDS endpoint;
- canonical warmup/origin subsystem;
- Engine-hosted sessions;
- ABI/Bybit command models;
- missed-bar catch-up v1.
