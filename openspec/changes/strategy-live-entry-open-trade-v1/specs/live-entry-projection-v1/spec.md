# Live entry projection v1

## ADDED Requirements

### Requirement: Expose the live-entry endpoint

Strategy Engine SHALL expose:

```http
POST /v1/strategy-evaluations/live-entry
```

The request SHALL be one flat object containing exactly `strategy_id`,
`raw_spec`, `ticker`, `base_timeframe`, and `target_bar_open_time_ms`.
It SHALL NOT contain nested `strategy` or `market` transport wrappers. Unknown
fields SHALL be rejected by the strict HTTP model.

The endpoint SHALL be stateless and SHALL NOT accept Runtime lifecycle or ABI order state.

#### Scenario: Valid live-entry request

- **WHEN** a valid request is submitted for a supported strategy and market
- **THEN** Engine SHALL evaluate the requested target through the shared live FeatureFrame path.

#### Scenario: Removed Runtime instance ID is supplied

- **WHEN** a live-entry request contains top-level `instance_id`
- **THEN** strict HTTP validation SHALL reject the request before MDS access.

#### Scenario: Retired nested request is supplied

- **WHEN** a live-entry request supplies `strategy` or `market` wrapper objects
- **THEN** strict HTTP validation SHALL reject the request before MDS access
- **AND** Engine SHALL NOT apply aliases, dual schemas, or a compatibility adapter.

### Requirement: Delegate through a strategy-family live-entry adapter

The generic live-entry application use case SHALL resolve a live-entry projection adapter through a dedicated live-entry registry using strategy family or strategy identity.

The generic use case SHALL NOT contain strategy-family-specific calculation branches as its extension mechanism.

The adapter SHALL receive explicit validated inputs and a complete live FeatureFrame, MAY reuse the existing broad strategy evaluator in v1, and SHALL return an internal strategy-specific live-entry projection.

The generic application layer SHALL normalize the internal side-wise adapter
result into the public `LiveEntryProjectionResult.desired_entry` without adding
request metadata.

#### Scenario: EMA Pullback live-entry projection

- **WHEN** a valid EMA Pullback live-entry request is evaluated
- **THEN** the live-entry registry SHALL resolve the EMA Pullback adapter
- **AND** the generic use case SHALL not inspect EMA Pullback-specific evaluator fields directly.

#### Scenario: Unsupported strategy family

- **WHEN** no live-entry adapter is registered for the requested strategy family
- **THEN** Engine SHALL return a typed unsupported-strategy error
- **AND** SHALL NOT fall back to a strategy-specific conditional branch.

### Requirement: Return only the live-entry calculation result

A successful response SHALL contain:

```text
desired_entry: DesiredEntry | null
```

The strict response model SHALL contain no fields beyond the schema above.
It SHALL NOT expose the adapter's internal side-wise representation.

The response SHALL NOT echo `strategy_id`, Runtime-owned `instance_id`, market
identity, base timeframe, or `target_bar_open_time_ms`. Runtime SHALL associate
the synchronous result with its originating request and strategy instance.

#### Scenario: No plan on either side

- **WHEN** neither side has a complete valid target-bar plan
- **THEN** the endpoint SHALL return HTTP success
- **AND** `desired_entry` SHALL be `null`.

#### Scenario: One side has a plan

- **WHEN** exactly one internal side plan is non-null
- **THEN** Engine SHALL return that plan as `desired_entry`.

#### Scenario: Both sides have plans

- **WHEN** both internal side plans are non-null
- **THEN** Engine SHALL fail closed with typed `evaluation_invariant_broken`
- **AND** SHALL NOT arbitrate between plans or choose a side
- **AND** SHALL NOT return a partial `desired_entry`.

### Requirement: Project target-bar entry plans from existing strategy results

For each side internally, Engine SHALL read the existing PotentialEntry entry,
stop, and take values at the target index and the exit-policy profile for the
same side and target index.

Engine SHALL NOT recalculate entry, risk distances, or profile selection in the HTTP adapter.

#### Scenario: Complete long target-bar plan

- **WHEN** target-index long entry, stop, and take are all present and valid
- **AND** a supported long exit profile is present at the same index
- **AND** the short internal plan is null
- **THEN** Engine SHALL return a complete long `desired_entry`.

#### Scenario: Incomplete target-bar triple

- **WHEN** any of entry, stop, or take is absent or invalid for a side
- **THEN** the internal plan for that side SHALL be `null`
- **AND** Engine SHALL NOT return a partial `DesiredEntry`.

### Requirement: Define the desired entry contract

A non-null `DesiredEntry` SHALL contain:

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

#### Scenario: Long desired-entry price geometry

- **WHEN** a long `desired_entry` is returned
- **THEN** `initial_stop_price < planned_entry_price < initial_take_price` SHALL hold.

#### Scenario: Short desired-entry price geometry

- **WHEN** a short `desired_entry` is returned
- **THEN** `initial_take_price < planned_entry_price < initial_stop_price` SHALL hold.

### Requirement: Lock profile on the source-plan bar

The desired entry's `locked_exit_profile` SHALL be the profile selected for that
side on the same target bar that produced the PotentialEntry triple.

Runtime SHALL NOT derive, fill, or replace the profile after the plan is returned.

#### Scenario: Profile changes on a later bar

- **WHEN** a later evaluation selects a different profile
- **THEN** an earlier returned desired entry SHALL retain its original locked profile
- **AND** a newly returned desired entry MAY contain the later profile.

### Requirement: Keep MDS provenance inside Engine

The MDS-owned `market_data_hash` SHALL remain available to Engine's internal
live-frame acquisition, but SHALL NOT be exposed in the Runtime-facing response.

#### Scenario: Successful live-entry projection

- **WHEN** Engine returns a live-entry result
- **THEN** Runtime SHALL receive the calculated plan without MDS provenance metadata.

### Requirement: Preserve existing evaluation contracts

Adding live-entry SHALL NOT alter `/range`, `/range-batch`, `/managed-replay`, current PotentialEntry vector semantics, or existing exit-policy vector semantics.

#### Scenario: Existing range fixture

- **WHEN** an existing range fixture is evaluated before and after this change
- **THEN** its pre-existing response and strategy semantics SHALL remain unchanged.
