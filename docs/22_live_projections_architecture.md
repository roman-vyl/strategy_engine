# Live Projections architecture

This document records the high-level architecture used by Strategy Engine live use cases. It intentionally does not freeze concrete class names, constructor shapes, file-level APIs, or protocol details that belong to implementation design.

## 1. Purpose

Strategy Runtime selects one live calculation path from current ABI operational state. Strategy Engine must then execute only the strategy projection that matches that path.

The two live projections are:

```text
armed / pending-entry lifecycle
    -> live-entry projection

confirmed open position + immutable receipt
    -> open-trade projection
```

They are different use cases with different inputs and different outputs. They must not be collapsed into one universal live evaluator.

## 2. Shared full-history feature acquisition in v1

Both live projections use the same shared market-input boundary:

```text
strategy + market + target bar
    -> MDS ready bounds
    -> candles from earliest committed bar through target bar
    -> one FeaturePlan
    -> one FeatureFrame
```

This is the accepted v1 compromise. Engine remains stateless and reconstructs the complete feature state from canonical history for each request.

Runtime does not send candles, indicator values, cached features, warmup ranges, or partially calculated strategy state. Engine owns feature acquisition and calculation.

The v1 architecture does not yet optimize FeaturePlan separately for entry-only or exit-only requirements. Both projections may use the existing full strategy feature requirements while the projection adapters restrict which strategy behavior is consumed. Feature-plan specialization is a later optimization, not a prerequisite for the live boundary.

## 3. Live Projections package boundary

Each strategy family owns a dedicated `Live Projections` package or equivalent physical boundary.

For a strategy family such as EMA Pullback, that boundary contains two independent adapters:

```text
LiveEntryProjectionAdapter
OpenTradeProjectionAdapter
```

The names above are conceptual. The implementation may choose exact Python names later.

The package is responsible for translating a generic live use case into calls to the strategy family's existing calculation primitives and for translating the resulting strategy data into a strategy-specific projection result.

It must not own:

- HTTP routing or serialization;
- Runtime lifecycle selection;
- ABI operational-state queries;
- exchange orders or fills;
- MDS transport details;
- persisted mutable state between calls.

## 4. Adapter responsibilities

### 4.1 Live-entry projection adapter

The live-entry adapter receives a complete FeatureFrame and target index and invokes the strategy behavior needed to produce the target-bar potential-entry projection.

Its externally relevant output includes the strategy plan data required by Runtime and ABI, such as planned entry, initial protection, locked exit profile, and strategy provenance.

It must not invoke open-position management behavior.

### 4.2 Open-trade projection adapter

The open-trade adapter receives a complete FeatureFrame, target index, and immutable executed-trade receipt.

It invokes the strategy behavior needed to reconstruct bar-to-bar management through the target bar and produce:

- post-target desired stop;
- post-target desired take or disabled take;
- target-active strategic close signal;
- strategy diagnostics.

It must not simulate exchange fills or own Runtime/ABI reconciliation.

In v1 the adapter may call the existing broad strategy evaluator where necessary. Narrow exit-only calculation is explicitly deferred until evidence shows it is needed. This avoids duplicating formulas or prematurely splitting the canonical strategy pipeline.

## 5. Registry and protocol boundary

Engine must support more than one strategy family without adding strategy-specific conditionals to generic application use cases.

Therefore the architecture includes:

- a live-entry adapter protocol and registry;
- an open-trade adapter protocol and registry.

The two registries remain separate because their request and result semantics are different.

Generic application use cases select the adapter by strategy family or strategy identity, then invoke the corresponding protocol. They must not contain branches such as:

```text
if strategy_id == ema_pullback
```

as the long-term extension mechanism.

The first implementation may register only EMA Pullback, but the extension seam must already exist.

## 6. Result layering

Each strategy-specific adapter returns an internal projection result appropriate to that family.

The generic application use case then combines that result with shared identity and provenance:

```text
strategy-specific projection result
    + strategy identity/version
    + market identity
    + target bar
    -> generic application result
```

The HTTP layer later performs serialization only. It must not inspect strategy internals or reconstruct the projection from raw evaluator objects.

## 7. Encapsulation invariant

A Live Projections adapter may know the public calculation contracts of its strategy family, but it must not depend on hidden mutable object state inside the calculation core.

The intended interaction is:

```text
explicit inputs
    -> existing pure or deterministic calculation functions
    -> explicit outputs
    -> projection result
```

not:

```text
create mutable strategy engine object
    -> manipulate hidden internal state
    -> inspect internal fields after calculation
```

## 8. Target architecture

```text
HTTP transport
    -> generic live application use case
    -> shared LiveFeatureFrame loader
    -> strategy-family adapter registry
    -> strategy-family Live Projections adapter
    -> existing strategy calculation primitives
    -> strategy-specific internal projection
    -> generic application result
    -> HTTP response DTO
```

This boundary keeps transport, orchestration, strategy calculation, and strategy-family adaptation vertically separated.

## 9. Implemented v1 code map

The architecture above is implemented by the following boundaries:

```text
strategies/application/load_live_feature_frame.py
    -> validates target and MDS ready bounds
    -> loads earliest-committed-through-target history
    -> builds one FeaturePlan and FeatureFrame

strategies/application/evaluate_live_entry_projection.py
    -> resolves the live-entry registry
    -> adds generic identity and provenance

strategies/application/evaluate_open_trade_projection.py
    -> validates the receipt before market access
    -> resolves the open-trade registry
    -> adds generic identity and provenance

strategies/live_projections/
    -> neutral protocols, separate registries, default registrations

strategies/ema_pullback/live_projections/
    -> EMA Pullback-specific target projection and result assembly
```

The shared loader stops at `LiveFeatureFrameBundle`. It does not run EMA Pullback strategy evaluation. Each selected strategy-family adapter owns the call into its calculation pipeline.

### Current multi-family limitation

The adapter protocols and registries are strategy-family-neutral, but the current v1 feature-planning implementation and `LiveFeatureFrameBundle.planned_features` are still typed around the EMA Pullback feature plan because EMA Pullback is the only registered family. Adding a second family therefore requires generalizing the feature-plan result/bundle boundary as well as registering new adapters. This is a known extension task, not hidden Runtime responsibility and not a blocker for the EMA Pullback HTTP surface.

## 10. Implemented strategic-close attribution

For EMA Pullback open-trade projection, only target-active strategic close rules participate. The current canonical ordering is:

```text
managed runtime-exit candidate
    before
standard locked-profile signal-exit candidate
```

When more than one candidate exists in the same layer, selection is deterministic by stable rule/instance identifier ordering. This attribution is strategy-level composition only. It is not exchange-fill arbitration and does not compare a close signal with stop/take fills.

## 11. Public result invariants implemented before HTTP serialization

The live application results and HTTP responses do not carry a redundant
payload-level `contract_version`. Their contracts are identified by the
dedicated endpoint and its published HTTP schema.
They also do not carry `source_config_hash`; Engine keeps specification hashing
inside Research and validation workflows rather than exposing it to Runtime.

Live-entry always returns stable `long` and `short` keys, each containing a
complete plan or `null`. Open-trade always returns a non-null desired stop, an
optional desired take, one strategic close-signal structure, and diagnostics.
The MDS-owned `market_data_hash` stays inside Engine's live-frame acquisition
pipeline and is not part of either Runtime-facing result. These are
transport-neutral domain results; the HTTP step must serialize them without
reconstructing strategy internals.

Live requests use a dedicated strategy input model and do not accept the
Research-only `strategy_version` or `compatibility_profile` selectors.
`strategy_id` selects the registered live adapter. Research evaluation and
authoring contracts retain their existing envelope, version, and compatibility
validation.

Open-trade carries no Runtime-owned `trade_id`. Its managed calculation is
identity-free; the separate Research `/managed-replay` endpoint keeps its
existing `trade_id` request/response label through a transport wrapper.

The executed-trade receipt contains only entry and management calculation
facts. Strategy identity, instance identity, ticker, and base timeframe come
from the outer request once; timestamp alignment uses that request timeframe.
