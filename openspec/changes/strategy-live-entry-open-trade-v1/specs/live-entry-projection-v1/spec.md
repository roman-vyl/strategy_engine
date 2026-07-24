# Live entry projection v1

## ADDED Requirements

### Requirement: Expose the live-entry endpoint

Strategy Engine SHALL expose:

```http
POST /v1/strategy-evaluations/live-entry
```

The request SHALL contain a strategy envelope, market identity, and `target_bar_open_time_ms`.

The endpoint SHALL be stateless and SHALL NOT accept Runtime lifecycle or ABI order state.

#### Scenario: Valid live-entry request

- **WHEN** a valid request is submitted for a supported strategy and market
- **THEN** Engine SHALL evaluate the requested target through the shared live FeatureFrame path.

### Requirement: Delegate through a strategy-family live-entry adapter

The generic live-entry application use case SHALL resolve a live-entry projection adapter through a dedicated live-entry registry using strategy family or strategy identity.

The generic use case SHALL NOT contain strategy-family-specific calculation branches as its extension mechanism.

The adapter SHALL receive explicit validated inputs and a complete live FeatureFrame, MAY reuse the existing broad strategy evaluator in v1, and SHALL return an internal strategy-specific live-entry projection.

The generic application layer SHALL add shared identity and provenance and SHALL produce the public `LiveEntryProjectionResult`.

#### Scenario: EMA Pullback live-entry projection

- **WHEN** a valid EMA Pullback live-entry request is evaluated
- **THEN** the live-entry registry SHALL resolve the EMA Pullback adapter
- **AND** the generic use case SHALL not inspect EMA Pullback-specific evaluator fields directly.

#### Scenario: Unsupported strategy family

- **WHEN** no live-entry adapter is registered for the requested strategy family
- **THEN** Engine SHALL return a typed unsupported-strategy error
- **AND** SHALL NOT fall back to a strategy-specific conditional branch.

### Requirement: Return a stable live-entry response identity

A successful response SHALL contain:

```text
strategy_id
strategy_version
instance_id
source_config_hash
market.ticker
market.base_timeframe
target_bar_open_time_ms
market_data_hash
plans_by_side.long
plans_by_side.short
```

The response SHALL NOT contain a payload-level `contract_version`; the endpoint
and its published HTTP schema define the contract.

Both side keys SHALL always be present and SHALL contain either a complete plan object or `null`.

#### Scenario: No plan on either side

- **WHEN** neither side has a complete valid target-bar plan
- **THEN** the endpoint SHALL return HTTP success
- **AND** both `plans_by_side.long` and `plans_by_side.short` SHALL be `null`.

### Requirement: Project target-bar entry plans from existing strategy results

For each side, Engine SHALL read the existing PotentialEntry entry, stop, and take values at the target index and the exit-policy profile for the same side and target index.

Engine SHALL NOT recalculate entry, risk distances, or profile selection in the HTTP adapter.

#### Scenario: Complete long target-bar plan

- **WHEN** target-index long entry, stop, and take are all present and valid
- **AND** a supported long exit profile is present at the same index
- **THEN** Engine SHALL return a complete long plan.

#### Scenario: Incomplete target-bar triple

- **WHEN** any of entry, stop, or take is absent or invalid for a side
- **THEN** the plan for that side SHALL be `null`
- **AND** Engine SHALL NOT return a partial plan.

### Requirement: Define the live entry plan contract

A non-null side plan SHALL contain:

```text
side
source_plan_bar_open_time_ms
planned_entry_price
initial_stop_price
initial_take_price
locked_exit_profile
```

`source_plan_bar_open_time_ms` SHALL equal the requested target bar.

Wire prices SHALL be positive normalized decimal text.

`locked_exit_profile` SHALL be one of `always_on`, `aligned`, `countertrend`, or `neutral`.

#### Scenario: Long price geometry

- **WHEN** a long plan is returned
- **THEN** `initial_stop_price < planned_entry_price < initial_take_price` SHALL hold.

#### Scenario: Short price geometry

- **WHEN** a short plan is returned
- **THEN** `initial_take_price < planned_entry_price < initial_stop_price` SHALL hold.

### Requirement: Lock profile on the source-plan bar

The plan's `locked_exit_profile` SHALL be the profile selected for that side on the same target bar that produced the PotentialEntry triple.

Runtime SHALL NOT derive, fill, or replace the profile after the plan is returned.

#### Scenario: Profile changes on a later bar

- **WHEN** a later evaluation selects a different profile
- **THEN** an earlier returned plan SHALL retain its original locked profile
- **AND** a newly returned plan MAY contain the later profile.

### Requirement: Return Engine and MDS provenance

`source_config_hash` SHALL be computed by Engine from the request strategy envelope.

`market_data_hash` SHALL be the unchanged MDS-owned hash for the exact loaded live range.

#### Scenario: Successful live-entry projection

- **WHEN** Engine returns a live-entry result
- **THEN** Runtime SHALL have sufficient identity and provenance to bind a filled plan to its source config and candle range.

### Requirement: Preserve existing evaluation contracts

Adding live-entry SHALL NOT alter `/range`, `/range-batch`, `/managed-replay`, current PotentialEntry vector semantics, or existing exit-policy vector semantics.

#### Scenario: Existing range fixture

- **WHEN** an existing range fixture is evaluated before and after this change
- **THEN** its pre-existing response and strategy semantics SHALL remain unchanged.
