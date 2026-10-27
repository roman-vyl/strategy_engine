## Why

Vote W8 components **Wk** and **D1v** of EMA200 give their value "our way" (research `review/d1sweep/wk_feat.py`, `d1v_feat.py`):

- Wk = g · previous-week body / weekly ATR (g = +1 long, −1 short);
- D1v = today's forming 1d candle (already side-aware), but only when yesterday's body our way is ≥ 1 ATR and yesterday's close is in
  the top 15 % of its range our way (on a short `(high − close)/range ≥ 0.85`); otherwise no value (weight 0).

The candle features (`candle_body_atr`, `candle_close_position`, OpenSpec `htf-candle-shape-v1`) have no side. The owner ruled on
2026-10-27 (10:36) that the side is the filter's job, not the vote's («Это ответственность фильтра посчитать верный знак»), so the vote
no longer carries side overrides or gates. Agreed with the owner on 2026-10-27 (10:49, «Да»).

## What Changes

- **New operand `signed`** `{"signed": {"operand", "center"}}`: `center + g · (x − center)`, `g` = +1 long, −1 short. `center` 0 negates on a
  short; `center` 0.5 maps a close position `x` to `1 − x` on a short.
- **New operand `only_if`** `{"only_if": {"operand", "require": [...]}}`: the inner value where every requirement holds on the bar, missing
  otherwise. A requirement is `{"operand", "min", "max", "bounds"?}` with the meaning of a `range`; a missing requirement value means
  "not met".
- **Wk** = `signed(1w candle_body_atr, center 0)`.
- **D1v** = `only_if(forming 1d candle, require: [signed(1d candle_body_atr, 0) ≥ 1, signed(1d candle_close_position, 0.5) ≥ 0.85])`.
- The Engine holds no number: thresholds and centers are config.
- **Cost**: one vectorised pass per operand; a spec without them pays nothing.

Not in this change: the vote type (`exponent-vote-weighting-v1`), deploy.
