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

### Requirement: Identity twins for predicates and composites

Every predicate, predicate column array, derived operand and composite local node SHALL have a resolve twin that yields its
`NodeSpec` without computing it.

- Labels (`instance_id`, `child_id`, `path_id`) SHALL NOT enter any
  identity.
- A side-free predicate SHALL have an identity without a side.
- A `change` predicate SHALL have its own node family whose identity
  carries `op`, `value` and `lookback` and whose upstream is the
  column node of its operand. It SHALL carry a side only when it has
  a `short` override.
- A segment operand SHALL have its own node family whose identity carries `from`, `to`, `value`, `window`, `aggregate` and `negate`, whose
  upstream is the episode node of the evaluated side and the column node of its series, and which carries the side. `span`,
  `top` and `eligibility` SHALL enter the identity only when set, so every segment written before this change keeps its identity.
- A ratio operand SHALL have its own node family whose identity carries its sides and whose upstream is the nodes of its
  non-constant sides; it SHALL carry a side when any side does.
- A `range` predicate's identity SHALL carry `bounds` and `empty` only when they differ from their defaults, so the
  identity of every range written before this change is unchanged.

A successful memoized evaluation of any spec containing
`composite_setup` SHALL end with zero `unforeseen_consumptions`.

#### Scenario: Composite in a batch

- **WHEN** a batch contains candidates that differ only in one
  predicate threshold
- **THEN** the shared feature columns, column arrays and unchanged
  children SHALL each be computed once per batch
- **AND** memoized and non-memoized evaluation SHALL produce
  bit-identical outputs.

#### Scenario: Change candidates differing in the threshold

- **WHEN** a batch contains candidates that differ only in the `value` of one `change` predicate
- **THEN** the operand's feature column and its column array SHALL each be computed once per batch.

#### Scenario: Band candidates differing in the bounds

- **WHEN** a batch contains candidates that differ only in `min` or `max` of one range over a ratio of two segments
- **THEN** the EMA columns, both segments and the ratio SHALL each be computed once per batch per side.

#### Scenario: Branch candidates differing only in the bounds

- **WHEN** a batch contains candidates that differ only in `min` or `max` of the range of one A2 branch
- **THEN** the EMA columns, both segments and the ratio of that branch SHALL each be computed once per batch per side.

### Requirement: No compute regression for existing specs

For specs without `composite_setup`, the following SHALL be identical
to the evaluation before this change:

- evaluation outputs;
- memoized compute counts per node family;
- node identities.

Wall-clock time on the existing batch benchmark workload SHALL show no
regression beyond measurement noise.

#### Scenario: Existing parity corpus

- **WHEN** the existing parity corpus and memo compute-count tests run
  after this change
- **THEN** outputs and compute counts SHALL match their pre-change
  values exactly.

### Requirement: Feature columns are converted once for predicates

Predicates SHALL read feature values through one memoized float64
array per feature identity per evaluation context. This array SHALL be
shared by all predicates, both sides and all batch candidates.

#### Scenario: Many predicates on one column

- **WHEN** three predicates read the same RSI column on both sides
- **THEN** that column SHALL be converted to an array once.

### Requirement: Memoized predicate children in the managed projection

When the historical projection is built under an evaluation context,
every predicate child of a composite phase condition SHALL be evaluated
through its predicate identity. It SHALL therefore share memoized nodes
with identical predicates of `composite_setup`, of other rules and of
other batch candidates.

The batch pre-pass SHALL predict these consumptions with the same
resolution the projection uses: a `managed` stage, resolved after the
exit-policy stage, that lists for every composite phase rule in
declared order, for `long` then `short`, each predicate child's `local`
node followed by its `nested` nodes. The stage SHALL be empty unless
`exit_management.mode` is `managed` and some composite phase condition
has a predicate child; for every other spec the pre-pass predictions
SHALL be unchanged and the projection SHALL resolve no identities. When
the stage cannot be resolved it SHALL be absent and the projection
SHALL evaluate its predicate children unmemoized. A successful memoized
evaluation of a spec with a composite phase condition SHALL end with
zero `unforeseen_consumptions`.

The following SHALL NOT be memo nodes:

- path folding;
- `at_least` counting;
- the `adx_di_threshold` series.

#### Scenario: Batch differing only in the MFE threshold

- **WHEN** a batch contains candidates whose composite phase conditions
  differ only in an `mfe_atr` threshold
- **THEN** each predicate child mask SHALL be computed once per batch
- **AND** memoized and non-memoized evaluation SHALL produce identical
  projections.

### Requirement: No compute regression for existing managed specs

For specs without `composite_phase_condition`, the following SHALL be
identical to the evaluation before this change:

- evaluation outputs, including the serialized managed projection;
- memoized compute counts per node family;
- node identities;
- `/managed-replay` and live open-trade outputs.

#### Scenario: Declared-invariant gate with managed cases

- **WHEN** the declared-invariant gate runs its managed cases after
  this change
- **THEN** every recorded quantity SHALL equal its pre-change value.

### Requirement: Identity twins for partial take nodes

Every partial take distance node SHALL have a resolve twin that yields
its `NodeSpec` without computing it.

- An `atr_partial_take` distance SHALL share the identity of any other
  ATR exit distance over the same ATR column.
- `instance_id` and `fraction_of_initial` SHALL NOT enter any identity.

A successful memoized evaluation of a spec with partial takes SHALL end
with zero `unforeseen_consumptions`.

#### Scenario: Partial takes in a batch

- **WHEN** a batch contains candidates that differ only in a partial
  take's `fraction_of_initial`
- **THEN** every exit distance node SHALL be computed once per batch
- **AND** memoized and non-memoized evaluation SHALL produce
  bit-identical outputs.

### Requirement: No compute regression for specs without partial takes

For specs without partial take rules, the following SHALL be identical
to the evaluation before this change:

- evaluation outputs, including the serialized execution projection,
  `/live-entry`, `/managed-replay` and open-trade outputs;
- memoized compute counts per node family;
- node identities.

#### Scenario: Declared-invariant gate

- **WHEN** the declared-invariant gate runs after this change
- **THEN** every recorded quantity SHALL equal its pre-change value.

### Requirement: Identity of the anchor stack width band setup

`anchor_stack_width_band_setup` SHALL be resolved into two side-free
node families, each with a resolve twin:

- a width node whose identity carries no parameters and whose
  upstream is the `fast`, `slow` and `atr` feature nodes;
- a local node whose identity carries `min_width_atr`, and
  `max_width_atr` only when present, both normalized to floating
  point, and whose upstream is the width node.

Labels (`instance_id`, `child_id`) SHALL NOT enter either identity.
The node identities of `anchor_stack_width_setup` SHALL be unchanged.

#### Scenario: Candidates differing only in the band

- **WHEN** a batch contains candidates that differ only in
  `min_width_atr` or `max_width_atr`
- **THEN** the width node SHALL be computed once per batch
- **AND** memoized and non-memoized evaluation SHALL produce
  bit-identical outputs
- **AND** the memoized evaluation SHALL end with zero
  `unforeseen_consumptions`.

#### Scenario: Equivalent bounds share identity

- **WHEN** one candidate sets `min_width_atr` to `5` and another to
  `5.0`
- **THEN** their local nodes SHALL have the same identity.

### Requirement: No compute regression without the anchor stack width band setup

For specs without `anchor_stack_width_band_setup`, evaluation outputs,
memoized compute counts per node family and node identities SHALL be
identical to the evaluation before this change.

#### Scenario: Existing specs

- **WHEN** the existing memo compute-count and identity tests run
  after this change
- **THEN** outputs, compute counts and identities SHALL match their
  pre-change values exactly.

### Requirement: No compute regression without the entry-anchored change child

For a spec without a `change_since_entry` child, the following SHALL be
identical to those before this change:

- `plan_hash` and plan labels;
- memoized node identities and compute counts per node family;
- evaluation outputs and the serialized managed projection.

A `change_since_entry` child SHALL NOT introduce a memo node family. Its
operand column SHALL be converted at most once per managed projection
and at most once per single-trade evaluation.

#### Scenario: Existing spec

- **WHEN** a spec with no `change_since_entry` child is evaluated
- **THEN** its `plan_hash`, node identities, compute counts and outputs
  SHALL equal those recorded before this change.

#### Scenario: Shared operand column

- **WHEN** two paths of one composite reference the same
  `change_since_entry` child
- **THEN** the projection SHALL convert its operand column once and emit
  one series for it.

### Requirement: Identity of the EMA stack episode

An episode declared in `raw_spec.ema_stack_episode` SHALL be resolved per side into one node of kind `episode.ema_stack`. Its identity SHALL carry `window_bars`, `break_bars`, `history_bars` and the side, and its upstream SHALL be the fast, anchor and slow EMA feature nodes. The `episode_ref` label SHALL NOT enter the identity. An episode operand SHALL carry its `entity`, `index` and `field`, with the episode node as upstream.

#### Scenario: Candidates sharing one episode

- **WHEN** a batch contains candidates that declare the same episode parameters and stack but differ elsewhere
- **THEN** the episode node SHALL be computed once per side per batch
- **AND** memoized and non-memoized evaluation SHALL produce bit-identical outputs
- **AND** the memoized evaluation SHALL end with zero `unforeseen_consumptions`.

### Requirement: No compute regression without an EMA stack episode

For specs without `ema_stack_episode`, evaluation outputs, memoized compute counts per node family, node identities and `plan_hash` SHALL be identical to the evaluation before this change.

#### Scenario: Existing specs

- **WHEN** the existing memo compute-count, identity and plan-hash tests run after this change
- **THEN** outputs, compute counts, identities and plan hashes SHALL match their pre-change values exactly.

### Requirement: No compute regression without segment or ratio operands

For specs that use no segment, no ratio and no new range field, evaluation outputs, node identities and
memoized compute counts per node family SHALL be identical to the evaluation before this change.

#### Scenario: Existing parity corpus

- **WHEN** the existing memo compute-count and node-identity tests run after this change
- **THEN** they SHALL pass unchanged.

### Requirement: Segment aggregate cost

`sum`, `mean_per_bar` and `abs_sum` SHALL cost O(n) per series. `max` and `min` SHALL cost at most O(n log n) per
(series, span) and O(1) per bar, independent of leg length. `top_abs_sum` SHALL cost at most O(n · `last_n`). A spec without
`span`, `top`, `eligibility` or the new aggregates SHALL evaluate with the compute count and outputs of the evaluation
before this change.

#### Scenario: No regression without the new fields

- **WHEN** a batch contains only A1 band candidates
- **THEN** the number of node computations and the outputs SHALL equal those before this change.

### Requirement: Candle operand identity and sharing

A candle operand SHALL have its own node family whose identity carries the episode identity, the leg, the timeframe, the
direction and the identity of the ATR column, and whose upstream is the episode, the market bars and that ATR column. Labels
SHALL NOT enter the identity.

#### Scenario: Band candidates share the operand

- **WHEN** a batch contains candidates that differ only in `min` or `max` of one range over a ratio of two candle operands
- **THEN** the ATR column, both candle operands and the ratio SHALL each be computed once per batch per side.

### Requirement: Candle operand cost

A candle operand SHALL cost O(n) per series, independent of leg length and of the timeframe. A spec without a candle operand
SHALL have the same node set and the same results as before this change.

#### Scenario: No compute regression without candle operands

- **WHEN** a spec has no candle operand
- **THEN** no candle node SHALL be created and no extra work done.

### Requirement: Touch, side series, from-start and ratio floor identity

`touch`, a `by_side` series and `value: from_start` SHALL enter the identity of a segment, and `right_floor` that of a ratio, only when set, so that
the identity of every A1 and A2 segment and ratio is unchanged. A `by_side` series SHALL enter it with the identities of both features.

#### Scenario: Unchanged identities

- **WHEN** a spec has no `touch`, no `by_side` and no `from_start`
- **THEN** its segment identities and results SHALL equal those before this change.

### Requirement: Directional index waves share nodes

Candidates that differ only in `min` or `max` of the range over a B2 ratio SHALL share both segments and the ratio. B2.1 and B2.2
SHALL share the directional index columns and the touch points.

#### Scenario: Band candidates

- **WHEN** a batch contains candidates that differ only in `min` of one range over a ratio of two segments
- **THEN** the directional index columns, both segments and the ratio SHALL each be computed once per batch per side.

### Requirement: From-start cost

`sum` and `mean_per_bar` of `from_start` SHALL cost O(n) per series; `max` and `min` SHALL cost at most O(n log n) per series and
O(1) per bar, independent of leg length. A `previous` segment SHALL add no pass over bars.

#### Scenario: No compute regression

- **WHEN** a spec has no `touch`, `by_side` or `from_start`
- **THEN** no extra node SHALL be created and no extra work done.

### Requirement: Touch end identity

`to: next_origin` SHALL enter the identity of a segment as its end point, so a `peak → next_origin` segment never shares a node with a
`peak → current` or `peak → touch` segment. A spec without the next-origin end point SHALL keep every segment identity and result it had before this
change.

#### Scenario: Unchanged identities

- **WHEN** a spec has no `to: next_origin`
- **THEN** its segment identities and results SHALL equal those before this change.

### Requirement: Counter-trade waves share nodes

Candidates that differ only in `min` or `max` of the range over a C1 ratio SHALL share both segments and the ratio. C1.1 and C1.2
SHALL share the counter-trade directional index columns and the touch points, and SHALL share the DI columns with B2 when the
period is equal.

#### Scenario: Band candidates

- **WHEN** a batch contains candidates that differ only in a bound of one range over a ratio of two segments
- **THEN** the directional index columns, both segments and the ratio SHALL each be computed once per batch per side.

### Requirement: Leg mean operand identity and sharing

A leg mean operand SHALL have its own node family whose identity carries the episode identity, the leg and the field, and whose
upstream is the episode and the market bars. Labels SHALL NOT enter the identity.

#### Scenario: Band candidates share the operands

- **WHEN** a batch contains candidates that differ only in `min` or `max` of one range over a ratio of two leg mean operands
- **THEN** both operands and the ratio SHALL each be computed once per batch per side.

### Requirement: Leg mean cost

A leg mean operand SHALL cost O(n) per series, independent of leg length. A spec without a leg mean operand SHALL have the same
node set and the same results as before this change.

#### Scenario: No compute regression

- **WHEN** a spec has no leg mean operand
- **THEN** no leg mean node SHALL be created and no extra work done.

### Requirement: Candle force series sharing and cost

The candle force series of a side SHALL be derived once per batch per side and field from the shared market arrays; candidates that
differ only in `min` or `max` of one range over a ratio of two leg mean operands SHALL share both operands and the ratio. A spec
without a force field SHALL have the same node set, identities and results as before this change, and no force series SHALL be built for it.
The cost SHALL be O(n) per series, independent of leg length.

#### Scenario: Band candidates share the operands

- **WHEN** a batch contains candidates that differ only in a bound of one range over a ratio of two force leg means
- **THEN** both operands and the ratio SHALL each be computed once per batch per side.

#### Scenario: No compute regression

- **WHEN** a spec has no force field
- **THEN** no force series SHALL be built and no extra work done.

### Requirement: Anchor follow operand identity and cost

An anchor follow operand SHALL have its own node family whose identity carries the episode identity (and thereby the anchor EMA the
episode is built from) and whose upstream is the episode. Labels SHALL NOT enter the identity. It SHALL cost O(n) per series, independent
of leg length. A spec without an anchor follow operand SHALL have the same node set and the same results as before this change.

#### Scenario: Band candidates share the operand

- **WHEN** a batch contains candidates that differ only in `min` or `max` of one range over an anchor follow operand
- **THEN** the operand SHALL be computed once per batch per side.

#### Scenario: No compute regression

- **WHEN** a spec has no anchor follow operand
- **THEN** no anchor follow node SHALL be created and no extra work done.

### Requirement: Identity of the weighted vote setup

A `weighted_vote_setup` SHALL be one semantic node ("Semantic node identity"). Its identity SHALL be derived from:

- the kind `setup.weighted_vote` and its implementation version;
- its normalized configuration (next requirement);
- the identities of its upstream operand and `count.of` predicate nodes;
- the side;
- the market/range identity of the batch.

#### Scenario: Same table on two sides

- **WHEN** the same weighted vote is evaluated on the long and the short side
- **THEN** the two vote nodes SHALL have different identities.

### Requirement: Normalized configuration of the weighted vote

The normalized local configuration of a weighted vote SHALL contain:

- `threshold` and every `weight` as the exact decimal strings of the requirement "Exact decimal weights";
- `level` as numbers;
- `role`, `direction`, the veto flags;
- `voter_id` and `input_id`, because they name the evidence series;
- the structure of voters, inputs and steps in declared order, because declared order names `blocked_by`.

#### Scenario: Labels change the vote node only

- **WHEN** two weighted votes are identical except for a `voter_id`
- **THEN** their vote nodes SHALL have different identities
- **AND** their operand nodes SHALL have the same identities and be computed once.

### Requirement: Sharing of weighted vote inputs

Identifiers and declared order SHALL NOT enter the identities of the upstream operand and predicate nodes. Those nodes keep their
existing identities, so they are shared with other setups, with `composite_setup` children and with other weighted votes.

A batch of specs with weighted votes SHALL end with zero `unforeseen_consumptions`.

#### Scenario: Candidates that differ only in the table

- **WHEN** a batch contains weighted votes that differ only in levels, weights, veto flags or `threshold`
- **THEN** each operand and each predicate of their inputs SHALL be computed once per side.

#### Scenario: Operand shared with a range setup

- **WHEN** the same ratio operand is the operand of a `range` child in a `composite_setup` and of a weighted vote input
- **THEN** it SHALL be computed once.

### Requirement: No compute regression without a weighted vote

For specs without `weighted_vote_setup` the node set, the node identities, the masks, the evidence and the compute counts SHALL be
identical to those before this change.

#### Scenario: Existing specs

- **WHEN** an existing spec without a weighted vote is evaluated
- **THEN** its results and identities SHALL equal those before this change.

### Requirement: Leg sum identity and cost

A leg sum operand SHALL have its own node family whose identity carries the episode identity, the leg and the field, with the
episode and the market bars upstream; labels SHALL NOT enter it. It SHALL cost O(n) per series. A spec without a leg sum operand
SHALL have the same node set and results as before this change.

#### Scenario: Level candidates share the operands

- **WHEN** a batch contains candidates that differ only in a level over a ratio of two leg sum operands
- **THEN** both operands and the ratio SHALL each be computed once per batch per side.

### Requirement: Leg top mean identity and cost

A leg top mean operand SHALL have its own node family whose identity carries the episode identity, the leg, the field and the
share. Its impulse value SHALL be computed once per touch and its pullback value only on bars with a valid wave. A spec without it
SHALL have the same node set and results as before this change.

#### Scenario: Level candidates share the operands

- **WHEN** a batch contains candidates that differ only in a level over a ratio of two leg top mean operands
- **THEN** both operands and the ratio SHALL each be computed once per batch per side.

### Requirement: Pullback depth identity and cost

A pullback depth operand SHALL have its own node family whose identity carries the episode identity. It SHALL be computed only on
bars with a valid wave. A spec without it SHALL have the same node set and results as before this change.

#### Scenario: Level candidates share the operand

- **WHEN** a batch contains candidates that differ only in a level over the pullback depth operand
- **THEN** the operand SHALL be computed once per batch per side.

### Requirement: Previous pullback depth identity

A pullback depth operand with `touch: previous` SHALL be a node of the pullback depth family whose params carry the touch; one with
`touch` absent or `current` SHALL keep the identity it had before this change.

#### Scenario: Current depth identity unchanged

- **WHEN** a spec writes `{"pullback_depth": {"episode": "trend", "touch": "current"}}`
- **THEN** it SHALL resolve to the same node as `{"pullback_depth": {"episode": "trend"}}`.

### Requirement: Leg speed identity and cost

A leg speed operand SHALL have its own node family whose identity carries the episode identity and the leg. A spec without it SHALL
have the same node set and results as before this change.

#### Scenario: Level candidates share the operands

- **WHEN** a batch contains candidates that differ only in a level over a ratio of two leg speed operands
- **THEN** both operands and the ratio SHALL each be computed once per batch per side.

### Requirement: Impulse ATR identity and cost

An impulse ATR operand SHALL have its own node family whose identity carries the episode identity and the ATR column identity. A
spec without it SHALL have the same node set and results as before this change.

#### Scenario: Level candidates share the operand

- **WHEN** a batch contains candidates that differ only in a level over the same impulse ATR operand
- **THEN** the operand and its ATR column SHALL each be computed once per batch per side.

### Requirement: Leg bars identity and cost

A leg bars operand SHALL have its own node family whose identity carries the episode identity and the leg. A spec without it SHALL
have the same node set and results as before this change.

#### Scenario: Level candidates share the operands

- **WHEN** a batch contains candidates that differ only in a level over a ratio of two leg bars operands
- **THEN** both operands and the ratio SHALL each be computed once per batch per side.

### Requirement: Forming candle identity and cost

A forming candle operand SHALL have its own node family whose identity carries the episode identity, the timeframe and the ATR
column. A spec without it SHALL have the same node set and results as before this change.

#### Scenario: Level candidates share the operand

- **WHEN** a batch contains candidates that differ only in a level over the same forming candle operand
- **THEN** the operand SHALL be computed once per batch per side.

### Requirement: Leg efficiency identity and cost

A leg efficiency operand SHALL have its own node family whose identity carries the episode identity and the leg. A spec without it
SHALL have the same node set and results as before this change.

#### Scenario: Level candidates share the operands

- **WHEN** a batch contains candidates that differ only in a level over a ratio of two leg efficiency operands
- **THEN** both operands and the ratio SHALL each be computed once per batch per side.

### Requirement: Open interest in the shared market arrays

The shared market arrays of one evaluation or range batch SHALL serve `open_interest` through the same lazily converted, cached `values` and `array` reads as the OHLCV fields: one float per bar, converted from the bar's Decimal, and NaN where the bar has no open interest. A missing value SHALL NOT be filled from another bar or replaced by zero. The OHLCV field set and the OHLCV columns SHALL NOT include open interest. The indicator DataFrame SHALL carry it as a last float64 column `open_interest` with the same values, and a higher-timeframe candle SHALL take the value of its last base bar, NaN when that bar has none, never a sum or an earlier bar's value.

#### Scenario: Open interest on a higher timeframe
- **WHEN** a 1h candle is built from twelve 5m bars and its last bar has no open interest
- **THEN** its `open_interest` is NaN, even when earlier bars of the candle have values

#### Scenario: Open interest with gaps
- **WHEN** a range has open interest on some bars and none on others
- **THEN** `array("open_interest")` is a read-only float64 array with each bar's own value and NaN on the bars without one
- **AND** repeated reads in the same evaluation return the same cached array.

#### Scenario: Existing computations are unchanged
- **WHEN** any strategy that does not read open interest is evaluated on bars that carry open interest
- **THEN** its OHLCV columns, feature values, intermediate results and output are bit-identical to the evaluation of the same bars without open interest.

### Requirement: Leg change identity and cost

A leg change operand SHALL have its own node family whose identity carries the episode identity, the leg, the field and the touch.
A spec without it SHALL have the same node set and results as before this change.

#### Scenario: Level candidates share the operand

- **WHEN** a batch contains candidates that differ only in a level over the same leg change operand
- **THEN** the operand SHALL be computed once per batch per side.

### Requirement: Absolute value identity and cost

An absolute value SHALL have its own node family whose upstream is the inner operand's node. A spec without it SHALL have the same
node set and results as before this change.

#### Scenario: Shared inner operand

- **WHEN** a batch contains candidates that differ only in a level over the same ratio with an absolute value
- **THEN** the inner operand, the absolute value and the ratio SHALL each be computed once per batch per side.

### Requirement: Difference identity and cost

A difference SHALL have its own node family whose upstream is its two sides' nodes. A spec without it SHALL have the same node set
and results as before this change.

#### Scenario: Level candidates share the operand

- **WHEN** a batch contains candidates that differ only in a level over the same difference
- **THEN** the difference and its sides SHALL each be computed once per batch per side.

### Requirement: At-point identity and cost

An at-point operand SHALL have its own node family whose upstream is its inner operand's node and the episode. A spec without it
SHALL have the same node set and results as before this change.

#### Scenario: Level candidates share the operand

- **WHEN** a batch contains candidates that differ only in a level over the same at-point operand
- **THEN** the at-point operand and its inner operand SHALL each be computed once per batch per side.

### Requirement: Window change identity and cost

A window change SHALL have its own node family whose upstream is its episode and its feature column. A spec without it SHALL have
the same node set and results as before this change.

#### Scenario: Level candidates share the operand

- **WHEN** a batch contains candidates that differ only in a level over the same window change
- **THEN** the window change SHALL be computed once per batch per side.

### Requirement: Signed and only-if identity and cost

Signed and only-if operands SHALL each have their own node family. The upstream SHALL be the inner operand's node, plus the requirement
operands' nodes for only-if. A spec without them SHALL have the same node set and results as before this change.

#### Scenario: Level candidates share the operands

- **WHEN** a batch contains candidates that differ only in a level over the same signed or only-if operand
- **THEN** that operand and its inputs SHALL each be computed once per batch per side.

