## Why

Managed phase rules gate on `mfe_pct` (a fraction of the entry price)
and `mfe_atr` (a multiple of the *current bar's* ATR). Neither says
"the trade has earned N times what it risked". The risk-relative form
is the natural unit for break-even and lock rules on strategies whose
stop and take are set in R (a stop of 3 ATR and a take of 8R), and the
current-bar ATR of `mfe_atr` drifts during the trade, so it cannot
express it.

This change adds one public trade-management atom, `mfe_r`: the trade's
best excursion in multiples of its initial risk. It is a vocabulary and
semantics change of the phase-rule DSL, so it is specified here. It is
independent of any experiment that consumes it.

## What Changes

- New phase atom `mfe_r` with `params.threshold` (> 0, in R):
  `mfe_r = MFE / initial_risk`, where `MFE = |mfe_price - entry_price|`
  as for `mfe_atr` and `initial_risk = |entry_price - initial_stop_price|`
  is frozen at entry.
- Available in atomic phase rules and as a composite phase condition
  trade child, in single-trade managed evaluation and in the
  `HistoricalManagedProjection`.
- The projection carries it as `trade_metric: "mfe_r"` with a constant
  R threshold series. The division by the trade's own initial risk is
  the executor's, because the threshold series cannot express a
  per-trade value. `TradeMetric` gains one literal.
- Live start-after-entry evaluation takes the initial stop from the
  receipt. `/managed-replay` carries no initial stop on its wire, so the
  atom is never met there; that endpoint is not extended.
- No feature planning, no new indicator, no change to the compute cost
  of specs that do not use the atom.

## Impact

- `ema-pullback-managed-policy-v1`: ADDED `mfe_r` requirement.
- `ema-pullback-composite-phase-condition-v1`: MODIFIED `Children`.
- `historical-managed-projection-v1`: ADDED `mfe_r` trade metric.
- Research Service consumes the new metric in its own change
  (`mfe-r-phase-threshold-v1`).
