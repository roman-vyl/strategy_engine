# EMA Pullback Managed Policy v1 Specification

## Purpose

Define the coarse-grained managed-policy replay contract, required opened-trade inputs, strategy-owned outputs, next-bar effectiveness, execution boundary, and determinism.
## Requirements
### Requirement: Coarse-grained replay

The service SHALL evaluate one already-open trade over a requested aligned market range in one application call and SHALL NOT require one HTTP call per bar.

#### Scenario: Replay one open trade

- **WHEN** a caller requests managed replay for an aligned market range
- **THEN** the service SHALL evaluate the entire requested range in one application call.

### Requirement: Required inputs

The request SHALL include the canonical strategy input
(`strategy-evaluation-canonical-input-v1`: `strategy_id`, `raw_spec`),
canonical market range, trade identity, side, entry timestamp, and entry
price. It SHALL NOT include `strategy_version`, caller-supplied
`instance_id`, or `compatibility_profile`.

#### Scenario: Submit managed replay inputs

- **WHEN** managed replay is requested
- **THEN** the request SHALL provide the canonical strategy input and
  market data plus all required opened-trade facts.

#### Scenario: Legacy envelope field is supplied

- **WHEN** a managed-replay request's `strategy` object contains
  `strategy_version`, `instance_id`, or `compatibility_profile`
- **THEN** strict HTTP validation SHALL reject the request before
  replay begins.

### Requirement: Strategy-owned outputs

The response SHALL expose ordered phase-change, active-stop, active-take, and runtime-exit events; per-bar active policy state; and final managed state.

#### Scenario: Return a managed policy replay

- **WHEN** managed replay succeeds
- **THEN** ordered policy events, per-bar decisions, and the final managed state SHALL be returned.

### Requirement: Next-bar effectiveness

Stop, take, and runtime-exit policy changes calculated at the end of bar N SHALL identify bar N+1 as their effective boundary.

#### Scenario: Emit a policy change at bar N

- **WHEN** a stop, take, or runtime-exit decision is produced at the end of bar N
- **THEN** its effective boundary SHALL be identified as bar N+1.

### Requirement: Execution exclusion

The service SHALL NOT decide actual OHLC stop hits, fill price, fees, PnL, or exchange order status.

#### Scenario: Return managed policy without execution facts

- **WHEN** replay produces stop, take, or close decisions
- **THEN** it SHALL return policy intent only
- **AND** SHALL NOT fabricate execution or accounting facts.

### Requirement: Determinism

The same spec, market range, and trade facts SHALL produce identical events and final state.

#### Scenario: Repeat an identical managed replay

- **WHEN** identical strategy, market, and opened-trade inputs are replayed
- **THEN** the ordered events and final state SHALL be identical.

### Requirement: Candidate-wide historical projection derives from the same formulas as single-trade replay

Whenever Strategy Engine produces a `HistoricalManagedProjection` for a
candidate, every condition, distance, and rule in that projection SHALL
be derived from the exact same phase-rule, runtime-exit,
stop-management, and take-management formulas that
`/managed-replay`'s single-trade evaluator uses for the same strategy
spec. The projection evaluator SHALL NOT reuse the static exit-policy
evaluator's condition/distance logic, since that evaluator uses
different comparison semantics and does not implement the same
confirm-bars sustain window.

#### Scenario: Formula parity, not reuse of the static evaluator

- **WHEN** a managed strategy spec references a component id that also
  exists in the static exit-policy evaluator (e.g. `rsi_signal_exit`,
  `ema_cross_loss_exit`)
- **THEN** the candidate-wide projection SHALL evaluate that component
  using managed policy's own comparison operators and confirm-bars
  semantics
- **AND** SHALL NOT delegate to the static exit-policy evaluator's
  implementation of the same component id.

### Requirement: Single-trade replay evaluates composite phase conditions

The single-trade managed evaluator SHALL evaluate
`composite_phase_condition` (`ema-pullback-composite-phase-condition-v1`)
in both of its entry points:

- `POST /v1/strategy-evaluations/managed-replay`;
- the live start-after-entry projection.

It SHALL build the market part of every path once per call from the
shared fold of market children. On each bar it SHALL check trade
children with the existing atom formulas. It SHALL NOT evaluate market
children per bar through a separate code path.

For specs without `composite_phase_condition`, replay events, per-bar
decisions and final state SHALL be identical to those before this
change.

#### Scenario: Composite through managed-replay

- **WHEN** Research calls `/managed-replay` for a trade of a spec whose
  phase rule uses `composite_phase_condition`
- **THEN** the replay SHALL succeed
- **AND** the `phase_changed` events SHALL carry `component_id:
  composite_phase_condition` and the winning `path_id` in `metadata`.

#### Scenario: Existing managed spec unchanged

- **WHEN** a managed spec uses only atomic phase conditions
- **THEN** its `/managed-replay` and live open-trade outputs SHALL be
  identical to the outputs before this change.

### Requirement: Context bundle for state predicates in managed evaluation

When a composite phase condition contains a `state` predicate, directly
or inside `temporal`, the managed evaluators SHALL obtain HTF state from
the `ContextBundle` of the same frame:

- live open-trade and the historical projection SHALL use the bundle
  already built by the strategy evaluation;
- `/managed-replay` SHALL build the bundle only when such a predicate
  is present.

For all other specs, `/managed-replay` SHALL NOT build a bundle.

#### Scenario: No state predicate, no extra work

- **WHEN** `/managed-replay` evaluates a spec with no `state` predicate
  in any composite phase condition
- **THEN** no context bundle SHALL be built for the replay.

### Requirement: Phase atom `mfe_r`

A phase condition `{component_id: "mfe_r", params: {threshold}}` SHALL be
met on a bar when the trade's best excursion, measured in multiples of
its initial risk, has reached `threshold`:

`mfe_r = |mfe_price - entry_price| / initial_risk`, met when
`mfe_r >= threshold`.

- `threshold` SHALL be a positive finite number of R.
- `mfe_price` and its bar range SHALL be those of `mfe_atr` and
  `mfe_pct` (the entry bar's extremes included).
- `initial_risk` SHALL be `|entry_price - initial_stop_price|`, fixed at
  entry. It SHALL NOT change while the managed state advances, and it
  SHALL NOT depend on any bar's ATR.
- When the evaluation has no initial stop, or the initial risk is not
  positive, the condition SHALL be unmet on every bar (fail closed).
- The atom SHALL need no planned feature and no history window.

#### Scenario: Threshold in multiples of initial risk

- **GIVEN** a long entry at 100 with initial stop 98 and `threshold` 2
- **WHEN** the best price reaches 104
- **THEN** the condition SHALL be met on that bar
- **AND** it SHALL NOT be met while the best price is below 104.

#### Scenario: Initial risk is frozen

- **GIVEN** a trade whose active stop has moved after entry
- **WHEN** `mfe_r` is evaluated on a later bar
- **THEN** the denominator SHALL still be `|entry_price - initial_stop_price|`.

#### Scenario: No initial stop

- **WHEN** the evaluation carries no initial stop
- **THEN** a rule gated by `mfe_r` SHALL never fire.

#### Scenario: Start-after-entry evaluation

- **WHEN** an open trade is evaluated from its receipt
- **THEN** the receipt's initial stop SHALL be the one used.

#### Scenario: Managed replay endpoint

- **WHEN** `/managed-replay` evaluates a spec with an `mfe_r` rule
- **THEN** its request carries no initial stop, so the rule SHALL never
  fire
- **AND** that endpoint SHALL NOT be required to support `mfe_r`.

