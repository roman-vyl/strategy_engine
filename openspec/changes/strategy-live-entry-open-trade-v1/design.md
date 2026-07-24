# Design: Strategy live entry and open trade projections v1

## 1. Baseline and boundary

The current public evaluation surface is:

```http
POST /v1/strategy-evaluations/range
POST /v1/strategy-evaluations/range-batch
POST /v1/strategy-evaluations/managed-replay
```

`/range` and `/range-batch` remain caller-bounded Research contracts. `/managed-replay` remains an externally seeded Research/compatibility replay with its current entry-bar behavior and current wire response.

The new live surface is:

```http
POST /v1/strategy-evaluations/live-entry
POST /v1/strategy-evaluations/open-trade
```

Runtime selects the endpoint from Runtime-owned lifecycle and a current ABI operational-state check:

```text
committed base bar webhook
  -> Runtime asks ABI for the correlated instance operational state

ABI says flat or already closed
  -> Runtime does not call open-trade
  -> Runtime closes/reconciles the local receipt lifecycle as applicable
  -> live-entry is eligible only when no pending/open lifecycle blocks it

ABI says armed/pending and not filled
  -> Runtime continues live-entry/pending reconciliation

ABI says position is currently open
  -> Runtime may call open-trade with the immutable receipt
  -> ABI reconciles the returned desired protection and close signal
```

The immutable receipt is strategy context, not proof that the exchange position still exists. ABI/exchange state is authoritative for whether `open-trade` is eligible.

Engine remains stateless. It does not accept `armed`, `pending`, `in_position`, previous managed state, actual order state, quantity, or exchange commands. Engine also does not infer that a protective order filled from OHLC data.

## 2. Shared live FeatureFrame acquisition

### 2.1 Existing MDS contracts

No new MDS endpoint is introduced. The Engine MDS adapter consumes:

```http
GET /v1/streams/{ticker}/{timeframe}/bounds
GET /v1/candles?ticker=...&timeframe=...&from_ms=...&to_ms=...
```

The bounds DTO is strict and contains:

```text
contract_version = market_stream_bounds.v1
ticker
timeframe
state
earliest_committed_open_time_ms | null
latest_committed_open_time_ms | null
```

Engine adds a transport-neutral `StreamBounds` model and `MarketDataPort.load_bounds(market)` method. Existing `load_range()` remains unchanged.

### 2.2 LoadLiveFeatureFrame

A shared application service, working name `LoadLiveFeatureFrame`, accepts:

```text
strategy envelope
market stream
target_bar_open_time_ms
```

It performs the following sequence:

1. validate the strategy envelope;
2. validate target alignment to the base timeframe;
3. call `load_bounds(market)`;
4. require response market identity to match the request;
5. require bounds contract version `market_stream_bounds.v1`;
6. require `state == ready`;
7. require non-null earliest and latest committed open times;
8. require earliest not later than latest;
9. require target not earlier than earliest and not later than latest;
10. derive the half-open range:

```text
from_ms = earliest_committed_open_time_ms
to_ms   = target_bar_open_time_ms + base_timeframe_duration
```

11. call the existing bounded `load_range()` operation;
12. require a complete ordered base-timeframe grid whose final bar is exactly target;
13. build one strategy feature plan;
14. run the existing indicator evaluation once;
15. return one internal `LiveFeatureFrameBundle` containing the validated strategy envelope, market identity, exact loaded range, target index, MDS-owned market-data hash, feature plan, and FeatureFrame.

The shared loader SHALL stop at the FeatureFrame boundary. Each live application use case SHALL invoke the existing EMA Pullback strategy evaluator exactly once over that bundle for its own projection. This keeps market-data/indicator acquisition shared while avoiding a generic bundle of partially interpreted strategy outputs.

The target bar must be committed but need not equal the absolute latest MDS bar. If MDS has already committed later bars, Engine still requests a range ending exactly after the requested target.

### 2.3 Same history policy before and after fill

Both live endpoints call the same `LoadLiveFeatureFrame` implementation. Therefore live entry planning and open-trade management use the same left-boundary rule and the same indicator pipeline.

Runtime does not send or derive `from_ms`. The receipt does not persist a calculation origin. The v1 policy is simply the complete current `ready` history from MDS earliest committed bar through target.

### 2.4 Two-read race

Bounds and candles are separate MDS reads. If the stream becomes non-ready, the range becomes unavailable, or MDS rejects the bounded read after bounds were accepted, Engine returns a typed upstream/readiness error and does not produce a partial projection.

The `market_data_hash` returned by MDS for the exact candle range remains
available inside the live-frame acquisition pipeline. Engine does not calculate
a substitute hash and does not expose the MDS hash to Runtime.

### 2.5 Live Projections adaptation boundary

After the shared `LiveFeatureFrameBundle` is built, each live use case delegates strategy-family interpretation to a dedicated `Live Projections` boundary.

Each supported strategy family SHALL provide two independent adapters:

```text
live-entry projection adapter
open-trade projection adapter
```

The two adapters have different inputs and results and SHALL NOT be collapsed into one universal live evaluator.

Engine SHALL expose separate application-facing protocols and registries for live-entry and open-trade projection adapters. Generic application use cases select the appropriate adapter by strategy family or strategy identity and SHALL NOT use long-term extension branches such as:

```text
if strategy_id == ema_pullback
```

The first implementation MAY register only EMA Pullback, but the extension seam SHALL support additional strategy families without changing the generic application use cases.

Each strategy-family adapter SHALL:

- receive explicit immutable inputs such as the validated strategy envelope, complete FeatureFrame, target index, and receipt where applicable;
- call existing deterministic strategy calculation primitives or the existing broad evaluator;
- return an internal strategy-specific projection result;
- avoid HTTP, Runtime lifecycle, ABI state, exchange commands, MDS transport, and persisted mutable session state.

The generic application use case SHALL combine the internal projection result with shared identity and provenance to produce the public transport-neutral result. The future HTTP layer SHALL serialize that result only.

For v1, both adapters MAY reuse the existing full strategy FeaturePlan and broad strategy evaluator. The change SHALL NOT require an entry-only or exit-only FeaturePlan, nor a duplicated live-only strategy formula pipeline. Narrow feature or evaluator specialization is deferred until performance evidence requires it.

## 3. Live-entry projection

### 3.1 Request wire contract

```json
{
  "strategy": {
    "strategy_id": "ema_pullback",
    "strategy_version": "1",
    "instance_id": "btc-ema-live-01",
    "raw_spec": {},
    "compatibility_profile": "bbb_v1"
  },
  "market": {
    "ticker": "BTCUSDT.P",
    "base_timeframe": "5m"
  },
  "target_bar_open_time_ms": 1710000000000
}
```

The request does not contain `from_ms`, `to_ms`, candles, warmup, FeaturePlan details, Runtime lifecycle, or ABI state.

### 3.2 Target-bar plan assembly

`EvaluateLiveEntryProjection` obtains a `LiveFeatureBundle`, resolves the strategy-family live-entry projection adapter through the live-entry registry, and delegates target projection to that adapter. For EMA Pullback, the adapter reads the existing `PotentialEntry` result at the target index and `exit_policy.profile_{side}` at the same target index.

A side plan is emitted only when entry, stop, and take are all present, finite, positive, and geometrically valid for the side. A missing or invalid triple yields `null` for that side. Runtime does not combine separate historical vectors.

The source-plan bar is the target bar. The locked profile is one of:

```text
always_on
aligned
countertrend
neutral
```

### 3.3 Response wire contract

```json
{
  "strategy_id": "ema_pullback",
  "strategy_version": "1",
  "instance_id": "btc-ema-live-01",
  "market": {
    "ticker": "BTCUSDT.P",
    "base_timeframe": "5m"
  },
  "target_bar_open_time_ms": 1710000000000,
  "plans_by_side": {
    "long": null,
    "short": {
      "side": "short",
      "source_plan_bar_open_time_ms": 1710000000000,
      "planned_entry_price": "65000",
      "initial_stop_price": "65500",
      "initial_take_price": "64000",
      "locked_exit_profile": "aligned"
    }
  }
}
```

Both `long` and `short` keys are always present. Decimal prices use normalized decimal text. A neutral response with both sides `null` is successful.

Engine does not persist this result. Runtime may replace its mutable pending snapshot on a later bar. ABI correlation determines which exact pending snapshot was filled.

## 4. Fill boundary and immutable receipt

At confirmed fill, Runtime creates one immutable receipt from the exact live-entry plan associated with the filled ABI entry plus fill facts.

The receipt wire object is:

```text
ExecutedTradeReceipt
  trade_id
  instance_id
  strategy_id
  strategy_version
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

Receipt invariants:

- IDs and correlation are non-empty strings;
- side is `long` or `short`;
- profile is a supported profile ID;
- all times are base-timeframe aligned;
- `source_plan_bar_open_time_ms <= entry_bar_open_time_ms`;
- all prices are positive normalized decimal text;
- for long, `initial_stop_price < planned_entry_price < initial_take_price`;
- for short, `initial_take_price < planned_entry_price < initial_stop_price`;

The receipt deliberately excludes `from_ms`, warmup, previous phase, MFE/MAE, active stop/take, quantity, exchange order IDs, historical features, and actual current market state.

## 5. Open-trade projection

### 5.1 Request wire contract

```json
{
  "strategy": {
    "strategy_id": "ema_pullback",
    "strategy_version": "1",
    "instance_id": "btc-ema-live-01",
    "raw_spec": {},
    "compatibility_profile": "bbb_v1"
  },
  "market": {
    "ticker": "BTCUSDT.P",
    "base_timeframe": "5m"
  },
  "target_bar_open_time_ms": 1710000300000,
  "executed_trade_receipt": {}
}
```

### 5.2 Pre-market validation

Before any MDS call, `EvaluateOpenTradeProjection` validates:

```text
request.strategy_id      == receipt.strategy_id
request.strategy_version == receipt.strategy_version
request.instance_id      == receipt.instance_id
request market           == receipt ticker/timeframe
source_plan_bar <= entry_bar <= target_bar
```

It also validates receipt IDs, side, profile, decimal values, alignment, and price geometry. A mismatch is a contract error and no market-data read occurs.

### 5.3 Coverage validation

After loading the live FeatureFrame, Engine requires source-plan, entry, and target bars to be present. Target must be the last bar of the loaded frame. Missing source-plan or entry coverage is a typed `trade_history_unavailable` error, not a newly initialized trade.

### 5.4 Plan-basis management

The strategic entry basis is `planned_entry_price`.

It is used for MFE/MAE strategy metrics, phase thresholds, break-even stop, lock-profit stop, and other entry-relative managed calculations. `executed_entry_price` is retained as an execution fact and does not alter v1 strategy mathematics.

Initial stop and take are absolute levels copied from the filled live-entry plan. Managed protection may only tighten the initial stop. Take management may keep the initial take, switch profile, or disable the fixed take.

### 5.5 Start-after-entry replay

Open-trade replay evaluates only:

```text
entry_index + 1 ... target_index
```

The entry bar:

- has `bars_in_trade = 1`;
- is excluded from MFE/MAE;
- does not run phase, managed-stop, take-management, standard-close, or managed-close rules.

The first post-entry bar has `bars_in_trade = 2`.

This behavior is implemented through a new internal helper or explicit replay mode. Public `/managed-replay` behavior remains unchanged.

### 5.6 Confirmed-open operational precondition

`open-trade` is a calculation contract for a position that Runtime has just confirmed as still open through ABI operational state. The precondition is enforced by Runtime before the request reaches Engine.

If a stop-loss or take-profit order was filled during the just-finished target bar, ABI reports that the position is no longer open. Runtime then does not call `open-trade` for that receipt and target. Consequently Engine does not calculate a hypothetical same-bar signal exit for a position that the exchange has already closed.

Engine cannot independently validate this operational precondition because the request deliberately contains no exchange position or order state. The endpoint contract therefore states a caller obligation: Runtime MUST NOT call `open-trade` unless ABI reports the correlated position as currently open.

### 5.7 Strategic close-signal projection

For a confirmed-open position, `EvaluateOpenTradeProjection` resolves the strategy-family open-trade projection adapter through the open-trade registry and delegates strategy-specific calculation to it. The adapter:

1. replays bar-to-bar management state from `entry_index + 1` through the target bar;
2. derives the post-target-bar desired stop and desired take that should become active after processing the target;
3. selects standard signal exits for the receipt side under `locked_exit_profile`;
4. obtains managed close signals produced by the existing bar-to-bar strategy rules;
5. reuses only the canonical strategy-level composition/attribution needed to expose one target-active close signal;
6. returns no simulated fill, exit price, trade-closed fact, or exchange command.

The live open-trade path MUST NOT run the backtest execution simulator's same-bar arbitration between protective-price hits and strategic close signals. That arbitration existed because backtest had to invent a single fill from OHLC data when no real orders or exchange events existed. In live operation, protective fills are real exchange facts resolved before Engine invocation by the ABI gate.

The open-trade adapter SHALL return a strategy-specific internal projection containing only the calculated protection, strategic close signal, and strategy diagnostics. The generic application use case SHALL add trade identity, strategy identity, market identity, and target bar to form `OpenTradeProjectionResult`.

Only the requested target bar determines the returned `close_signal`. A transient strategic close signal on a skipped earlier bar is not recovered in v1. This is an accepted trading risk; no catch-up, terminal scan, durable cursor, or retry queue is added.

### 5.8 Response wire contract

```json
{
  "trade_id": "trade-123",
  "instance_id": "btc-ema-live-01",
  "strategy_id": "ema_pullback",
  "strategy_version": "1",
  "market": {
    "ticker": "BTCUSDT.P",
    "base_timeframe": "5m"
  },
  "target_bar_open_time_ms": 1710000300000,
  "desired_protection": {
    "stop_price": "65000",
    "take_price": null
  },
  "close_signal": {
    "active": false,
    "reason": null,
    "component_id": null,
    "layer": null
  },
  "diagnostics": {
    "phase": "protected",
    "max_phase_reached": "protected",
    "bars_in_trade": 4,
    "mfe_pct": "1.25",
    "mae_pct": "-0.3",
    "managed_events": []
  }
}
```

`desired_protection.stop_price` is always present and must be at least as protective as the initial stop under side-relative ordering. `desired_protection.take_price` may be `null`. These values are the post-target-bar strategic protection state, effective after target processing; they are not claims about levels that were active inside the already-finished target bar.

`close_signal` describes only a target-active strategic command to close a position that ABI has confirmed is still open. Existing strategy-level composition may select a canonical reason/component when multiple strategic close rules are active. It does not arbitrate against stop/take fills.

`diagnostics` are optional for execution and exist for audit and parity. Runtime/ABI must not treat phase, MFE/MAE, or managed events as exchange commands.

For live open-trade projection, `exit_management.mode` is not a capability gate. Missing `mode`, `diagnostic_only`, and `managed` all use the same post-entry projection path and evaluate the configured management rules. The historical public `/managed-replay` contract retains its existing managed-mode requirement.

Receipt and public protection prices remain canonical decimal text at service boundaries. Receipt-seeded values are preserved as `Decimal` and are not round-tripped through float when unchanged. Exchange tick-size, lot-step, and order-aware quantization are explicitly owned by ABI, not Strategy Engine.

Engine never returns quantity, order IDs, fill price, exit time, realized PnL, `move_stop`, `replace_order`, `cancel_take`, `close_order`, or Bybit-specific parameters.

## 6. Error model

All errors use the existing stable envelope:

```json
{
  "error": "code",
  "message": "human-readable message",
  "details": {},
  "request_id": "..."
}
```

The new use cases define these typed outcomes:

| Code | HTTP | Meaning |
|---|---:|---|
| `invalid_request` | 422 | schema, alignment, enum, decimal, time-order, or price-geometry failure |
| `trade_contract_mismatch` | 409 | request strategy/instance/market/config does not match receipt |
| `market_stream_not_found` | 404 | MDS bounds reports unknown stream |
| `market_stream_not_ready` | 409 | stream exists but state is not `ready`, or bounds are empty |
| `target_bar_not_committed` | 409 | target lies outside committed bounds |
| `trade_history_unavailable` | 409 | source-plan or entry bar is absent from the loaded live frame |
| `upstream_contract_error` | 502 | malformed, mismatched, gapped, unordered, or incomplete MDS response |
| `market_data_unavailable` | 503 | MDS transport or server failure |

No error response contains partial plans or partial desired state.

## 7. Compatibility and verification

The implementation must prove:

- existing `/range` fixtures are unchanged except for changes already owned by earlier completed specs;
- `/range-batch` remains unchanged;
- `/managed-replay` remains unchanged;
- current PotentialEntry vector semantics remain unchanged;
- live-entry plan equals the target-index PotentialEntry triple and target-index profile when evaluated on the same full-ready-history fixture;
- open-trade managed formulas retain parity with the existing pure managed implementation, subject only to start-after-entry semantics;
- repeated identical requests over identical MDS data are deterministic;
- Engine imports no Runtime or ABI package DTOs.

## 8. Performance and v1 limitations

FeatureFrame may be rebuilt from the full ready history on every live request. Managed replay is limited to the post-entry interval and is not a full historical backtest.

Before production rollout, benchmark configured maximum history on supported base timeframes, multiple active instances, MDS payload size, wall-clock latency, and memory. Caching or incremental feature updates may be added internally later without changing either live endpoint contract.

V1 relies on existing MDS ready, continuity, and no-automatic-retention behavior. Historical corrections, versioned prefixes, and active-trade retention management are not introduced by this change.
