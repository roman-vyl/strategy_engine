## Why

Pullback strategies on an anchor EMA need to know where the current bar sits inside the trend that the EMA stack describes:

- whether the stack has formed and how long ago;
- which touch of the anchor this is;
- whether price is sawing at the line or has broken through it;
- how long and how strong each up leg and each down leg of the trend were.

The only component that tracks a trend episode today is `ema_bounce_counter_setup`. It keeps that state internally, counts touches from any side with a fixed window, resets on a one-bar stack break, and exposes nothing but its own mask. Nothing else can read the episode, and the legs between touches are not modelled at all.

This change adds the episode as a strategy context: a strictly causal, per-bar description of the EMA stack episode and its waves. Any predicate can query it, as of the bar being evaluated, without knowing the bars to the right.

## What Changes

- New context provider `ema_stack_episode` under `raw_spec.contexts`, beside `htf_context`. It is not a setup, trigger or blocker.
- Episode and touch rules (long; short is the mirror):
  - The episode starts at S0, the first bar where `fast > anchor > slow`.
  - It ends when that order is violated for more than `break_bars` consecutive bars.
  - A touch is counted only on an approach against the trend: the previous bar lies wholly above the anchor and the current bar's low reaches it.
  - A touch opens a zone. Contacts at least every `window_bars` bars extend the zone under the same number, and so do dips wholly below the line of at most `window_bars` bars.
  - A zone ends after `window_bars` bars without contact.
  - More than `window_bars` bars wholly below the line is a false break. The number stays.
  - The comeback above the line after a false break gets no number. Only the next approach from above gets the next number.
  - If the stack breaks instead, the last number stays last.
- Per-bar data model per side:
  - episode fields: `episode_id`, `bars_since_s0`, `censored`, `touch_number`, `phase` (`none`, `away`, `in_zone`, `false_break`) and events;
  - wave fields: the S and P points and the up and down legs of every wave `k`, plus the forming wave toward the next touch.
- New predicate operand `{"episode": {"context_ref", "field", "wave"}}` beside `feature`, `price` and `const`. It is usable in `compare` and `range`, and through `temporal`.
- The strategy range result carries the episode series and a per-episode table of zones and legs for inspection.
- Live history: an explicit `history_bars` parameter plus the EMA warm-up. An episode that starts at the first bar of the window is flagged `censored` and fails closed.
- Specs without `ema_stack_episode` are unchanged: same values, labels, `plan_hash`, node identities and compute counts.

## Impact

- ADDED capability `ema-stack-episode-context-v1`.
- `ema-pullback-context-bundle-v1`: MODIFIED `Strategy-owned context construction`; ADDED `Episode context in the API result`.
- `pre-entry-predicates-v1`: MODIFIED `Supported predicate classes`; ADDED `Episode operands`.
- `live-calculation-window-planning`: ADDED `History policy for the EMA stack episode context`.
- `batch-computation-reuse`: ADDED `Identity of the EMA stack episode context` and `No compute regression without the EMA stack episode context`.
- Not modified: `ema_bounce_counter_setup`, `untouched_anchor_setup`, triggers, exits, the managed state machine and `historical-managed-projection-v1`.

## Verification

- Hand-built bar sequences for every rule:
  - approach versus comeback;
  - saw with a short dip;
  - zone end after `window_bars`;
  - false break with a comeback and with a stack break;
  - a stack violation of up to `break_bars` bars versus more;
  - the short mirror.
- The two owner-approved pictures, reproduced as fixtures, give exactly the drawn numbers.
- Causality: values on bar `t` are unchanged when bars after `t` are removed.
- Parity on real data: the Engine series equal the research reference counter `counter_v6.py` on BTCUSDT.P 5m for every zone.
- Identity, memo and no-regression tests. Gate: ruff, mypy, the full suite, `openspec validate ema-stack-episode-context-v1 --strict`.
