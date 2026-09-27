# batch-computation-reuse Specification

## Purpose

Defines the semantic node identity contract and batch-scoped evaluation context that let the Strategy Engine reuse a computation across candidates whenever, and only whenever, it is semantically identical, while guaranteeing one evaluation path (used by single-spec and batch alike) and bit-exact parity of Strategy Engine outputs with the current per-candidate evaluator.

## Requirements

### Requirement: Single evaluation path for single-spec and batch
The system SHALL use exactly one evaluation context implementation and one shared range-input representation for both single-spec range evaluation and range-batch evaluation. A single-spec evaluation SHALL be modeled as an evaluation context with exactly one root; a range-batch evaluation SHALL be modeled as an evaluation context with N roots. The final architecture SHALL NOT contain a permanent, separate preparation or evaluation path for single-spec evaluation; single-spec evaluation is the same mechanism specialized to one root, not a parallel implementation. The system SHALL NOT contain logic that selects a different evaluation path, or a different code branch producing observably different intermediate computations, based on which strategy-spec field(s) vary across the candidates in a batch.

This requirement governs routed, production range-evaluation entrypoints (`/range`, `/range-batch`, and `/range/diagnostics`) — i.e. the paths a real request actually reaches. It does not require removing, or otherwise apply to, an unrouted compatibility/reference surface that another capability's spec (`strategy-research-execution-contract-v1`) explicitly requires to be retained as private, in-process-only, context-free code for that capability's own test suite and future regression comparison. Any future removal of that surface is out of scope for this change and requires its own change with an explicit delta to `strategy-research-execution-contract-v1`.

#### Scenario: Batch with a single candidate behaves like single-spec evaluation
- **WHEN** a range-batch request contains exactly one candidate variant
- **THEN** the produced NDJSON output line is byte-identical to the output of evaluating that same variant via the single-spec range endpoint with the same market range

#### Scenario: No branching on swept parameter
- **WHEN** two batches are submitted that vary different strategy-spec fields (e.g. one batch varies only an anchor-stack width threshold, another varies only a take-profit multiplier)
- **THEN** both batches are evaluated by the same evaluation code path with no conditional logic keyed on which field differs

### Requirement: Semantic node identity
Every computation node on the evaluation path (feature/indicator, context, context-consumption gate, direction, blocker, setup component, trigger, exit rule, exit aggregate/select) SHALL have an explicit semantic identity derived from: the node kind and its implementation version, its normalized effective local configuration (after all defaults are applied), the identities of its upstream node dependencies, the side of the computation only when that side is actually read by the node, and the market/range identity of the batch. This identity SHALL NOT be derived from, or rely on, the pre-existing `output_id` field used for feature-plan deduplication.

The identity contract is: (1) semantically equivalent normalized inputs and dependencies SHALL produce the same identity; (2) semantically distinct computation SHALL NOT produce the same identity; (3) the same identity SHALL imply a bit-identical computed result. This contract is defined over normalized inputs and dependency structure, not over output values: two nodes producing coincidentally equal output values SHALL NOT be inferred to share a semantic identity, and identity equality SHALL NOT be established or validated by comparing computed outputs alone.

#### Scenario: Identical effective configuration yields identical identity
- **WHEN** two candidates in the same range-batch declare the same component with configuration values that normalize to the same effective parameters (e.g. one candidate omits a parameter that defaults to 50 and another explicitly sets it to 50)
- **THEN** the two candidates' nodes for that component receive the same semantic identity

#### Scenario: Different effective configuration yields different identity
- **WHEN** two candidates declare the same component with configuration values that normalize to different effective parameters
- **THEN** the two candidates' nodes for that component receive different semantic identities

#### Scenario: Source-distinct indicators never collide
- **WHEN** two candidates request an indicator of the same kind, timeframe, and period but computed from different source columns (e.g. close vs open)
- **THEN** the two indicator nodes receive different semantic identities and are evaluated independently

#### Scenario: Timeframe aliases do not spuriously diverge
- **WHEN** two candidates request the same indicator using different but equivalent timeframe designations that resolve to the same effective timeframe (e.g. `"base"` and the literal base timeframe string)
- **THEN** the two indicator nodes receive the same semantic identity

#### Scenario: Side-insensitive nodes are not split by side
- **WHEN** a computation node's result does not depend on which side (long/short) it is evaluated for
- **THEN** its semantic identity does not include a side component, and its result is computed once and reused for both sides

#### Scenario: Coincidentally equal outputs do not imply shared identity
- **WHEN** two candidates configure the same node kind with normalized effective parameters that differ, but the resulting computed output values happen to be equal for the current market range (e.g. two different lookback windows that select the same bars in a short warmup period)
- **THEN** the two nodes are assigned different semantic identities and are evaluated independently, rather than being treated as reusable because their outputs matched

### Requirement: Batch-scoped evaluation context
The system SHALL provide a per-range-batch evaluation context that holds range-invariant common market data (in a form that does not require re-derivation from the raw market frame for each node) and memoizes the result of each computation node by its semantic identity for the duration of that range-batch evaluation. A memoized result SHALL be produced exactly once per unique identity within the context's lifetime, regardless of how many candidates depend on it.

#### Scenario: Shared computation is evaluated once
- **WHEN** N candidates in a range-batch all require a computation node with the same semantic identity
- **THEN** that node's underlying computation executes exactly once for the batch, and all N candidates observe the identical result

#### Scenario: Divergent computation is not shared
- **WHEN** two candidates in a range-batch require a computation node whose effective configuration differs
- **THEN** the node is computed independently for each candidate and no reuse occurs between them

#### Scenario: Fully heterogeneous batch degrades gracefully
- **WHEN** every candidate in a range-batch has entirely distinct effective configuration for every node
- **THEN** every node is computed independently (no incorrect reuse), and the batch's behavior and output are unchanged from the current per-candidate evaluator

### Requirement: Bit-exact parity of Strategy Engine outputs with pre-change evaluation
For any given strategy spec, market range, and market data, the reused/memoized evaluation path SHALL produce Strategy Engine output byte-identical to the current per-candidate evaluation path, at every observable and intermediate layer: indicator values, context/gate/direction/blocker/setup/trigger results, entries, exit policy evaluation fields, the historical execution projection, and the serialized NDJSON response. Floating-point and Decimal conversion semantics, and computation ordering semantics, SHALL be preserved exactly.

#### Scenario: Byte-identical NDJSON across evaluators
- **WHEN** the same range-batch request is evaluated once by the pre-change evaluator and once by the reuse-enabled evaluator
- **THEN** every NDJSON output line is byte-identical between the two runs, for homogeneous, partially-shared, and fully heterogeneous batches

### Requirement: Observable failure semantics preserved
Error and failure behavior SHALL be preserved exactly: the same failure category, the same message/payload, the same point in each affected candidate's evaluation sequence, and the same caught-vs-propagated behavior as the current per-candidate evaluator, including the current distinction between errors that are caught and reported per-variant and errors that propagate and terminate the batch stream. This requirement is defined over observable failure category, message/payload, and propagation behavior; it does not require preserving Python exception object identity or traceback identity across a replayed failure.

#### Scenario: Shared-node failure is replayed identically per dependent candidate
- **WHEN** a computation node shared by multiple candidates fails for one candidate's identity
- **THEN** every candidate depending on that same identity observes a failure with the same category and message/payload, raised at the same point in that candidate's own evaluation sequence as it would be raised by the pre-change evaluator, regardless of whether the same Python exception object is reused

#### Scenario: Uncaught error propagation is preserved
- **WHEN** the historical execution projection step raises an error that is not a recognized strategy-engine error in the current evaluator
- **THEN** the reuse-enabled evaluator propagates the same category of error out of the batch stream in the same way, rather than catching or suppressing it

### Requirement: Semantic parity of downstream Research Service artifacts
For a Research Service batch run materialized from output produced by the reuse-enabled evaluator, the resulting trades, fills, fees, PnL, cumulative R, metrics, and provenance-relevant content (including the market-data hash and config hash) SHALL be identical in semantic content to those produced from the pre-change evaluator's output for the same request, once non-deterministic metadata fields that are unrelated to this change (such as `run_id` and creation timestamps) are excluded from the comparison. Byte-identical comparison of the full persisted artifact, including non-deterministic metadata, is not a requirement of this change and SHALL NOT be claimed.

#### Scenario: Downstream Research Service artifacts match after excluding non-deterministic metadata
- **WHEN** the same Research Service batch request is run once against the pre-change Strategy Engine and once against the reuse-enabled Strategy Engine
- **THEN** the persisted run artifacts are identical in trades, fills, fees, PnL, cumulative R, metrics, and provenance-relevant content once `run_id` and timestamp fields are excluded from the comparison

### Requirement: NDJSON streaming behavior preserved
The system SHALL continue to stream range-batch results as NDJSON with one line per candidate, emitted lazily in request order, with per-variant error isolation behavior unchanged. Introducing computation reuse SHALL NOT require buffering all results before the first line is emitted, and SHALL NOT change the order in which results are emitted.

#### Scenario: First result is emitted without waiting for the full batch
- **WHEN** a range-batch request with multiple candidates is evaluated
- **THEN** the first candidate's NDJSON line is emitted without waiting for computation nodes needed only by later candidates

#### Scenario: Output order matches request order
- **WHEN** a range-batch request lists candidates in a given order
- **THEN** NDJSON lines are emitted in that same order, regardless of which computations were reused internally
