## Purpose

Defines the semantic node identity contract and batch-scoped evaluation context that let the Strategy Engine reuse a computation across candidates whenever, and only whenever, it is semantically identical, while guaranteeing one evaluation path and bit-exact parity with the current per-candidate evaluator.

## ADDED Requirements

### Requirement: Single evaluation path for single-spec and batch
The system SHALL use exactly one evaluation code path for both single-spec range evaluation and range-batch evaluation. A single-spec evaluation SHALL be modeled as an evaluation context with exactly one root; a range-batch evaluation SHALL be modeled as an evaluation context with N roots. The system SHALL NOT contain logic that selects a different evaluation path, or a different code branch producing observably different intermediate computations, based on which strategy-spec field(s) vary across the candidates in a batch.

#### Scenario: Batch with a single candidate behaves like single-spec evaluation
- **WHEN** a range-batch request contains exactly one candidate variant
- **THEN** the produced NDJSON output line is byte-identical to the output of evaluating that same variant via the single-spec range endpoint with the same market range

#### Scenario: No branching on swept parameter
- **WHEN** two batches are submitted that vary different strategy-spec fields (e.g. one batch varies only an anchor-stack width threshold, another varies only a take-profit multiplier)
- **THEN** both batches are evaluated by the same evaluation code path with no conditional logic keyed on which field differs

### Requirement: Semantic node identity
Every computation node on the evaluation path (feature/indicator, context, context-consumption gate, direction, blocker, setup component, trigger, exit rule, exit aggregate/select) SHALL have an explicit semantic identity derived from: the node kind and its implementation version, its normalized effective local configuration (after all defaults are applied), the identities of its upstream node dependencies, the side of the computation only when that side is actually read by the node, and the market/range identity of the batch. This identity SHALL NOT be derived from, or rely on, the pre-existing `output_id` field used for feature-plan deduplication.

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

### Requirement: Bit-exact parity with pre-change evaluation
For any given strategy spec, market range, and market data, the reused/memoized evaluation path SHALL produce output byte-identical to the current per-candidate evaluation path, at every observable and intermediate layer: indicator values, context/gate/direction/blocker/setup/trigger results, entries, exit policy evaluation fields, the historical execution projection, and the serialized NDJSON response. Floating-point and Decimal conversion semantics, computation ordering semantics, and error/exception behavior SHALL be preserved exactly, including the current distinction between errors that are caught and reported per-variant and errors that propagate and terminate the batch stream.

#### Scenario: Byte-identical NDJSON across evaluators
- **WHEN** the same range-batch request is evaluated once by the pre-change evaluator and once by the reuse-enabled evaluator
- **THEN** every NDJSON output line is byte-identical between the two runs, for homogeneous, partially-shared, and fully heterogeneous batches

#### Scenario: Shared-node failure is replayed identically per dependent candidate
- **WHEN** a computation node shared by multiple candidates raises an error for one candidate's identity
- **THEN** every candidate depending on that same identity observes the identical error, raised at the same point in that candidate's own evaluation sequence as it would be raised by the pre-change evaluator

#### Scenario: Uncaught error propagation is preserved
- **WHEN** the historical execution projection step raises an error that is not a recognized strategy-engine error in the current evaluator
- **THEN** the reuse-enabled evaluator propagates the same category of error out of the batch stream in the same way, rather than catching or suppressing it

#### Scenario: Downstream Research Service artifacts are unaffected
- **WHEN** a Research Service batch run is materialized from output produced by the reuse-enabled evaluator
- **THEN** the resulting trades, fills, fees, PnL, metrics, and provenance are identical to those produced from the pre-change evaluator's output for the same request

### Requirement: NDJSON streaming behavior preserved
The system SHALL continue to stream range-batch results as NDJSON with one line per candidate, emitted lazily in request order, with per-variant error isolation behavior unchanged. Introducing computation reuse SHALL NOT require buffering all results before the first line is emitted, and SHALL NOT change the order in which results are emitted.

#### Scenario: First result is emitted without waiting for the full batch
- **WHEN** a range-batch request with multiple candidates is evaluated
- **THEN** the first candidate's NDJSON line is emitted without waiting for computation nodes needed only by later candidates

#### Scenario: Output order matches request order
- **WHEN** a range-batch request lists candidates in a given order
- **THEN** NDJSON lines are emitted in that same order, regardless of which computations were reused internally
