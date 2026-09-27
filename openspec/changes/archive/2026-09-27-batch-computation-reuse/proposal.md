## Why

A completed performance audit and a follow-up architectural dependency audit of the Strategy Engine batch/range-batch evaluation path established that per-candidate evaluation currently repeats a large amount of range-invariant and sub-spec-invariant computation for every candidate in a parameter sweep, even when the effective computation is identical across candidates. On a real 1560-candidate 3D grid (width threshold × untouched-lookback × TP/SL sweep), the audit measured:

| Computation | Current calls | Semantically unique |
|---|---|---|
| market → dataframe conversion | 1560 | 1 |
| EMA | 4680 | 3 |
| ATR | 1560 | 1 |
| ATR distance | 3120 | 14 |
| direction/trigger | 3120 | 2 |
| setup components | 6240 | 38 |
| setups/entries | 3120 | 240 |
| exit numeric policy | 1560 | 13 |
| final projection | 1560 | 1560 (irreducible) |

The audit also established that every node on this path is a pure, deterministic function of (market/range identity, normalized effective local config, upstream results, side-if-read), with no cross-variant mutable state. That means a universal, semantics-driven reuse mechanism is possible — one that reuses a computation whenever two candidates happen to need the exact same thing, without ever knowing which experiment parameter a sweep is varying. This is architecturally far more significant than any Rosetta/ARM64 deployment fix, and does not require branching batch evaluation into special-cased "fast paths" per swept parameter.

This change proposes introducing that reuse mechanism now, before any other optimization (parallelism, output diet, ARM64 migration), because it removes genuine duplicate work rather than papering over it, and because doing it first makes any later optimization's baseline meaningful.

## What Changes

- Introduce an explicit **semantic node identity** (`NodeSpec`) for each computation node on the evaluation path (indicators, context/gate, direction, blockers, setup components, triggers, exit-rule/aggregate/select nodes), derived from node kind + version, normalized effective config (post-defaults), identities of upstream nodes, and side only when the node actually reads it, rooted in the market/range identity. This identity is **not** the existing `output_id` field, which the audit found to be semantically unsound (it collides distinct computations — e.g. close vs open EMA(200) both hash to `ema_close_base_200` — and splits identical ones — e.g. `'base'` vs `'5m'` timeframe aliasing). The identity contract is: semantically equivalent normalized inputs/dependencies produce the same identity; semantically distinct computation never produces the same identity; same identity implies bit-identical result. Coincidentally equal output values between two distinct computations do **not** imply, and must never be used to infer, a shared identity.
- Introduce a **batch-scoped `EvaluationContext`** that: (a) holds range-invariant common arrays (float64 OHLCV, `DatetimeIndex`, `time_ms`) shared by all candidates in one range-batch call, replacing repeated per-node Decimal→float conversion; (b) memoizes `identity → immutable computed result` for the lifetime of one range-batch call, with lifetime managed by refcounts computed from all variants' `NodeSpec`s before streaming begins.
- Preserve exactly **one evaluation context implementation and one shared range-input representation** for both single-spec and batch evaluation. A single-spec request is a context with one root; a batch is a context with N roots. The final architecture has no permanent, separate preparation/evaluation path for single-spec — single-spec is the same mechanism specialized to one root. No per-experiment-dimension branching is introduced anywhere (no "if the sweep varies X use path A" logic).
- Preserve NDJSON streaming semantics exactly: lazy per-root evaluation in request order, unchanged first-byte latency, unchanged per-variant error isolation.
- Preserve observable failure semantics exactly: a failing shared node must produce the same failure category, message/payload, evaluation-sequence position, and caught-vs-propagated behavior for every dependent variant as the pre-change evaluator, via a memoized immutable failure representation (not a requirement to reuse the same Python exception object or traceback); the existing distinction between `StrategyEngineError` (caught per-variant) and `AssertionError` from the projection step (currently propagates and is not caught) must be preserved exactly.
- Roll out in the following order, each stage validated for parity against a golden corpus before proceeding — bit-exact for Strategy Engine intermediates/NDJSON, semantic-content-exact (excluding non-deterministic metadata) for downstream Research Service artifacts — with no wall-clock speedup claimed until the final benchmark stage:
  1. Parity harness + golden corpus (recording every intermediate: indicator series, masks, entries, `ExitPolicyEvaluation` fields, projection object, exact NDJSON bytes) across real batches and synthetic/alias probes.
  2. Shared range-invariant common arrays (Class-A conversion), used by both single-spec and batch evaluation, proven bit-identical before any identity/memo work begins.
  3. `resolve()`/`NodeSpec` introduced per component with memoization still disabled — proves the identity contract holds (equivalent normalized inputs ⇒ same identity; distinct computation ⇒ distinct identity; no alias collisions) with zero behavior change. Identity soundness is verified against normalized inputs and dependency structure, never inferred from output-value equality.
  4. `EvaluationContext` memoization enabled incrementally per node family (indicators → direction/blocker/trigger/setup components → exit-rule/aggregate/select), each family validated bitwise memo-ON vs memo-OFF in the same evaluator before the next family is enabled.
  5. Batch integration: `EvaluationContext` wired per range-batch call end to end, refcount eviction, failure memoization/replay.
  6. Benchmark measuring actual computation-count and wall-clock effect; only then decide whether further optimization (parallelism, output diet, ARM64) is warranted.

**Explicitly out of scope for this change** (left for later, separate changes):
- Removing computation of currently-unread outputs ("output diet" — e.g. `potential_entries`, unused exit traces/aggregates the audit found unread by the projection). This changes internal computed surface even if not externally observable and must be validated independently of reuse.
- Multiprocessing/threading/parallelism across unique nodes.
- ARM64/native image migration.
- Any change to strategy semantics, execution semantics, output contracts, or Research Service artifacts.

## Capabilities

### New Capabilities
- `batch-computation-reuse`: Defines the semantic node identity contract and batch-scoped evaluation context that allow the Strategy Engine to reuse a computation across candidates whenever, and only whenever, it is semantically identical — with a single evaluation path for both single-spec and batch requests, bit-exact parity of Strategy Engine outputs with the pre-change evaluator, and semantic-content parity of downstream Research Service artifacts.

### Modified Capabilities
(none — this change introduces an internal reuse mechanism; it must not alter the observable requirements of any existing capability. Every existing spec's behavior is preserved bit-for-bit and is validated, not modified, by this change.)

## Impact

- **Affected modules** (Strategy Engine, `src/strategy_engine/`): `strategies/application/evaluate_range_batch.py`, `strategies/application/evaluate_range.py`, `strategies/ema_pullback/evaluator.py`, `strategies/ema_pullback/evaluation.py`, `strategies/ema_pullback/{contexts,context_consumption,direction_blockers,setups,triggers,exits,risk,potential_entries}.py`, `strategies/historical_execution_projection.py`, `indicators/application/evaluate_range.py`, `indicators/implementations/{range_evaluator,frame_ops}.py`, `strategies/ema_pullback/feature_plan.py`.
- **Not affected**: Research Service, Market Data Service, SE HTTP contracts, NDJSON wire format, strategy/execution semantics, output artifacts. Downstream Research Service trades/fills/fees/PnL/cumulative R/metrics/provenance must remain identical in semantic content, excluding non-deterministic metadata such as `run_id` and timestamps.
- **Dependencies**: relies on findings from the prior performance audit and architectural dependency audit (both already completed, referenced above); no new external dependencies introduced.
- **Risk**: primarily correctness-parity risk (silent semantic drift from a bad identity or unsafe reuse), mitigated entirely by the staged, parity-first rollout with bitwise validation at every stage before the next is enabled.
