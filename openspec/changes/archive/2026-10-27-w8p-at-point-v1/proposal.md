## Why

Research metric **W8p "open interest at the peak against its 30-day maximum"** of vote W8 for EMA200:
`W8p = OI(P) / max30d OI at P`, where P is the peak of the current touch and the OI history at P covers at least 30 days.
W8_14, W8_30 and W8r (OpenSpec `w8-rolling-extreme-v1`) read the same kind of ratio on the entry bar. W8p reads it on bar P.
Agreed with the owner on 2026-10-27 (04:42, «Давай»).

The ratio already exists. The only missing piece is reading an operand's value on a wave point of the current touch.

## What Changes

- **New operand `at_point`** `{"at_point": {"episode", "point", "operand"}}`: on every bar of a valid current touch, the value of
  the inner operand on that touch's point (`peak` = P, `origin` = S*). It is missing where the touch is not valid or the inner value
  at the point is missing.
- **W8p** is `at_point(peak, ratio({price: open_interest}, rolling_max open_interest 8640))` in the config. The Engine holds no number.
- **No look-ahead**: the point is never later than the bar (`point <= t` on a valid touch), and the inner value at the point is the
  one computed on that bar.
- **Cost**: one gather per bar; a spec without the operand pays nothing.

Not in this change: the voting module, deploy.
