## Context

This is the Strategy Engine half of a two-repo migration. The companion
`research_service` change (`compact-strategy-evaluation-boundary-v1`
there too) covers persistence/diagnostics-artifact splitting and the
`/range-batch` incremental-settlement follow-on. This document covers
only the wire-contract shape Engine emits and the proofs behind it.

## Sparse decision-event shape

Per-field losslessness, proven against actual consumer code (not
designed from first principles — see the two audit passes this change
is based on):

| field | consumer read pattern | sparse representation |
|---|---|---|
| `entries[side]` | point-query at one `bar_index`, only while flat, first-true-wins (`execution/entry.py`) | one event per bar where a side fires |
| `stop_ready` | point-query at one `bar_index`, only while flat (`protection.py`) | one event per bar where it becomes true |
| `signal_exit[side]` | point-query at one `bar_index`, only while a position is open (`static_exits.py`) | one event per bar where it becomes true |
| `stop_loss_ratio`/`take_profit_ratio` | read **only at the entry bar**, cached on the position, never re-read (`protection.py::resolve_initial_protection`) | one value pair attached to the entry event only |

Proposed per-bar event shape (illustrative — exact field naming is an
implementation decision, not fixed by this proposal):

```
StrategyDecisionEvent
  bar_index
  entry: {side: "long" | "short", stop_loss_ratio, take_profit_ratio} | null
  signal_exit: {long: bool, short: bool}   # only present if either is true
  stop_ready: bool                          # only present if true
```

Only bars carrying at least one of `entry`/`signal_exit`/`stop_ready`
are emitted — for a naked-trigger strategy over 675,887 bars with a few
hundred trades, this is O(hundreds) events, not O(675,887) array
elements.

`StrategyEvaluationExecution` (the mandatory response envelope):

```
StrategyEvaluationExecution
  strategy_id, config_hash, instance_id
  market provenance (ticker/timeframe/from/to)
  market_data_hash
  bar_count
  decision_events: StrategyDecisionEvent[]
```

No `time_ms` field. No `features`/`contexts`/`component_evidence`/
`potential_entries`/`raw` on this type at all — those move to the
separate diagnostic-evaluation response, generated only on request (see
companion change).

## bar_index invariant

`bar_index` on every `StrategyDecisionEvent` indexes exactly the
canonical range the response's own `market_data_hash`/`bar_count`
describe — position `i` in that event corresponds to position `i` in
Research's own `MarketFrame` for the *same* `market_data_hash`, no
other join key is needed or provided (this is what makes dropping
`time_ms` lossless — see "Full history by default"/Q2 verification this
proposal is based on). Engine SHALL NOT emit a `bar_index` outside
`[0, bar_count)` for the range it reports. This is a strengthened,
explicit version of what `time_ms`'s validation-only equality check used
to informally guard — with `time_ms` gone, `bar_index` + `market_data_hash`
+ `bar_count` alignment is the *only* thing standing between Research and
silently executing against misaligned data, so it is stated here as a
first-class contract requirement, not left implicit.

## Diagnostic-evaluation entrypoint — ownership and minimal contract

Ownership: **Strategy Engine owns computing diagnostic data**; Research
owns requesting and persisting it (see companion change). This is not
left "TBD" — it is fixed now, even though the entrypoint's
implementation is a deferred phase (task 3.2).

Minimal cross-service contract:

- **Request**: the same three things that identify an execution
  evaluation — strategy identity (`strategy_id`, `raw_spec`), market
  provenance (ticker/timeframe/range), and `expected_market_data_hash`.
  No new identity concept is introduced; a diagnostic request is "give
  me the dense trace for the evaluation you'd produce for this exact
  execution-evaluation request."
- **Response provenance**: the diagnostic response SHALL carry
  `config_hash`, `market_data_hash`, and `bar_count` equal to what the
  matching execution evaluation for the same request would produce.
  Research fails closed (companion change) if these don't match the
  provenance already stored on the run the diagnostics were requested
  for — this prevents diagnostics silently being generated against a
  different market snapshot or strategy config than the run they claim
  to explain.
- Implementation of the entrypoint itself (route shape, application
  service) is deferred to task 3.2 — this section fixes only ownership
  and the provenance contract, not the wire schema in full detail.

## Mutual-exclusivity invariant

`entries["long"][i]`/`entries["short"][i]` are proven mutually exclusive
today only because the sole `direction` component
(`ema_anchor_stack_trend`) uses strict `>`/`<` — an exact-equality bar
makes both sides false, never both true. This guarantee does **not**
live in the trigger layer itself: `touch_anchor` alone (`close >=
anchor` for long, `close <= anchor` for short) is not exclusive at
`close == anchor`. Since a single-slot `entry` field on
`StrategyDecisionEvent` is only lossless as long as this holds, the
Engine's decision-event emission path SHALL assert (fail loudly, not
silently pick one side) if both sides are ever true on the same bar.
This makes the invariant self-enforcing rather than a documentation-only
assumption that a future `direction` component could silently violate.

## Migration order (binding on implementation, not just a suggestion)

1. Prove parity for single-instance `full_available` N=1 first: old
   dense contract vs new sparse contract must produce, for the same
   input, the same output, per the exact "Parity means" definition
   below. Measure and report CPU/RSS/response body size for both,
   before and after.
2. Adopt the same compact per-variant result on `/range-batch` — batch
   gets no separate strategy semantics of its own; it evaluates through
   the same fixed single-evaluation contract, shared-L0 acquisition
   unchanged. **This step alone does not make batch memory bounded in
   N.** The sparse contract shrinks each variant's payload
   (~700MB→~KB-scale per candidate), but `EvaluateStrategyRangeBatch
   .execute` still accumulates all N `BatchVariantOutcome`s into one
   `outcomes` list before returning, and `strategy_routes.py`'s
   `evaluate_strategy_range_batch` still builds one `{"variants":[...]}`
   response covering all N — i.e. N results are still held
   simultaneously, just each one is now small instead of huge.
3. **Separate, binding phase — per-candidate evaluate → deliver/settle →
   release.** Only after step 2, change the aggregation pattern itself so
   N candidates are evaluated, delivered to the caller, and released one
   at a time — never all N held resident simultaneously — while still
   retaining the shared-L0 property (one market acquisition, one window
   resolution, for the whole batch). The exact transport/call-pattern
   mechanics for this (e.g. Research driving N sequential single-
   evaluation calls instead of one `/range-batch` call, or Engine-side
   streaming/chunking) are an implementation decision deferred past this
   proposal — this step only fixes the requirement that whichever
   mechanism is chosen must not retain N full results simultaneously.

## Parity means (not byte-identical full artifact)

Because `time_ms` is intentionally removed from the contract, the old
and new contracts cannot produce byte-identical persisted artifacts —
that is expected, not a parity failure. Parity is proven when, for the
same input:

- the resulting `TradeRecord` sequence is identical (same trades, same
  order, same entry/exit bar indices, prices, quantities, fees, PnL);
- accounting totals are exact (net/gross PnL, fees, equity curve);
- exit reasons are exact, trade-for-trade;
- provenance is semantically equal — same `market_data_hash`,
  `bar_count`, `config_hash`, `instance_id` — not byte-identical
  serialized bytes of the full response.

## Acceptance criteria

- Parity per "Parity means" above (old contract vs new contract, same
  input, same output) on `full_available` BTCUSDT.P/5m (675,887 bars).
- N=1 bounded, materially lower memory/CPU than today's measured
  baseline (N=1 default ≈3.60GB / N=1 minimal-options ≈2.52GB).
- N=1/2/4/11 batch memory approximately constant in N (not linear) —
  this criterion applies **only after** migration-order step 3 (the
  per-candidate evaluate→deliver/settle→release phase) lands, not as an
  automatic consequence of the sparse contract alone.
- No dense per-bar Python-string boxing anywhere on the mandatory
  execution path (diagnostics remain dense, but only inside the
  separate, optional, on-request diagnostic-evaluation path).

## Out of scope for this change

- Exact transport/call-pattern mechanics for migration-order step 3
  (per-candidate evaluate→deliver/settle→release) — the requirement that
  it must not retain N results simultaneously is binding; *how* that's
  achieved (sequential single-evaluation calls, streaming, chunking) is
  deferred to implementation planning, coordinated with the companion
  `research_service` change.
- Full wire schema of the diagnostic-evaluation entrypoint (ownership and
  minimal provenance contract are fixed above; route/schema detail is
  deferred to task 3.2).
- Any indicator math, component semantics, or business-logic change.
