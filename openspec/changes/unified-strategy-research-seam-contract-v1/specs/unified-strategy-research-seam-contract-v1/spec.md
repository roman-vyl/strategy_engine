# Requirements

## Single physical seam

The two services SHALL describe the same cut through the same legacy callers and callees.

## Managed ownership

Strategy Engine SHALL return policy decisions only. Research Service SHALL own arbitration, fills, PnL and trade records.

## No legacy runtime

Neither service SHALL import or execute `legacy_source` in production.
