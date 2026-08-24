# live-feature-frame-acquisition-v1 Specification

## Purpose

Define the shared internal live-history acquisition path both live-entry and open-trade evaluation use: consuming MDS stream bounds, requiring ready committed coverage, constructing the exact half-open live range, and building one complete target-ending FeatureFrame without exposing MDS provenance to Runtime.
## Requirements
### Requirement: Target-oriented live history acquisition

Strategy Engine SHALL provide one shared internal live-history acquisition path for both live-entry and open-trade evaluation.

The path SHALL accept a validated strategy envelope, a market stream, and `target_bar_open_time_ms`.

Runtime SHALL NOT be required or permitted by these live contracts to supply `from_ms`, `to_ms`, warmup length, indicator periods, HTF requirements, candle arrays, or calculation origin.

#### Scenario: Runtime supplies only market and target

- **WHEN** Runtime requests live evaluation for a valid strategy, market, and aligned target bar
- **THEN** Engine SHALL determine the market-data range internally
- **AND** SHALL NOT require caller-provided history boundaries or candle data.

### Requirement: Consume existing MDS stream bounds

Engine SHALL consume `GET /v1/streams/{ticker}/{timeframe}/bounds` through a strict `load_bounds` adapter operation.

The adapter SHALL require `contract_version = market_stream_bounds.v1` and SHALL validate ticker and timeframe identity against the request.

The adapter SHALL consume, without redefining, `state`, `earliest_committed_open_time_ms`, and `latest_committed_open_time_ms`.

#### Scenario: Bounds identity matches

- **WHEN** MDS returns the expected contract version, ticker, and timeframe
- **THEN** Engine SHALL accept the bounds payload for live range construction.

#### Scenario: Bounds identity is malformed or mismatched

- **WHEN** the bounds response has an unsupported contract version or mismatched market identity
- **THEN** Engine SHALL reject it as `upstream_contract_error`
- **AND** SHALL NOT request candles.

### Requirement: Require ready committed coverage

Live evaluation SHALL require bounds state `ready` and non-null earliest and latest committed open times.

The earliest committed open time SHALL NOT be later than the latest committed open time.

The target bar SHALL be aligned to the base timeframe and SHALL lie inclusively between earliest and latest committed open times.

#### Scenario: Stream is ready and target is committed

- **WHEN** state is `ready`
- **AND** both committed bounds are present
- **AND** the aligned target lies within those bounds
- **THEN** Engine SHALL proceed to candle loading.

#### Scenario: Stream is not ready

- **WHEN** state is not `ready`
- **THEN** Engine SHALL return `market_stream_not_ready`
- **AND** SHALL NOT return a partial projection.

#### Scenario: Bounds are empty

- **WHEN** either committed bound is null
- **THEN** Engine SHALL return `market_stream_not_ready`
- **AND** SHALL NOT return a partial projection.

#### Scenario: Target is not committed

- **WHEN** target is earlier than earliest committed open time or later than latest committed open time
- **THEN** Engine SHALL return `target_bar_not_committed`.

### Requirement: Construct the exact half-open live range

For an accepted target, Engine SHALL construct:

```text
from_ms = max(planned_from_ms, earliest_committed_open_time_ms)
to_ms   = target_bar_open_time_ms + base_timeframe_duration
```

where `planned_from_ms` is produced by the live-calculation-window-planning capability from the strategy spec, its indicator plan, the base timeframe, and a history anchor. The history anchor SHALL be computed by the calling live use case (`target_bar_open_time_ms` for live-entry; the earlier of source-plan and entry bar open time for open-trade), not by this shared acquisition path: Engine's live FeatureFrame acquisition SHALL accept the history anchor as an input on its request and SHALL NOT derive or recompute it internally. `planned_from_ms` already accounts for indicator convergence/finite warm-up combined additively with strategy-semantic lookback, and is already aligned to a complete leading higher-timeframe resample bucket for every higher timeframe the plan uses; Engine SHALL NOT re-derive or adjust any of that internally — its only remaining responsibility is the MDS-bounds clamp below.

Engine SHALL load that range through the existing bounded candle-read operation.

The target SHALL NOT be required to equal the absolute latest committed MDS bar.

When `earliest_committed_open_time_ms` is later than `planned_from_ms`, Engine SHALL clamp `from_ms` to `earliest_committed_open_time_ms`. This truncation SHALL NOT be treated as an error and SHALL NOT block the live request.

Engine SHALL retain `planned_from_ms` (the pre-clamp value) on the existing internal `LiveFeatureFrameBundle`, alongside the already-present `requested_range.from_ms` (the actual, possibly-clamped value), so that truncation is observable by comparing the two: truncation occurred iff `requested_range.from_ms > planned_from_ms`. This observability SHALL NOT require, and this requirement SHALL NOT introduce, any logger call, metrics emitter, event, or diagnostic DTO.

#### Scenario: MDS has bars later than target

- **WHEN** latest committed open time is later than target
- **THEN** Engine SHALL request candles only through `target + base_timeframe_duration`
- **AND** the resulting frame SHALL end exactly on target.

#### Scenario: Planned history start is within available bounds

- **WHEN** `planned_from_ms` is at or after `earliest_committed_open_time_ms`
- **THEN** Engine SHALL use `planned_from_ms` as `from_ms`
- **AND** `LiveFeatureFrameBundle.requested_range.from_ms` SHALL equal `LiveFeatureFrameBundle.planned_from_ms`.

#### Scenario: Planned history start predates available bounds

- **WHEN** `planned_from_ms` is earlier than `earliest_committed_open_time_ms`
- **THEN** Engine SHALL use `earliest_committed_open_time_ms` as `from_ms`
- **AND** `LiveFeatureFrameBundle.requested_range.from_ms` SHALL be greater than `LiveFeatureFrameBundle.planned_from_ms`
- **AND** Engine SHALL proceed with the live request without returning an error.

### Requirement: Build one complete live FeatureFrame

The loaded candle range SHALL be complete, ordered, gap-free, and aligned to the base timeframe.

Engine SHALL build one FeaturePlan and run the existing indicator and HTF feature calculation pipeline once per live request.

The shared acquisition path SHALL stop at the FeatureFrame boundary. The calling live use case SHALL run the existing EMA Pullback strategy evaluation exactly once over that FeatureFrame.

The resulting FeatureFrame SHALL contain target as its final bar.

#### Scenario: Complete live range

- **WHEN** MDS returns the exact complete ordered candle range
- **THEN** Engine SHALL build one FeatureFrame
- **AND** SHALL expose the target index to the calling live use case
- **AND** SHALL NOT precompute a generic strategy projection inside the shared acquisition service.

#### Scenario: Gapped or incomplete range

- **WHEN** MDS returns a gap, wrong order, wrong identity, or an incomplete final boundary
- **THEN** Engine SHALL return `upstream_contract_error`
- **AND** SHALL NOT build a partial FeatureFrame.

### Requirement: Keep the MDS-owned market data hash internal

Engine SHALL propagate the `market_data_hash` returned by MDS for the exact loaded range.

Engine SHALL NOT independently calculate, reinterpret, or replace this hash.

#### Scenario: Live FeatureFrame is built

- **WHEN** MDS returns a valid candle range and hash
- **THEN** the internal live bundle SHALL contain that unchanged hash
- **AND** the Runtime-facing live response SHALL NOT expose it.

### Requirement: Share the history policy across live use cases

Live-entry and open-trade evaluation SHALL invoke the same live FeatureFrame acquisition implementation and SHALL therefore use the same planned-and-clamped history policy, differing only in the history anchor each use case supplies to the planner.

#### Scenario: Same strategy market and target

- **WHEN** live-entry and open-trade requests use the same strategy, market, target, and unchanged MDS data, and both supply the same history anchor
- **THEN** both SHALL be evaluated on the same requested candle range
- **AND** Engine's internal live bundles SHALL observe the same market-data hash.

#### Scenario: Open-trade anchor precedes target

- **WHEN** an open-trade request's source-plan or entry bar open time is earlier than the target bar
- **THEN** the history anchor supplied to the planner SHALL be the earlier of source-plan and entry bar open time
- **AND** the resulting `from_ms` SHALL account for required warm-up before that anchor, not only before the target.

### Requirement: Handle the two-read race without partial output

Bounds and candles MAY be separate MDS reads, but Engine SHALL return a typed readiness, upstream-contract, or availability error and SHALL NOT return a partial live result if MDS readiness or range availability changes between them.

#### Scenario: Candle read is rejected after accepted bounds

- **WHEN** bounds are accepted but the subsequent candle read is rejected because the stream is no longer readable
- **THEN** Engine SHALL fail the live request
- **AND** SHALL NOT reuse stale or partial candles.
