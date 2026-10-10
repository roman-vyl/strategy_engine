## MODIFIED Requirements

### Requirement: Recursive indicator convergence warm-up

For indicators computed recursively (where a fixed bar count does not fully bound the influence of prior history), the planner SHALL use a convergence warm-up: a history length long enough that the influence of an arbitrary initial seed value falls below a fixed tolerance by the target bar.

For an exponential-moving-average-style indicator with smoothing factor `alpha`, the seed influence after `n` bars decays as `(1-alpha)^n`; the warm-up requirement SHALL be derived from `(1-alpha)^n < tolerance`, not from `alpha^n`.

The Wilder-smoothed ADX/DI cascade (recursive smoothing of TR/+DM/-DM followed by a second recursive smoothing pass to produce ADX) SHALL be resolved as its own recursive requirement, using Wilder's decay factor, independently from the exponential-moving-average policy above.

The MACD cascade (`macd`, `macd_signal`, `macd_hist`: two EMAs of the close, then an EMA of their difference) SHALL be resolved as the EMA convergence bars of `slow` plus the EMA convergence bars of `signal`, at the EMA tolerance, a sufficient bound for all three kinds.

Indicators whose full history dependence is bounded by a fixed bar count (no recursive seed-influence term) SHALL be resolved as finite-window requirements instead.

#### Scenario: EMA-based indicator in the spec

- **WHEN** the indicator plan includes an exponential-moving-average-style indicator
- **THEN** the resolved requirement SHALL express a bar count sufficient for `(1-alpha)^n` to fall below the fixed tolerance
- **AND** SHALL NOT treat the indicator's period alone as sufficient history.

#### Scenario: ADX/DMI indicator in the spec

- **WHEN** the indicator plan includes the Wilder-smoothed ADX/DI indicator
- **THEN** the resolved requirement SHALL be derived from Wilder's recursive smoothing decay, evaluated independently from the exponential-moving-average tolerance policy
- **AND** SHALL NOT be classified as a finite-window requirement.

#### Scenario: MACD indicator in the spec

- **WHEN** the indicator plan includes `macd_hist` with `slow` 78 and `signal` 48
- **THEN** the resolved requirement SHALL be the EMA convergence bars of period 78 plus those of period 48, in bars of the
  feature's timeframe.

#### Scenario: Finite-window indicator in the spec

- **WHEN** the indicator plan includes an indicator whose value at a bar depends only on a fixed preceding bar count
- **THEN** the resolved requirement SHALL be that fixed bar count
- **AND** SHALL NOT apply a convergence-tolerance calculation.

## ADDED Requirements

### Requirement: History policy for segment and ratio operands

A `compare` or `range` predicate whose operands include a segment or a ratio SHALL contribute the explicit
zero-additional-history entry of a current-bar predicate. The bars a segment reads back to `S*` lie inside the history of the
episode it names, which every declared episode already requires (`history_bars`), and the series' warm-up is counted by the
per-feature policy.

#### Scenario: Band filter child

- **WHEN** a composite child is a `range` over a ratio of two segments on episode `trend`
- **THEN** the child SHALL contribute a zero-additional entry
- **AND** the requirements SHALL still include `history_bars` of `trend` and the MACD warm-up.
