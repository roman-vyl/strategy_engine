# EMA Pullback Triggers v1

The independent engine now owns all current BBB entry trigger semantics:

- `reclaim_anchor`: prior wick probe plus current close reclaim;
- `strong_reclaim_anchor`: prior close probe plus current close reclaim;
- `touch_anchor`: current range touch plus current close on the correct side.

The reclaim rolling window is deliberately shifted by one bar, so a probe on the current candle cannot satisfy the trigger. The resulting trigger mask is combined with `pre_trigger_allowed` to produce `pre_risk_entry_allowed`. Risk and final entries remain unported.
