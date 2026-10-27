## Why

Vote W8 **variant 8** for EMA200 (owner, 2026-10-27 07:20 «Сохраняй как новый вариант», 07:36 «Способ голосования делаем сразу после
компонента ема») does not give a voter fixed weights per threshold step, as vote B does. Each voter's weight grows smoothly with how bad
its value is:

- `e` = the voter's **black curve** at the entry's value: pooled excess of the stop share over the coin base (percentage points), linear
  between grid points, negative nodes counted as 0, the end node outside the grid;
- weight `w = (exp(k·e) − 1) / (exp(k·e_v) − 1)`, no cap; `k` and `e_v` per voter;
- several voters merged by **OR** weigh the maximum of their members;
- block when the sum of voter weights is ≥ θ (1.75), or any of the nine vote-B vetoes fires.

`weighted_vote_setup` today supports only step weights. Many steps could approximate a curve but would not equal research. OR merging
already exists: a voter weighs the largest weight of its inputs.

Two inputs of variant 8 also need small input-level options that the vote does not have yet:

- **Wk** reads the previous week body "our way": on a short it is `−candle_body_atr 1w`. A vote input has one operand for both sides.
- **D1v** is today's forming 1d candle (`forming_candle`), but only when yesterday's body is ≥ 1 ATR our way and yesterday closed in the
  top 15 % of its range our way; otherwise it does not vote.

## What Changes

- A vote input MAY carry **`curve`** `{grid, excess, k, e_v}` instead of `steps` and `direction`. Its weight is the exponent of the
  curve value as above, a float. Missing operand → weight 0. Static validation of the arrays and of overflow.
- A vote input MAY carry **`short`** `{operand}`: on the short side the input reads that operand instead (step and curve inputs).
- A vote input MAY carry **`when`**: a non-empty list of predicate-layer predicates. On a bar where any of them is False the input
  weighs 0 and does not veto.
- **Score:** a vote with at least one curve input sums voter weights exactly as rationals (each float curve weight taken at its exact
  binary value, each step weight at its exact decimal value), so the block does not depend on voter order. Without curve inputs the
  arithmetic is unchanged.
- **Trace:** `input:<id>:excess` for curve inputs; `input:<id>:when` for inputs with `when`.
- **Unchanged:** step inputs, vetoes, `count` inputs, OR as max of inputs, specs without the new keys (identical masks, evidence and
  identities).

Not in this change:
- any operand (W8 family, kI, O1, W1d/W1r, W2d, D1v parts, Wk, EMA-slope `window_change`, vol1h): they are separate OpenSpecs on
  `claude/project-thread-teko29` / PR #49 and `ema-slope-window-change-v1`;
- the volume source of vol1h (derivative vs spot/total) — owner's decision pending, a config slot only;
- higher-timeframe OI (owner 2026-10-27: not used);
- how curves, k, e_v and θ are chosen (research);
- catalog bindings, manifests, deploy.

## Impact

- `ema-pullback-weighted-vote-setup-v1` (modified inputs, weights, score, evidence).
- Code: `weighted_vote_spec.py`, the vote evaluation in `setups.py`, identity normalisation of the setup config.
