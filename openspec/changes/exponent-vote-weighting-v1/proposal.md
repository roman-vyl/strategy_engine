## Why

Vote W8 **variant 8** for EMA200 (owner 2026-10-27 07:20 «Сохраняй как новый вариант»; 07:36 «Способ голосования делаем сразу после
компонента ема»; 08:37 «Сейчас существует линейное пороговое, а мы экспоненту сделаем… Выбор в файле спецификации»; 08:44 «Перепиши
спеку») weighs each filter in two steps:

1. the filter value is turned into a number by a table (the filter's **black curve**: excess of the stop share over the coin base, pp);
2. the vote turns that number into a weight by an **exponent** `w = (exp(k·x) − 1) / (exp(k·e_v) − 1)`, `k` and `e_v` per filter.

Then OR groups take the max, the sum is compared with θ 1.75, and the nine vote-B vetoes block alone.

The table of step 1 already exists in `weighted_vote_setup`: the ladder of steps `{level, weight}`. Today the ladder value is the weight
("linear" weighting). This change adds a second way to weigh, chosen in the strategy spec per input: **exponent**.

## What Changes

- **Weighting per input.** An input MAY carry `weighting`: absent = today's behaviour (ladder value is the weight);
  `{"exponent": {"k": …, "e_v": …}}` = the ladder value `x` gives the weight `(exp(k·x) − 1) / (exp(k·e_v) − 1)`. Per input, not per
  voter, because one OR voter holds kI (k 0.3, e_v 16) and O1 (k 0.6, e_v 20).
- **Between steps.** An input MAY carry `between: "linear"`: the ladder value goes in a straight line between neighbouring levels and
  stays at the end value outside them (as the research black curve). Default `step` = today. Needed for parity: with a pure step ladder
  the v8 masks lose 50 / 51 / 38 blocked entries on BTC / ETH / SOL (of 1045 / 866 / 898); with lines they match exactly.
- **Short operand.** An input MAY carry `short: {"operand": …}` read on the short side (Wk = −previous-week body on a short).
- **Gate.** An input MAY carry `when`: predicates of the predicate layer; when any is False the input weighs 0 and does not veto (D1v
  votes only after a strong yesterday candle).
- **Score.** With any exponent input the sum is exact over rationals (float weights at their exact binary value), order independent.
- **Trace:** `input:<id>:level_value` (ladder value before weighting) and `input:<id>:when`.
- **Unchanged:** specs without the new keys (vote B) give identical masks, evidence and identities.

Not in this change:
- operands (W8 family, kI, O1, W1d/W1r, W2d, D1v parts, Wk, EMA slope `window_change`, vol1h): PR #49 and `ema-slope-window-change-v1`
  on `claude/project-thread-teko29`;
- vol1h volume source (owner's decision pending): a config slot only; higher-timeframe OI (not used);
- how curves, k, e_v and θ are chosen (research); catalog bindings, manifests, deploy.

## Impact

- `ema-pullback-weighted-vote-setup-v1` (inputs, weights, score, evidence).
- Code: `weighted_vote_spec.py`, vote evaluation in `setups.py`, identity of the setup config, feature plan for `short`/`when` operands.
