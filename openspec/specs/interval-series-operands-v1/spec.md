# interval-series-operands-v1 Specification

## Purpose
Provide reusable, causal endpoint measurements of base-timeframe arithmetic series over fixed windows and current episode legs, without embedding trading-filter definitions.
## Requirements
### Requirement: Interval measurement shape

The Engine SHALL accept `interval_change` with exactly `of`, `interval`, `operation`. Operation SHALL be change, change_per_bar, relative_change or relative_change_per_bar. Unknown keys, missing fields and invalid enum values SHALL be rejected before market-data acquisition.

#### Scenario: Invalid operation
- **WHEN** an interval_change specifies operation acceleration or omits interval
- **THEN** static validation SHALL reject the spec.

### Requirement: Fixed interval

A fixed interval SHALL have exactly kind=fixed and a positive integer bars=N, excluding booleans. At evaluated base bar t it SHALL resolve a=t-N,b=t without requiring an episode or clamping to a peak. Missing history SHALL produce a missing measurement.

#### Scenario: Short pullback inside a full window
- **WHEN** t=100, N=12 and the current peak is 96
- **THEN** the fixed interval SHALL use 88..100, not 96..100.

#### Scenario: Insufficient history
- **WHEN** t=5 and N=12 in a frame starting at index zero
- **THEN** the measurement SHALL be missing, without negative-index wraparound.

### Requirement: Episode interval

An episode interval SHALL require kind=episode, ref and leg=impulse|pullback, and MAY include positive integer last_n. It SHALL use the evaluated side's current valid touch as known at t: S..P for impulse and P..t for pullback. With last_n=N its start SHALL be max(start,end-N). Unknown refs and other keys SHALL be rejected.

#### Scenario: Truncated impulse
- **WHEN** S=20, P=70 and last_n=12 at a valid touch
- **THEN** the interval SHALL use 58..70.

#### Scenario: Short pullback
- **WHEN** P=96, t=100 and last_n=12
- **THEN** the interval SHALL use 96..100.

#### Scenario: Invalid wave
- **WHEN** the current touch is invalid, endpoints lie outside the frame or a>=b
- **THEN** the measurement SHALL be missing and SHALL NOT substitute another touch.

### Requirement: Sampled arithmetic series

The of expression SHALL recursively allow base-timeframe feature, price, const, difference, ratio, abs and scale, with at least one nonconstant leaf. It SHALL reject all other operand forms and non-base feature timeframes. Arithmetic SHALL be evaluated at each sampled endpoint before measuring its change.

#### Scenario: Normalized distance
- **WHEN** of is (EMA100-EMA200)/EMA200 and operation is change
- **THEN** the result SHALL subtract the two endpoint ratios, not subtract separately normalized EMA changes.

#### Scenario: Ambiguous sampled episode expression
- **WHEN** of contains at_point, signed, segment or another interval_change
- **THEN** static validation SHALL reject it.

### Requirement: Measurement formulas and missing values

For finite u=x[a],v=x[b] and n=b-a>0, the operations SHALL return v-u, (v-u)/n, (v-u)/u and ((v-u)/u)/n respectively. Relative operations SHALL require u!=0. Nonfinite endpoints or results SHALL be missing. No implicit side sign, filling, extrapolation or clipping SHALL occur.

#### Scenario: Units and duration
- **WHEN** u=100,v=102,n=4
- **THEN** change SHALL be 2, change_per_bar .5, relative_change .02 and relative_change_per_bar .005.

#### Scenario: Interior gap
- **WHEN** both sampled endpoints are finite but an interior series value is missing
- **THEN** the endpoint measurement SHALL remain defined.

#### Scenario: Zero relative baseline
- **WHEN** u=0 and v=2
- **THEN** change SHALL be 2 and relative_change SHALL be missing.

### Requirement: Scale operand and placement

Scale SHALL have exactly operand and finite numeric factor, excluding booleans; the operand SHALL NOT be a constant. Its value SHALL be factor times the operand, with nonfinite input or output missing. Scale and interval_change SHALL be usable wherever ratio is usable, including weighted-vote inputs, but not as a change-predicate operand.

#### Scenario: Explicit basis points
- **WHEN** scale wraps a relative change of .01 with factor 10000
- **THEN** it SHALL produce 100.

#### Scenario: Zero factor with missing input
- **WHEN** factor is zero and the operand is missing
- **THEN** scale SHALL remain missing.

### Requirement: Causal evaluation and direction

The new operations SHALL read only data available at t and the episode state known at t. Measurement SHALL NOT apply trade-side orientation; an enclosing signed operand SHALL supply direction exactly once. Changing later data SHALL NOT change earlier outputs.

#### Scenario: Prefix evaluation
- **WHEN** a sufficiently warmed history ending at t is compared with a longer history sharing the same prefix
- **THEN** outputs through t SHALL agree, including missing values and both trade sides.

### Requirement: Planning and shared computation

All leaves of new expressions SHALL participate in feature and history planning and shared dependency accounting. Fixed windows SHALL extend required input history by N base intervals; episode measurements SHALL provision input history at the earliest recoverable endpoint under existing episode-history policy. Evaluation cost SHALL NOT grow with leg length per evaluated bar.

#### Scenario: Warm-up precedes the endpoint
- **WHEN** a fixed window samples a feature at t-N
- **THEN** the planned history SHALL include that feature's warm-up before t-N, not only before t.

#### Scenario: Shared expression
- **WHEN** two vote inputs use the same series and interval with different thresholds
- **THEN** shared computation SHALL return the same values as separate evaluations without missing or extra dependency-consumption errors.

### Requirement: Compatibility and evidence

Specs without new keys SHALL retain previous values, missing masks, vote decisions and node identities. New expression identities SHALL distinguish interval, operation, scale and denominator mode. Existing operand-value diagnostics and weighted-vote input evidence SHALL expose new operand values without introducing a new response envelope.

#### Scenario: Old pullback window
- **WHEN** an existing window_change or default ratio is evaluated after the addition
- **THEN** its values and identities SHALL remain unchanged.

#### Scenario: Same series different intervals
- **WHEN** a fixed interval and a truncated episode interval share the same series
- **THEN** they SHALL NOT share a measurement identity merely because their lengths sometimes coincide.

