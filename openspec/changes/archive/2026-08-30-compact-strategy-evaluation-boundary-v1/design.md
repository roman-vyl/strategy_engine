## Context

This is the Strategy Engine half of a two-repo migration. The companion
`research_service` change (`compact-strategy-evaluation-boundary-v1`
there too) covers persistence/diagnostics-artifact splitting and
Research-side execution parity. This document covers the wire-contract
shape Engine emits, the proofs behind it, and — as of this revision —
the corrected semantic model (executable entry opportunity, locked exit
profile, per-profile attribution) that supersedes this change's first
shipped draft.

**This is a revision, not a fresh document.** The first draft of this
design (sparse `StrategyDecisionEvent` with `entries`+`stop_ready`, flat
non-profile-scoped `signal_exit`, no `locked_exit_profile`, no
attribution) was implemented, tested, and route-cut-over on this branch.
A second, deeper audit (old BBB monolith execution core + current
Research consumer map + the live `strategy_engine ↔ strategy_runtime`
boundary) found that draft reintroduces a real trading-semantics defect.
Everything below the "Native fast path (confirmed, unaffected by this
revision)" section describes the corrected target; the shipped draft is
reworked to match it in I1 (see "Master Plan reference").

## Native fast path (confirmed, unaffected by this revision)

Unrelated to the semantic correction below — this was task 3.3's
resolution (Decision: Variant 3, internal-only native fast path) and
remains valid:

- `RangeIndicatorEvaluator.evaluate_native()` is the single source of
  indicator computation (native `float | None`, never string-boxed).
  `evaluate()` (the public, `ema-indicator-vertical-slice-v1`-governed
  contract) is a thin boxing wrapper over it — not a second formula
  implementation. Unchanged by this revision.
- Measured real split (task 2.1-era harness, real `full_available`
  BTCUSDT.P/5m, 675,986 bars): indicator computation ~76% of wall time,
  strategy-logic evaluation ~20%, event packaging ~4%. **The dominant
  cost is indicator computation, not event packaging** — this corrects
  an earlier assumption that a Python per-bar event-building loop was
  the bottleneck. Engine-internals vectorization of the indicator→
  strategy-layer pipeline (currently drops out of numpy/pandas into
  Python-tuple `zip()` loops immediately after native indicator
  computation) is real, larger follow-on work, explicitly deferred to a
  separate track starting only after the Master Plan's I7 checkpoint,
  using its I5 parity harness as a regression net.

## Protected boundaries (explicit invariant, not implicit)

- **Live `strategy_engine ↔ strategy_runtime` boundary is never
  modified**: `evaluate_live_entry_projection`/`evaluate_open_trade_
  projection` routes, `LiveEntryPlan`/`DesiredEntry`/
  `ExecutedTradeReceipt`/`OpenTradeProjectionResult` types, and their
  `locked_exit_profile` field. This boundary already solves the exact
  problem this change is correcting for the historical path — Engine is
  stateless per call; the caller (`strategy_runtime`) captures
  `locked_exit_profile` once at entry and round-trips it back on every
  subsequent `open-trade` call. This is the reference mechanism the
  historical path's Research-side consumer (I4) ports, not something
  this change redesigns on the live side.
- **Public indicator wire contract is never modified**: `FeatureFrame`'s
  normalized-decimal-text serialization, confirmed unchanged by the
  native-fast-path work above.

## Semantic reference: what old BBB actually proved (audit summary)

Cited here as the binding reference for I1's builder and I2's parity
scenario — not re-derived, the full citations live in the audit report
this revision is based on:

- **Locked exit profile**: both old-BBB execution paths (vectorbt/Numba
  `signal_func_nb`/`adjust_sl_func_nb`/`adjust_tp_func_nb`, and the
  managed execution loop's `_OpenPosition.locked_profile`) select an
  exit profile once at entry and hold it fixed for the trade's life;
  later-bar signal-exit/SL-TP lookups are indexed by the *locked*
  profile, never the profile active on the current bar.
- **SL/TP timing**: read only at the entry bar (`c.init_i` in the
  vectorbt path, `entry_idx` via `_agg_sl_tp_at_entry` in the managed
  path), cached for the trade's life, never re-read.
- **Exit attribution**: `ExitAttributionResult` = `exit_reason`,
  `exit_group`, `exit_profile`, `exit_component_id`, `exit_instance_id`,
  `exit_kind` (+ managed path's `exit_layer`/`exit_owner`/`role`). Built
  live during the managed loop; reconstructed post-hoc via
  `classify_exit_attribution` after simulation in the vectorbt path —
  an asymmetry between the two old paths this change's attribution must
  be correct against, regardless of which old-path behavior is the
  reference for a given exit type.
- **Multi-rule aggregation**: `_compile_distance_series`
  (`exits.py:152-179`) aggregates every applicable rule's distance for a
  leg via `min()` — identically for stop and take, no separate
  direction per leg. `_pick_distance_instance`
  (`exit_attribution.py:155-178`) selects the attribution owner: the
  applicable rule whose own distance equals the aggregate, first in the
  strategy config's declared rule order on a tie (`always_on` list then
  active profile's list, never re-sorted) — the reference model's own
  docstring states this explicitly ("first in spec on tie"), it is not
  an incidental side effect of iteration order this change is inferring.
  See the normative algorithm in the spec delta.
- **SL/TP legs are independently nullable** — `_stop_ready`
  (`exits.py:196-207`) only constrains readiness on a leg if that
  rule group has at least one configured rule for it; a group with zero
  stop rules never blocks readiness on the stop leg, and symmetrically
  for take. A strategy MAY be take-only or stop-only for a given
  `always_on`+profile combination.
- **`stop_ready` was never a standalone old-BBB concept** — it is
  effectively `entry_allowed AND protection_ready`, collapsed into
  whether an executable entry opportunity exists; old BBB never exposed
  it as its own array.

## Target shape: Historical Execution Projection

Supersedes the first draft's `StrategyDecisionEvent`
(`entries`+`stop_ready`, flat `signal_exit`, no profile, no
attribution). Exact type names are an I1 implementation decision;
illustrative shape:

```
HistoricalExecutionProjection
  contract_version: "strategy_evaluation_execution.v2"  # next version of
                              # the shipped .v1 sparse envelope family
                              # (strategy_serialization.py); normative on
                              # the wire regardless of which checkpoint
                              # first serializes it -- see
                              # strategy-research-execution-contract-v1
  provenance:
    strategy_id, config_hash, market_data_hash
    market (ticker/base_timeframe), requested_range   # bar_count and
                              # market_data_hash nest inside `market` on
                              # the wire, matching the .v1 envelope
    bar_count
  entry_opportunities: ExecutableEntryOpportunity[]
  signal_exit_events: SignalExitProjection   # indexed, see below

ExecutableEntryOpportunity
  bar_index
  side
  locked_exit_profile        # profile active AT THIS bar -- the
                              # candidate lock value if a caller treats
                              # this bar as the real entry (Engine has
                              # no trade-lifecycle state; it cannot
                              # itself prove this stays "locked" across
                              # a trade's life -- see I2 scope note)
  initial_stop: {ratio, attribution: ExitAttribution} | null   # null: no
                              # stop rule configured/applicable for this
                              # opportunity's profile -- independently
                              # nullable, matching the reference model
                              # exactly (`_stop_ready`: a leg with zero
                              # configured rules never blocks readiness)
  initial_take: {ratio, attribution: ExitAttribution} | null   # same,
                              # independently of initial_stop

ExitAttribution               # shared shape, every historical execution fact
  rule_id
  component_id
  exit_kind                   # canonical: "stop_loss" | "take_profit" | "signal"
                              # no `layer` field -- Research derives the
                              # canonical constant "exit_policy", see
                              # companion research_service capability

SignalExitProjection   # per side, per profile, sparse event list
  long:  {aligned: SignalExitEvent[], countertrend: [...], neutral: [...]}
  short: {aligned: [...], countertrend: [...], neutral: [...]}

SignalExitEvent
  bar_index
  candidates: {attribution: ExitAttribution}[]
```

**Multi-rule attribution, exact algorithm** (normative, see spec delta
for the full requirement text): aggregate distance for a leg = `min()`
over every applicable rule's distance, identically for stop and take
(not different directions per leg — corrects an earlier draft's
assumption). Attribution owner = the applicable rule whose own distance
equals that aggregate, first in the strategy config's declared rule
order (`always_on` list, then active profile's own list) on a tie —
matching the reference model's `_compile_distance_series`/
`_pick_distance_instance` verbatim, including its explicit "first in
spec on tie" behavior.

**Explicitly absent from this contract** (collapsed into
`entry_opportunities`, or moved to the diagnostic-evaluation path):
`entries[]`, `stop_ready[]`, `profile[]` (dense per-bar profile-name
array), dense SL/TP arrays, a flattened current-bar-profile
`signal_exit[]`. `entry_allowed AND protection_ready` is an internal
Engine computation, never surfaced as its own field.

**Executable-entry selection replaces the "emit whenever anything is
true" rule from the first draft.** An `ExecutableEntryOpportunity`
exists at a bar only when `entries[side][bar] AND protection_ready
[bar]` — this directly eliminates the ~676k-events-on-~676k-bars problem
the audit measured, which was caused by `stop_ready` (protection-
readiness) being true on nearly every bar and treated as its own
event-triggering field.

**Per-profile indexing, not dense per-profile arrays.** Old BBB kept all
profiles' dense arrays in-process (cheap, single-process). Exposing that
fully dense (3 profiles × 2 sides × bar_count) over HTTP would be worse
than what this change already cut. Per-profile *sparse* event lists
(only bars where that specific profile's signal actually fires) keep
the same O(events-per-profile-that-actually-fires) property as the rest
of this contract, while making the exact lookup a locked-profile trade
needs a single indexed read, not a bulk scan.

## bar_index invariant (unchanged)

`bar_index` on every projection element indexes exactly the canonical
range the response's own `market_data_hash`/`bar_count` describe —
position `i` corresponds to position `i` in Research's own `MarketFrame`
for the same `market_data_hash`. Engine SHALL NOT emit a `bar_index`
outside `[0, bar_count)`. `time_ms` remains dropped (unchanged from the
first draft — still proven redundant; see the original per-field
analysis this proposal is based on).

## Diagnostic-evaluation entrypoint — ownership and minimal contract (unchanged)

Ownership: Strategy Engine owns computing diagnostic data; Research owns
requesting and persisting it. Request identifies strategy/market/
expected-hash the same way an execution-evaluation request does.
Response provenance (`config_hash`/`market_data_hash`/`bar_count`) must
equal what the matching execution evaluation would produce; Research
fails closed on mismatch. Wire schema detail remains deferred to I1
implementation planning.

## Mutual-exclusivity invariant (unchanged)

`entries["long"][i]`/`entries["short"][i]` are proven mutually exclusive
today only because the sole `direction` component
(`ema_anchor_stack_trend`) uses strict `>`/`<`. This guarantee does
**not** live in the trigger layer itself. The Engine's entry-opportunity
emission path SHALL assert (fail loudly) if both sides are ever true on
the same bar — carried over unchanged from the first draft into the
corrected model.

## Master Plan reference (supersedes the old "Migration order" section)

This design is I0 (Spec Freeze) of a 9-checkpoint plan. Full checkpoint
definitions live in the coordinator's approved master plan (referenced
by both repos' companion changes, not duplicated verbatim here to avoid
drift between two copies — this repo's tasks.md carries the
strategy_engine-relevant checkpoints as actionable tasks). Summary of
what strategy_engine owns:

- **I1** — new domain types + a pure builder (`EmaPullbackEvaluation →
  HistoricalExecutionProjection`) from already-computed native outputs.
  No route/wire change yet — `evaluate_execution()`/routes stay on the
  currently-shipped (superseded) contract until I7.
- **I2** — prove the I1 builder against old BBB on a **profile-sensitive
  adversarial spec** (three profiles, each with distinct signal-exit +
  SL/TP, plus a profile-drift-while-open scenario) — not the always-on
  spec the first parity proof used, which cannot exercise this defect.
  Scope is per-opportunity/per-profile correctness (every
  `locked_exit_profile` value correct, every per-profile signal-exit
  stream correct, attribution correct including the deterministic
  multi-rule tie-break) — **not** a trade-lifecycle "held fixed" claim,
  which Engine has no state to prove itself (that's I4/I5).
- **I7** — coordinated single-instance-only cutover (`/range`, not
  `/range-batch`) with `strategy_runtime` and public-indicator-API
  regression fences green.
- **I8** — batch, only after I7, re-litigating whether `/range-batch`'s
  one-big-response shape is even required (shared-L0 acquisition is the
  actual requirement, not necessarily one HTTP response for N
  evaluations).

## I5 joint gate — Engine's slice (explore findings, this revision)

`research_service`'s I5 end-to-end proof (companion capability
`research-historical-execution-parity-v1`) needs one thing from Engine
that does not exist yet: a **proof-only serializer** producing the
exact `contract_version: "strategy_evaluation_execution.v2"` JSON
envelope (already normatively fixed above) from real production
computation. `strategy_serialization.py` today only serializes the
superseded `.v1` `StrategyEvaluationExecution` shape — there is no v2
equivalent anywhere, wired or unwired. Without it, Research's I5
harness has no way to obtain a real Engine-computed
`HistoricalExecutionProjection` in wire form, since `/range` is not
cut over until I7.

This is a genuinely new Engine-owned artifact (not just a Research
concern), hence the minimal companion requirement/scenario added to
`strategy-research-execution-contract-v1` above, and the corresponding
task in tasks.md (`I5.Engine`) — not a new capability, since it is one
function inside the contract this capability already governs, not new
production behavior. It is never route-wired before I7; I5's proof
calls it in-process (or via a thin script), the same way I2's own
proof already calls `build_historical_execution_projection` directly.

## Parity means (revised)

Because `time_ms` is dropped, byte-identical full-artifact comparison is
never the bar. Parity is proven when, for the same input:

- executable-entry-opportunity bars and sides are identical;
- `locked_exit_profile` is correct at every entry opportunity
  (I2-level) and, end to end (I5), correctly held fixed across each
  real trade's life;
- initial stop/take — ratio **and** rule/component attribution — are
  identical, including under the deterministic multi-rule tie-break;
- signal-exit candidates under the *locked* profile (not current-bar
  profile) are identical for every subsequent bar a position is open;
- exit attribution (`rule_id`/`component_id`/`exit_kind`/`layer`) is
  identical, trade-for-trade;
- the resulting `TradeRecord` sequence is identical (entry/exit bar
  indices, prices, quantities, fees, PnL) and accounting totals are
  exact (I5, end to end only — Engine alone cannot prove this);
- provenance is semantically equal (`market_data_hash`, `bar_count`,
  `config_hash`) — not byte-identical serialized bytes.

The profile-transition adversarial scenario is mandatory parity
evidence at both I2 (Engine-level) and I5 (end to end) — not optional,
not satisfiable by re-running the always-on spec that already passed.

## Acceptance criteria (revised)

- I2: Engine-level parity per "Parity means" (opportunity/profile/
  attribution scope) on the profile-sensitive adversarial spec, zero
  semantic diffs.
- I5: end-to-end parity per "Parity means" (full scope, including
  `TradeRecord`/accounting) on both the always-on spec (already
  measured) and the profile-sensitive adversarial spec, zero semantic
  diffs.
- Performance properties already measured on the (now-superseded) first
  draft — 11x response-body-size reduction, 54% peak-RSS reduction, 39%
  wall-time reduction vs. the original dense contract — are carried
  forward as a target for the corrected model's I1 implementation, not
  re-guaranteed by this design document alone; I1/I2 must re-measure
  once the corrected shape is built, since executable-entry-opportunity
  selection (vs. `stop_ready`-driven near-universal events) changes the
  event count profile materially.
- No dense per-bar Python-string boxing anywhere on the mandatory
  execution path (unchanged requirement, already satisfied by the native
  fast path, carried forward into the corrected model).
- N=1/2/4/11 batch memory approximately constant in N — I8 only, not
  claimed before then.

## Out of scope for this change

- Exact transport/call-pattern mechanics for I8's per-candidate release
  phase — deferred to that checkpoint's own planning.
- Full wire schema of the diagnostic-evaluation entrypoint beyond
  ownership/provenance (deferred to I1).
- Any indicator math, component semantics, or business-logic change.
- Engine-internals vectorization (separate track, post-I7).
- Any change to `strategy_runtime`/live contracts or the public
  indicator API (protected boundaries, see above).
