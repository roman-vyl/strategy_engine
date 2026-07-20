# Open trade projection v1

## ADDED Requirements

### Requirement: Expose the open-trade endpoint

Strategy Engine SHALL expose:

```http
POST /v1/strategy-evaluations/open-trade
```

The request SHALL contain a strategy envelope, market identity, `target_bar_open_time_ms`, and `executed_trade_receipt`.

The endpoint SHALL be stateless and SHALL NOT accept previous managed state, actual exchange protection, quantity, or order commands.

Runtime SHALL call the endpoint only after ABI operational state confirms that the correlated exchange position is currently open. The immutable receipt alone SHALL NOT be treated as proof that the position still exists.

#### Scenario: Valid open-trade request

- **WHEN** ABI has confirmed the correlated position is currently open and a valid immutable receipt and matching strategy request are submitted
- **THEN** Engine SHALL evaluate desired strategic state through the shared live FeatureFrame path.

### Requirement: Publish typed HTTP transport contracts

The HTTP adapter SHALL publish explicit OpenAPI request and response schemas for the
open-trade endpoint. The request schema SHALL forbid unknown fields and SHALL map
exactly to `OpenTradeProjectionRequest`. The success schema SHALL map exactly to
`OpenTradeProjectionResult`, including nested desired protection, close signal, and
diagnostics objects.

The HTTP adapter SHALL remain a thin serializer and SHALL NOT calculate strategy
state, inspect EMA Pullback internals, or reinterpret application results.

#### Scenario: OpenAPI schema inspection

- **WHEN** a client reads `/openapi.json`
- **THEN** the open-trade operation SHALL reference named request and success response models
- **AND** SHALL publish the stable nested response fields defined by this specification.

### Requirement: Preserve typed errors over HTTP

The endpoint SHALL preserve the stable Strategy Engine error envelope:

```text
error
message
details
request_id
```

The OpenAPI operation SHALL publish typed error responses for `409`, `422`, `500`,
`501`, `502`, and `503`. Application errors SHALL be returned without partial desired
protection, close signal, or diagnostics payloads.

#### Scenario: Receipt or request validation fails

- **WHEN** request validation, receipt validation, trade binding, readiness, target commitment, or history coverage fails
- **THEN** the endpoint SHALL return the corresponding typed error envelope
- **AND** SHALL NOT return a partial `OpenTradeProjectionResult`.

### Requirement: Delegate through a strategy-family open-trade adapter

The generic open-trade application use case SHALL resolve an open-trade projection adapter through a dedicated open-trade registry using strategy family or strategy identity.

The generic use case SHALL NOT contain strategy-family-specific calculation branches as its extension mechanism.

The adapter SHALL receive explicit validated inputs, the complete live FeatureFrame, target index, and immutable receipt. It MAY reuse the existing broad strategy evaluator and full strategy FeaturePlan in v1. It SHALL return an internal strategy-specific projection containing desired protection, target-active strategic close signal, and diagnostics.

The generic application layer SHALL add shared trade, strategy, market, target, config-hash, and market-data-hash provenance to produce `OpenTradeProjectionResult`.

#### Scenario: EMA Pullback open-trade projection

- **WHEN** a valid EMA Pullback open-trade request is evaluated
- **THEN** the open-trade registry SHALL resolve the EMA Pullback adapter
- **AND** the generic use case SHALL not parse EMA Pullback raw spec or evaluator internals directly.

#### Scenario: Unsupported strategy family

- **WHEN** no open-trade adapter is registered for the requested strategy family
- **THEN** Engine SHALL return a typed unsupported-strategy error
- **AND** SHALL NOT fall back to a strategy-specific conditional branch.

### Requirement: Define the immutable executed-trade receipt

The receipt SHALL contain:

```text
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

IDs and correlation SHALL be non-empty. Hash SHALL be lowercase SHA-256 text. Times SHALL be aligned. Prices SHALL be positive normalized decimal text. Side and profile SHALL use supported enums.

The receipt SHALL NOT contain calculation origin, warmup, current phase, MFE/MAE, active stop/take, quantity, order IDs, or FeatureFrame data.

#### Scenario: Receipt is complete

- **WHEN** every required field is present and valid
- **THEN** Engine MAY proceed to identity validation.

#### Scenario: Receipt is incomplete or malformed

- **WHEN** a required field is absent, empty, unaligned, non-positive, malformed, or unsupported
- **THEN** Engine SHALL return `invalid_request`
- **AND** SHALL NOT read MDS.

### Requirement: Validate receipt price geometry

For a long receipt:

```text
initial_stop_price < planned_entry_price < initial_take_price
```

For a short receipt:

```text
initial_take_price < planned_entry_price < initial_stop_price
```

`executed_entry_price` SHALL be positive but SHALL NOT be required to lie between the initial stop and take.

#### Scenario: Invalid long geometry

- **WHEN** a long receipt has stop at or above planned entry or take at or below planned entry
- **THEN** Engine SHALL return `invalid_request` before MDS access.

### Requirement: Bind the receipt to strategy instance and config

Before MDS access, Engine SHALL require:

```text
request.strategy.strategy_id      == receipt.strategy_id
request.strategy.strategy_version == receipt.strategy_version
request.strategy.instance_id      == receipt.instance_id
request.market.ticker             == receipt.ticker
request.market.base_timeframe     == receipt.base_timeframe
request.strategy.config_hash      == receipt.source_config_hash
```

#### Scenario: Config hash mismatch

- **WHEN** request strategy config hash differs from receipt source config hash
- **THEN** Engine SHALL return `trade_contract_mismatch`
- **AND** SHALL NOT calculate the trade under the new config.

#### Scenario: Instance or market mismatch

- **WHEN** any strategy identity, instance, ticker, or timeframe field differs
- **THEN** Engine SHALL return `trade_contract_mismatch`
- **AND** SHALL NOT read MDS.

### Requirement: Validate trade time ordering

Engine SHALL require:

```text
source_plan_bar_open_time_ms <= entry_bar_open_time_ms <= target_bar_open_time_ms
```

All three bars SHALL be aligned to the receipt base timeframe.

#### Scenario: Target precedes entry

- **WHEN** target is earlier than entry
- **THEN** Engine SHALL return `invalid_request` before MDS access.

### Requirement: Require source-plan entry and target coverage

After loading the live FeatureFrame, Engine SHALL require source-plan, entry, and target bars to be present.

Target SHALL be the final bar of the loaded frame.

Missing source-plan or entry coverage SHALL return `trade_history_unavailable` and SHALL NOT initialize a replacement trade state.

#### Scenario: Entry bar is absent

- **WHEN** the loaded live frame does not contain the receipt entry bar
- **THEN** Engine SHALL return `trade_history_unavailable`.

### Requirement: Use plan-basis management semantics

Open-trade managed calculations SHALL use `planned_entry_price` as the strategic entry basis for MFE/MAE, phase thresholds, break-even stop, lock-profit stop, and other entry-relative rules.

`executed_entry_price` SHALL remain an execution fact and SHALL NOT alter v1 strategy mathematics.

#### Scenario: Planned and executed prices differ

- **WHEN** receipt planned and executed entry prices differ
- **THEN** managed calculations SHALL use planned entry price
- **AND** response identity SHALL still preserve the receipt-bound trade.

### Requirement: Start management after the entry bar

Open-trade replay SHALL evaluate bars from `entry_index + 1` through target index.

The entry bar SHALL have `bars_in_trade = 1`, SHALL be excluded from MFE/MAE, and SHALL not run phase, managed-stop, take-management, standard-close, or managed-close rules.

The first post-entry bar SHALL have `bars_in_trade = 2`.

#### Scenario: Request targets the entry bar

- **WHEN** target equals entry bar
- **THEN** Engine SHALL return initial stop and initial take as desired protection
- **AND** phase SHALL remain initial
- **AND** no managed or close event SHALL be produced.

#### Scenario: First post-entry bar

- **WHEN** target is the first bar after entry
- **THEN** management SHALL evaluate that bar
- **AND** `bars_in_trade` SHALL equal 2.

### Requirement: Preserve and tighten initial protection

Desired stop SHALL begin at the receipt initial stop and managed stop logic SHALL only tighten it under side-relative ordering.

Desired take SHALL begin at the receipt initial take and MAY remain, change according to supported take-management semantics, or become `null` when the fixed take is explicitly disabled.

#### Scenario: Managed stop is not tighter

- **WHEN** a managed stop candidate is less protective than the current desired stop
- **THEN** Engine SHALL retain the more protective stop.

### Requirement: Use the locked exit profile

Target-bar standard signal exit selection SHALL use receipt `locked_exit_profile` and receipt side.

Engine SHALL NOT replace it with the exit profile newly selected on the target bar.

#### Scenario: Target-bar selected profile differs

- **WHEN** current context selects a profile different from receipt locked profile
- **THEN** standard exit SHALL still be evaluated under the locked profile.

### Requirement: Require a confirmed-open caller precondition

Runtime SHALL NOT call `open-trade` unless ABI operational state reports that the correlated exchange position is currently open.

If ABI reports that the position was closed by a protective order or any other exchange event during the just-finished target bar, Runtime SHALL NOT invoke Engine open-trade evaluation for that receipt and target.

Engine SHALL NOT infer protective-order fills from OHLC data and SHALL NOT treat the immutable receipt as proof of current exchange position existence.

#### Scenario: Take or stop filled before webhook processing

- **WHEN** ABI reports that the correlated position is no longer open after the target bar commits
- **THEN** Runtime SHALL NOT call `open-trade`
- **AND** no hypothetical target-bar strategic close signal SHALL be calculated for that closed position.

### Requirement: Project post-target-bar desired protection

For a confirmed-open position, Engine SHALL return the desired stop and desired take after processing the target bar.

The returned levels SHALL be effective for subsequent realtime movement after target processing. They SHALL NOT be interpreted as levels that were necessarily active during the already-finished target bar and SHALL NOT assert that either level filled.

#### Scenario: Managed protection changes on target

- **WHEN** target-bar management tightens stop or disables/switches take
- **THEN** the response SHALL expose the resulting post-target-bar protection state.

### Requirement: Evaluate strategic close signal only on the requested target bar

The response close signal and its evidence SHALL be projected from target-active standard and managed strategy close rules. Standard signal selection SHALL use receipt `locked_exit_profile`.

Engine MAY reuse existing canonical strategy-level close-signal composition and attribution when multiple strategic close rules are active. Engine SHALL NOT run backtest execution-fill arbitration between protective-price hits and strategic close signals.

A transient strategic close signal present only on an earlier skipped bar SHALL NOT be recovered in v1.

#### Scenario: Transient exit occurred on a skipped bar

- **WHEN** a strategic exit signal was true only on an earlier skipped bar and false on target
- **THEN** `close_signal.active` SHALL be false unless another target-bar strategic close rule is active
- **AND** Engine SHALL NOT perform catch-up or terminal scanning.

#### Scenario: Multiple strategic close rules on target

- **WHEN** multiple standard or managed strategic close rules are active on target
- **THEN** Engine SHALL expose the canonical strategy-level close reason/component selected by existing strategy semantics
- **AND** SHALL NOT compare those rules with simulated stop/take fills.

### Requirement: Return desired strategic state

A successful response SHALL contain:

```text
contract_version = strategy_open_trade_projection.v1
trade_id
instance_id
strategy_id
strategy_version
source_config_hash
market.ticker
market.base_timeframe
target_bar_open_time_ms
market_data_hash
desired_protection.stop_price
desired_protection.take_price | null
close_signal.active
close_signal.reason | null
close_signal.component_id | null
close_signal.layer | null
diagnostics.phase
diagnostics.max_phase_reached
diagnostics.bars_in_trade
diagnostics.mfe_pct
diagnostics.mae_pct
diagnostics.managed_events[]
```

Prices and percentages SHALL serialize as normalized decimal text or `null` where allowed.

The response SHALL NOT contain exchange commands, quantity, exchange order IDs, fill price, exit time, realized PnL, or Bybit-specific parameters.

#### Scenario: No strategic close is required

- **WHEN** no target-bar standard or managed strategic close rule is active
- **THEN** `close_signal.active` SHALL be false
- **AND** close reason/component/layer SHALL be `null`.

#### Scenario: Strategic close is required

- **WHEN** canonical target-bar strategy semantics require a close command
- **THEN** `close_signal.active` SHALL be true
- **AND** reason/component/layer SHALL preserve canonical strategic attribution.

### Requirement: Produce deterministic stateless projections

Repeated identical requests over identical MDS candle data SHALL produce identical responses.

Engine SHALL NOT persist an open-trade session or mutate the receipt.

#### Scenario: Identical retry

- **WHEN** Runtime retries an identical request and MDS returns the same exact candle range and hash
- **THEN** Engine SHALL return the same desired state.

### Requirement: Preserve public managed replay compatibility

The start-after-entry helper added for open-trade SHALL NOT alter the existing `/managed-replay` request, response, entry-bar behavior, events, or fixtures.

#### Scenario: Existing managed replay fixture

- **WHEN** an existing managed replay fixture is evaluated after this change
- **THEN** its response SHALL remain unchanged.
