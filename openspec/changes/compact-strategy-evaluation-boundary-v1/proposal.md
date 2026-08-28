## Why

A cross-repo audit of the OLD BBB monolith (single process, no wire
boundary) versus the current split-service single-instance and batch
paths found that a real `full_available` BTCUSDT.P/5m evaluation
(675,887 bars) pegs both paths at multi-GB memory and multi-minute
CPU-bound cost — for a *single* candidate, not just for batch. Root
cause, proven from code, not assumed: `RangeIndicatorEvaluator` boxed
every bar of every planned indicator series into a Python `str`
unconditionally; `entries`/`exit_policy` were built as dense per-bar
arrays unconditionally; the wire response conflated an execution
contract, a diagnostic trace, a persistence artifact, and an HTTP DTO
into one dense object with no shared consumer. This part is fixed and
proven (see "Status" below).

**A second, deeper audit** (old BBB monolith execution core vs. current
Research consumer vs. current Engine wire contract vs. the live
`strategy_engine ↔ strategy_runtime` boundary) found that the sparse
contract this change first shipped **reintroduces a real trading-
semantics defect**, not just a transport one:

- Old BBB proved, in both its execution paths (vectorbt/Numba and the
  managed execution loop), a `locked_exit_profile` invariant: an exit
  profile (`aligned`/`countertrend`/`neutral`) is selected once at trade
  entry and held fixed for that trade's entire life — later bars use the
  *locked* profile's signal-exit/SL-TP state, never the profile that
  happens to be active on the current bar. SL/TP ratios are read only at
  the entry bar and then cached for the trade's life.
- Current Research's execution loop never implemented this at all — it
  executes only the `always_on` exit set, unconditionally, for every
  trade. The old dense Engine wire contract exposed `profile_long`/
  `profile_short`/`by_profile.*` (enough to reconstruct locked-profile
  semantics), but Research never consumed those fields.
- The sparse contract this change first shipped (`StrategyDecisionEvent`
  with `entries`+`stop_ready`, flat non-profile-scoped
  `signal_exit`/`stop_ready`, `DecisionEntry` with no profile field)
  **removes even the possibility of reconstructing this** — no per-
  profile data, no locked-profile field, no attribution beyond a bare
  `stop_loss_ratio`/`take_profit_ratio` pair.
- The live `strategy_engine ↔ strategy_runtime` boundary already solves
  the identical problem correctly and is the reference pattern: Engine
  returns a `locked_exit_profile` string once on `live-entry`; Runtime
  captures it and round-trips it back on every subsequent `open-trade`
  call, so Engine (stateless per call) is always told which profile to
  honor rather than recomputing "current" profile. This mechanism is
  untouched by this change and remains the reference to port to the
  historical path — not to be redesigned.
- Exit attribution (`rule_id`/`component_id`/`exit_kind`/`layer`) has
  the same gap: old BBB's `ExitAttributionResult` carried it in both
  execution paths (built live in the managed loop; reconstructed
  post-hoc via `classify_exit_attribution` in the vectorbt path); current
  Research's execution loop never reads Engine's `component_evidence`/
  `rule_evidence` at all, and the shipped sparse contract carries no
  attribution fields.

This is a semantic defect, not a performance regression, and it is not
acceptable to fix it by declaring "equal PnL" sufficient — proving equal
PnL without equal exit-profile/attribution semantics would validate a
contract that produces the right numbers for the wrong reasons on any
strategy spec that actually varies behavior by profile (which the
original always-on-only parity test never exercised).

## Status: superseding the shipped sparse-event model

Tasks 1–4 in `tasks.md` (sparse `StrategyDecisionEvent`, native fast
path, route cutover, N=1 payload/RSS measurement) were implemented and
merged into this branch and are **factually complete as shipped** — that
history is not rewritten. This proposal now supersedes that shape with
the corrected model below; the shipped code is reworked, not the
history erased. See "Master Plan reference" for the staged rework.

## Master Plan reference

This proposal is Spec Freeze (**I0**) of a 9-checkpoint cross-repo master
plan (`strategy_engine` + `research_service`, both `compact-strategy-
evaluation-boundary-v1`). I0 is OpenSpec-only. I1–I8 (Engine projection
builder, Engine semantics proof, Research consumer, Research execution
parity, N=1 end-to-end proof, persistence split, coordinated single-
instance cutover, batch lifetime redesign — strictly gated, one at a
time) are separate, future authorizations; this proposal does not
authorize any of them. Engine-internals vectorization (indicator
computation is ~76% of wall time, not the ~4% `build_decision_events`
step originally assumed to be the bottleneck) is an explicitly deferred,
separate track starting only after the I5 parity harness exists.

## What Changes (target model, I1+ implementation)

- **Replace `entries[]`+`stop_ready[]` with executable entry
  opportunities.** `stop_ready` does not survive as a standalone field —
  it is an internal Engine fact (`entry_allowed AND protection_ready`)
  that collapses into whether an *executable entry opportunity* exists
  at a bar. Old BBB never exposed `stop_ready` as its own array either;
  keeping it separate in the first draft of this contract preserved
  almost exactly the problem this change exists to fix (a real spec
  measured ~676k events on ~676k bars, because `stop_ready` was true on
  nearly every bar).
- **Add `locked_exit_profile` to every entry opportunity.** For each bar
  where an executable entry opportunity exists, Engine reports the exit
  profile that is active *at that bar* — this is the candidate locked
  profile if a caller treats this bar as the real entry. Engine has no
  trade-lifecycle state (it doesn't know which opportunity a caller
  actually acts on), so it cannot itself prove "held fixed for the
  trade's life" — it can and must prove the per-opportunity value is
  correct. Holding it fixed across a trade's life is a Research-side
  (I4) and end-to-end (I5) concern.
- **Add per-profile-indexed signal-exit event streams.** Instead of one
  flat `signal_exit[side][bar]`, Engine emits signal-exit events indexed
  by `(side, profile)` — a caller holding a locked profile for an open
  trade looks up only that profile's stream for later bars, never
  today's active profile. Illustrative shape, not fixed by this
  proposal:
  ```
  signal_exit_events:
    long:  {aligned: [...], countertrend: [...], neutral: [...]}
    short: {aligned: [...], countertrend: [...], neutral: [...]}
  ```
- **Add exit attribution as a first-class, non-optional field.**
  `rule_id`/`component_id`/`exit_kind` on initial stop/take and on every
  signal-exit candidate, provably equal to what old BBB's
  `ExitAttributionResult` would produce for the same input. This is a
  hard invariant (not "nice to have," not satisfied by PnL parity alone)
  — restoring old-BBB attribution semantics wherever old BBB had them,
  not preserving Research's currently-degraded always-on-only
  categorization.
- **Fix deterministic multi-rule attribution.** When multiple stop rules
  (or multiple take rules) are applicable at entry and their distances
  are aggregated into one `ratio`, which rule's `rule_id`/`component_id`
  is reported was previously undefined. This proposal requires a
  deterministic, old-BBB-compatible selection rule for: multiple
  applicable stop rules, multiple applicable take rules, and
  tied/equal distances — matching old BBB's actual aggregation-then-
  attribution logic (`_agg_sl_tp_at_entry`/`exit_attribution.py`), not
  an arbitrary new tie-break invented for this contract.
- **Drop `time_ms` from the mandatory execution response** (unchanged
  from the original proposal — still proven redundant, `bar_index` +
  `market_data_hash` + `bar_count` is the sufficient join key).
- **Split the execution contract from the diagnostic trace** (unchanged
  from the original proposal) — dense `features`/`contexts`/
  `component_evidence`/`potential_entries` remain a separate,
  explicitly-requested diagnostic-evaluation capability.
- **Keep the mutual-exclusivity guard** (unchanged) — `direction`'s
  strict-inequality property is what makes at-most-one-side-per-bar safe
  today; Engine still asserts rather than silently picking a side.

## What Does Not Change

- No change to what Research computes (execution, accounting, fills,
  fees, PnL) — Strategy Engine still computes *strategy facts*
  (executable opportunities, protection policy, signal-exit candidates),
  never *executed* trading facts (fills, PnL, equity); Research still
  owns everything downstream of a decision
  (`unified-strategy-research-seam-contract-v1` unaffected).
- No change to indicator computation math, component semantics, or any
  existing component's business logic.
- **The live `strategy_engine ↔ strategy_runtime` boundary is never
  modified by this change or any of its I1–I8 follow-ons** — `live-
  entry`, `open-trade`, `DesiredEntry`, `OpenTradeProjectionResult`, and
  their `locked_exit_profile` field stay exactly as they are; that
  mechanism is the reference pattern this change ports to the historical
  path, not something to redesign. This is stated as an explicit
  protected-boundary invariant (see spec delta), not left implicit.
- **The public indicator wire contract is never modified** —
  `ema-indicator-vertical-slice-v1` and sibling capabilities'
  normalized-decimal-text serialization is unaffected; `RangeIndicator
  Evaluator.evaluate_native()` remains the single native computation
  source, `evaluate()` remains a thin boxing wrapper over it.
- No change to `/range-batch`'s shared-L0 acquisition property itself.
  Batch production cutover is explicitly out of scope until I8 — I7
  covers single-instance `/range` only; `/range-batch` may gain schema
  compatibility with the new projection shape if technically necessary
  during I7's coordinated cutover, but that does not make it a
  production-approved execution path.
- Migration order is strictly gated (see Master Plan reference): no
  Research consumption work before Engine semantics are proven on a
  profile-sensitive adversarial spec (not the always-on spec the first
  parity proof used, which cannot exercise this defect); no persistence/
  cutover work before N=1 end-to-end parity is proven; no batch work
  before single-instance cutover is proven in production.

## Impact

- Affected capability: `strategy-research-execution-contract-v1`
  (MODIFIED requirements) — same capability as the original proposal;
  this revision corrects its target shape, does not introduce a new
  capability.
- Affected code, I1+ (deferred, not part of this I0 proposal):
  `strategies/contracts.py` (rework `StrategyDecisionEvent`/
  `DecisionEntry`/`DecisionSignalExit`/`DecisionStopReady` into the
  executable-opportunity + locked-profile + per-profile-indexed +
  attribution shape), `strategies/decision_events.py` (rework
  `build_decision_events`), `strategies/ema_pullback/evaluator.py`
  (`evaluate_execution`/`evaluate_diagnostics`), `adapters/http/
  strategy_routes.py`/`strategy_serialization.py` (wire shape, already
  cut over to the superseded shape — reworked in I1, re-cut-over only at
  I7), `strategies/application/evaluate_range.py`/
  `evaluate_range_batch.py` (result shape only).
