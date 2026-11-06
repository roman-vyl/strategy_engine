# segment-level-extrema-v1 Specification

## Purpose
Allow strategy expressions to measure indicator level extrema over current and previous episode intervals with explicit causal boundary semantics.
## Requirements
### Requirement: Level extrema on existing segments

Existing segment operands SHALL support value=level with aggregate=min or max over finite included samples of their existing supported feature series. They SHALL reuse existing current/previous same-episode point resolution. Any included nonfinite sample, missing endpoint, reversed endpoint or future endpoint SHALL produce missing, not a partial extreme. Results SHALL be available to existing arithmetic and filter predicates.

#### Scenario: Previous pullback
- **WHEN** previous peak→next_origin is requested on a touch with a previous wave
- **THEN** the endpoints SHALL be the previous wave peak and current wave origin, rather than the previous touch candle.

#### Scenario: First touch
- **WHEN** a previous-wave extreme is requested without a previous touch in the same episode
- **THEN** it SHALL be missing.

### Requirement: Explicit start exclusion and coincident endpoints

For level min/max, segment SHALL accept include_start (boolean, default true) and empty_policy (missing or end, default missing). End SHALL remain inclusive. Start exclusion SHALL precede last_n sample clipping. With empty_policy=end, valid coincident current endpoints SHALL yield the end sample even if start is excluded. It SHALL NOT repair unavailable, reversed or future endpoints or relax existing strict previous-interval ordering. Nondefault options on unsupported segment modes SHALL be rejected. Omitted defaults SHALL preserve legacy behavior and identities.

#### Scenario: Excluded peak with included entry
- **WHEN** peak=10, current=13 and include_start=false
- **THEN** extrema SHALL use samples11,12,13, including the evaluated entry candle.

#### Scenario: Entry on peak
- **WHEN** a current level-min segment has peak=current=10, include_start=false and empty_policy=end
- **THEN** it SHALL return sample10.

#### Scenario: Explicit empty segment
- **WHEN** those coincident endpoints use empty_policy=missing
- **THEN** the result SHALL be missing.

### Requirement: Composable original C6 acceptance

An example strategy SHALL express long C6 as min(RSI over current pullback) minus min(RSI over previous pullback), and short C6 as previous max minus current max. It SHALL use rsi_ewm period168, previous interval (previous P,current S], current interval (P,entry] with the coincident-entry fallback. The example SHALL use generic operands without filter-ID dispatch. Acceptance SHALL compare aligned BTC/ETH/SOL reference values and missing masks on identical history prefixes and episode points, with maximum finite absolute error at most1e-9; missing mismatches SHALL be reported and resolved.

#### Scenario: Long and short parity
- **WHEN** original C6 reference fixtures for all three coins are evaluated
- **THEN** both directions SHALL pass value and missing-mask parity, including entry-candle extrema and coincident current endpoints.

#### Scenario: Causal output
- **WHEN** candles strictly after the evaluated entry are changed or appended
- **THEN** the C6 output at that entry SHALL remain unchanged.

