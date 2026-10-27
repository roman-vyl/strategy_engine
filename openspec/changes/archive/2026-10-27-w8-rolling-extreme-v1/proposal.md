## Why

Research metrics **W8_14 and W8_30 "open interest against its recent maximum"** of vote W8 for EMA200:
`W8_d = OI(b) / max(OI over the last d days)`, with the window ending at the current record and including it. The value is
missing while the OI history is shorter than d days. Reference: `review/ema100/feat100.py` under the 5m rule
(`engine-tasks/ema200/oi5m_rule/OI_5M_RULE.md`). Agreed with the owner on 2026-10-26 (21:12, «Да», step 1 of 3 for the W8 family).

The Engine has neither a rolling maximum or minimum, nor the current bar's open interest as an operand.

## What Changes

- **New feature kinds `rolling_max` and `rolling_min`** `{period}` over a source `open`, `high`, `low`, `close` or
  `open_interest`, on any timeframe. The value is the maximum or minimum of the source over the last `period` candles, the current
  one included. It is missing until `period` finite values fill the window. On a higher timeframe the base bars see the last
  completed candle, as for every feature.
- **Open interest as a base-bar field operand**: `{"price": "open_interest"}` is accepted next to `open`, `high`, `low` and `close`.
  The value is the bar's own open interest (the Bybit snapshot at the bar's open), missing where the bar has none.
- **W8_30** is `ratio({price: open_interest}, {feature: rolling_max, source open_interest, period 8640})`, and W8_14 is the same with
  4032 (30 and 14 days of 5m bars). The periods live in the config; the Engine holds no number.
- **Live warm-up**: a rolling feature needs `period` candles of history.

Not in this change: W8r (step 2, composition of these pieces), W8p (step 3, value at a wave point), the voting module, deploy.
