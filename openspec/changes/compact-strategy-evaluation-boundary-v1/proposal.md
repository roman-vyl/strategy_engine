## Why

A cross-repo audit of the OLD BBB monolith (single process, no wire
boundary) versus the current split-service single-instance and batch
paths found that a real `full_available` BTCUSDT.P/5m evaluation
(675,887 bars) pegs both paths at multi-GB memory and multi-minute
CPU-bound cost — for a *single* candidate, not just for batch. Root
cause, proven from code, not assumed:

- `RangeIndicatorEvaluator.evaluate` boxes every bar of every planned
  indicator series into a Python `str` unconditionally, before any
  `include_features` flag is even consulted — turning that flag off does
  not avoid the dominant cost.
- `EmaPullbackRangeEvaluator.evaluate` builds `entries` as two full
  per-bar boolean lists per side, unconditionally, regardless of any
  option.
- `StrategyRangeResult`/the wire response conflates four things that have
  no shared consumer: an execution contract (`entries`, `exit_policy`),
  a diagnostic trace (`features`, `contexts`, `component_evidence`), a
  persistence artifact shape, and an HTTP DTO — all one dense object.
- Research's execution/accounting loop (`execution/loop.py`,
  `execution/entry.py`, `execution/static_exits.py`, `protection.py`)
  consumes every one of `entries`, `stop_ready`, `signal_exit`,
  `stop_loss_ratio`/`take_profit_ratio` via **point-queries at specific
  bar indices only** — never a dense scan or random-access pattern that
  requires the full array. This was proven per-field, with exact call-site
  citations, not assumed: `entries`/`stop_ready` are read once per bar
  only while flat (first-true-wins, at most one open position per
  instance); `signal_exit` is read once per bar only while a position is
  open; `stop_loss_ratio`/`take_profit_ratio` are read **only at the
  entry bar** and then cached on the position for its entire life — the
  ratio series is never re-read after entry.
- `entries["long"]`/`entries["short"]` are proven mutually exclusive
  per bar under the only `direction` component that exists today
  (`ema_anchor_stack_trend`: strict `>`/`<` comparisons make both sides
  false at exact equality, never both true) — but this exclusivity lives
  in `direction`, not in `triggers`/`entries` themselves (the trigger
  layer alone, e.g. `touch_anchor`, is *not* independently exclusive at
  `close == anchor`). A single-slot decision-per-bar wire shape is safe
  today but must be an asserted, guarded invariant, not a silent
  assumption, so a future `direction` component can't violate it
  unnoticed.
- `time_ms` is proven redundant on the wire: every Research consumer
  either doesn't use Engine's copy at all (`TradeRecord` timestamps come
  from Research's own `MarketFrame.candles[bar_index].open_time_ms`) or
  uses it only as a validation-only equality cross-check against data
  Research already independently has. `bar_index` + `market_data_hash` +
  `bar_count` is sufficient to unambiguously join back to Research's own
  candle at that index.

Old BBB avoided all of this because it never crossed a process boundary:
its batch was a plain sequential loop with no cross-candidate retention,
never boxed per-bar data into JSON-compatible objects, and freed each
candidate's working set before the next began. The one-JSON-response
`/range-batch` path retains N full evaluations simultaneously instead
(confirmed OOM at N=4, ~3.4GB/variant linear scaling) — but that
amplification sits on top of a defect that already exists at N=1. Fixing
batch alone (transport/incremental settlement) without fixing this
would still leave every candidate paying the same unconditional dense
cost; a research batch would remain expensive regardless of how it's
orchestrated.

This change is Strategy Engine's half of a two-repo migration
(`research_service` carries the companion change): replace the
mandatory dense per-bar wire contract with a lossless sparse
decision-event contract sized to O(events), not O(bars), and stop
returning diagnostic-only data as part of the mandatory execution
response.

## What Changes

- **Replace dense per-bar `entries`/`exit_policy` series with sparse
  decision events.** A new wire shape emits one entry per bar that
  actually carries a decision, not one entry per bar in the market
  window. Proven lossless per-field (see Design) against every
  execution/accounting consumer.
- **Drop `time_ms` from the mandatory execution response.** Replaced by
  the already-existing `market_data_hash` + `bar_count` join; Research
  already resolves its own `MarketFrame` for the same hash and already
  cross-validates against it — this removes a fully redundant
  675,887-element array from the wire, it does not remove any
  information Research doesn't already have from its own market read.
- **Split the execution contract from the diagnostic trace.** The
  mandatory range-evaluation response carries only what
  `strategy-research-execution-contract-v1` already requires for
  external execution (identity, alignment, provenance, decision
  events) — `features`, `contexts`, `component_evidence`,
  `potential_entries` move to a separate, explicitly optional
  diagnostic-evaluation capability, requested only when diagnostics are
  actually needed (see the companion `research_service` change for the
  on-demand generation flow).
- **Add an explicit mutual-exclusivity guard.** Since the single-slot
  decision-per-bar shape's safety depends on `direction`'s strict
  inequality property, not on the trigger/entries layer itself, the
  Engine asserts (fails loudly, does not silently drop) if a future
  `direction` component ever produces both sides true on the same bar.

## What Does Not Change

- No change to what Research computes (execution, accounting, fills,
  fees, PnL) — Strategy Engine still returns decisions only, Research
  still owns everything downstream of a decision
  (`unified-strategy-research-seam-contract-v1` unaffected).
- No change to indicator computation math, component semantics, or any
  existing component's business logic — only how already-computed
  per-bar decisions are represented on the wire.
- No change to `/range-batch`'s shared-L0 acquisition (one market read,
  one window resolution per batch) — this change makes each variant's
  own evaluation cheap; batch orchestration itself is the companion
  `research_service` change's concern.
- Migration order is single-instance first: this change's acceptance
  criteria require proven exact trade/accounting/exit-reason/provenance
  parity between the old dense contract and the new sparse contract on a
  real `full_available` N=1 evaluation before `/range-batch` is touched
  at all.

## Impact

- Affected capability: `strategy-research-execution-contract-v1`
  (MODIFIED requirements) — this is the capability that already defines
  "the versioned per-bar decision contract consumed by Research
  Service"; this change makes that contract sparse and splits out
  diagnostics, it does not introduce a new capability for the execution
  contract itself.
- New capability: diagnostic-evaluation projection (name TBD at
  implementation time — out of scope for this proposal to name
  precisely since it is primarily a `research_service`-side capability
  that calls back into an Engine diagnostic-evaluation endpoint; see the
  companion change for the on-demand generation flow this enables).
- Affected code (implementation deferred, not part of this proposal):
  `strategies/contracts.py` (`StrategyRangeResult` split), `strategies/
  ema_pullback/evaluator.py` (sparse event emission), `indicators/
  implementations/range_evaluator.py` (stop unconditional string-boxing
  on the mandatory path), `adapters/http/strategy_routes.py` (wire
  shape), `strategies/application/evaluate_range.py` and
  `evaluate_range_batch.py` (result shape only, no batch-orchestration
  change here).
