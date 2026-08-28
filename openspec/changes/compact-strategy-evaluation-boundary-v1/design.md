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
   dense contract vs new sparse contract must produce byte-identical
   `TradeRecord`s, accounting totals, exit reasons, and provenance on a
   real 675,887-bar evaluation. Measure and report CPU/RSS/response body
   size for both, before and after.
2. Only after that parity is proven does `/range-batch` adopt the same
   compact per-variant result — batch gets no separate strategy
   semantics of its own; it becomes orchestration over the same fixed
   single-evaluation contract (shared-L0 acquisition unchanged, per-
   variant cost now bounded instead of linear-amplifying).

## Acceptance criteria

- Exact canonical trade/accounting parity (old contract vs new contract,
  same input, same output) on `full_available` BTCUSDT.P/5m (675,887
  bars).
- N=1 bounded, materially lower memory/CPU than today's measured
  baseline (N=1 default ≈3.60GB / N=1 minimal-options ≈2.52GB).
- N=1/2/4/11 batch memory approximately constant in N (not linear) once
  the companion `research_service` change's incremental settlement
  lands on top of this contract.
- No dense per-bar Python-string boxing anywhere on the mandatory
  execution path (diagnostics remain dense, but only inside the
  separate, optional, on-request diagnostic-evaluation path).

## Out of scope for this change

- `/range-batch` orchestration/transport (companion `research_service`
  change).
- Naming/shape of the diagnostic-evaluation capability in detail
  (companion change owns the consumer side; this change only commits to
  removing diagnostic fields from the *mandatory* response).
- Any indicator math, component semantics, or business-logic change.
