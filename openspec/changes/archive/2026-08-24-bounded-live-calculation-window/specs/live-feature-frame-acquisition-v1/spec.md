## MODIFIED Requirements

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
