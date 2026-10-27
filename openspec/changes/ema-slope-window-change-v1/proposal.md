## Why

EMA200 vote variant 8 adds one voter built from three EMA slope values of the last hour or two of the pullback (research
`review/emaslope/feat.py`). Low values mean the fast EMA turned against the trade at the end of the pullback. The owner asked
for them on 2026-10-27 (07:36, «Наклон ема делаем прямо сейчас»).

- **slope_ema100_R12**: EMA100 slope over the last 12 bars of the pullback, bp of its start value per bar.
- **slope_ema50_R24**: the same for EMA50 over 24 bars.
- **move_ema50_R24_over_impulse**: the EMA50 move over the same 24 bars as a share of the impulse height `|P − S*|`.

The window is clipped at the peak P, so it never reaches into the impulse. No existing operand reads a feature at the start of
such a clipped window, so one is needed.

## What Changes

- **New operand `window_change`** `{"window_change": {"episode", "of", "last_n", "form"}}`. On bar t of a valid current touch,
  the window is `s0 = max(P, t − last_n)`, `s1 = t`. The value is signed by side (`g` = +1 long, −1 short):
  - `form: change` gives `g · (x[s1] − x[s0])`;
  - `form: slope` gives `g · (x[s1] − x[s0]) / x[s0] / (s1 − s0) · 10⁴` (bp per bar).
  It is missing where the touch is not valid, `s1 ≤ s0`, a value at s0 or s1 is not finite, or (`slope`) `x[s0]` is 0.
- The three values are config compositions; the Engine holds no number:
  - slope_ema100_R12 = `window_change(ema 100, last_n 12, slope)`;
  - slope_ema50_R24 = `window_change(ema 50, last_n 24, slope)`;
  - move_ema50_R24_over_impulse = `ratio(window_change(ema 50, last_n 24, change), abs(difference(wave peak_price, wave origin_price)))`.
- **Cost**: one vectorised gather per bar; a spec without the operand pays nothing.

Not in this change: the vote type (exponent curve weight, OR merge), vol1h, deploy.
