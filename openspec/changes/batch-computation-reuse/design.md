## Context

See `proposal.md - Why` for motivation and measured redundancy. Relevant current-state facts established by the prior audits (cited by file:line in the audit reports, not repeated in full here):

- Batch entrypoint: `strategies/application/evaluate_range_batch.py:EvaluateStrategyRangeBatch.execute` loads the market range once (`load_range`, already shared), then streams candidates via `_stream_variants`, which catches only `StrategyEngineError` per variant — an `AssertionError` raised deeper in the projection step (`strategies/historical_execution_projection.py`) propagates uncaught today.
- Per-variant evaluation (`strategies/ema_pullback/evaluator.py:evaluate_execution_projection`) re-derives, per candidate: a float64 `DataFrame` from the Decimal `MarketFrame` (`indicators/implementations/frame_ops.py:market_frame_to_dataframe`), all indicators via `BuildStrategyFeaturePlan` + `indicators/implementations/range_evaluator.py:evaluate_native`, and the full `contexts → context_consumption → direction_blockers → setups → triggers → risk → exits → potential_entries` chain (`strategies/ema_pullback/evaluation.py:evaluate_ema_pullback_frame`), independently of what any other candidate in the same batch already computed.
- The existing per-call caches inside `RangeIndicatorEvaluator` (`cached_frames`, `adx_dmi_cache`, `range_evaluator.py:110-113,159-168`) are scoped-memoization precedent already in the codebase, just limited to a single call rather than a batch.
- The existing `output_id` used in feature-plan deduplication (`strategies/ema_pullback/feature_plan.py`) is not a safe cross-candidate identity: it collides distinct computations (close vs open EMA(200) both hash to `ema_close_base_200`) and separates identical ones (`'base'` vs the literal base timeframe string).
- No cross-variant mutable state exists on this path; every node read during the audit was a pure function of its declared inputs.

## Goals / Non-Goals

**Goals:**
- One evaluation code path serving both single-spec and batch evaluation, differing only in root count.
- A semantic node identity that is sound: same identity implies same result; different computation never collides onto the same identity.
- A batch-scoped context that amortizes range-invariant conversion once, and memoizes any node whose identity repeats within a batch.
- Provable bit-exact parity with the current evaluator at every stage of rollout, before the next stage begins.
- No knowledge of specific research/experiment dimensions anywhere in the reuse mechanism.

**Non-Goals (design-level, in addition to proposal.md's scope exclusions):**
- Redesigning the shape of any node's *output* (e.g. switching float tuples to numpy arrays) is allowed only where it can be proven representation-equivalent (e.g. `tobytes()` comparison for float64), and is not required for correctness of reuse — it is considered separately per node family as a memory/perf detail, not a spec-level change.
- Removing computation of unread outputs (output diet) is excluded even where it looks trivial, because it changes internal computed surface, which must be validated independently of reuse (see proposal.md).
- Persisting a memo beyond the lifetime of a single range-batch call (e.g. cross-request caching) is out of scope; the context lifetime is exactly one range-batch (or single-spec) request.

## Decisions

### D1: Batch-scoped memoization with declared identities, not an explicit DAG executor
Alternatives considered: (a) scoped memoization inside the existing pipeline, keyed by component-declared identity; (b) an explicit computation DAG with its own planner/executor; (c) stage-level grouping of candidates by effective sub-spec.

Chosen: (a). Rationale, from the architecture audit's comparison:
- (b) requires a second execution engine, risking divergence from today's evaluation order and error-raising order — exactly the parity risk this change most wants to avoid. It also complicates NDJSON's lazy, request-ordered streaming (a breadth-first DAG executor would tend toward buffering).
- (c) requires each stage function to become batch-aware (N-ary), which risks the grouping key itself becoming a proxy for "which experiment dimension changed," and does not compose well across cross-stage sharing (e.g. an ATR shared between a setup and an exit rule can't be grouped at a single stage).
- (a) requires no new scheduler: the existing evaluator keeps its current execution order; each component gains a `resolve()` (produce identity from spec + upstream identities) and keeps its existing pure `compute()`. This is the smallest change that satisfies "one semantic path" and is the easiest to prove correct incrementally, because memo-disabled behavior is exactly today's behavior.

### D2: Semantic identity is a resolved, normalized value — never the raw spec or `output_id`
Each node's `resolve()` must apply the same default-normalization the current `compute()` applies internally (e.g. `int(params.get("lookback", 50))`), so the identity is computed post-defaults, not from raw JSON. `output_id` is not reused as a key (see Context). The identity is a frozen, hashable Python value (e.g. a tuple or frozen dataclass) composed of: node kind + implementation version tag, normalized effective parameters, upstream identities (recursively, not upstream *values*), side only when read, and the batch's market/range identity as an implicit root all identities are scoped under (the context itself is per-range, so the market identity does not need to be repeated inside every node's identity — but must be part of the context's own key so contexts for different ranges never share memo entries).

Alternatives considered: hashing serialized JSON of the raw spec fragment. Rejected — this reintroduces the `output_id`-style unsoundness (defaults not normalized, alias fields not resolved) and is harder to audit for the "same identity ⇒ same result" invariant than an explicit, typed identity value per node kind.

### D3: Rollout order is parity-gated per stage, not "big-bang"
Each stage in proposal.md's rollout list must pass a bitwise parity check against the golden corpus before the next stage starts, and the memo-ON/memo-OFF A/B comparison (same evaluator, same code, cache capacity flag) is the primary tool for isolating any regression, since it removes "different code path" as a confound. Node families are enabled in dependency order (indicators → direction/blocker/trigger/setup components → exit-rule/aggregate/select) so that if a regression appears, it is attributable to the most recently enabled family.

Alternative considered: enabling memoization for all node families at once after `resolve()`/`NodeSpec` lands everywhere. Rejected — a single-shot enablement makes it much harder to localize which node family's identity or compute function is unsound if a parity check fails on a large heterogeneous batch.

### D4: Common range-invariant arrays precede identity work
Class-A conversion (shared float64 OHLCV / `DatetimeIndex` / `time_ms` per batch) is done first, before `resolve()`/`NodeSpec` exist, because it requires no identity concept at all (it's not conditional reuse, it's a strict amortization of Decimal→float conversion done unconditionally once per batch) and immediately removes a proven, easily-verified cost (~1.25s+0.5s of the audited 6.4s/candidate) with the simplest possible parity check (bitwise-equal float64 arrays vs per-node conversions).

### D5: Refcount-based eviction determined up front, not LRU
Because all variants' specs are known before streaming begins (the range-batch request is fully parsed up front), refcounts per identity can be computed once before the first root is evaluated, and each memoized result can be evicted from the context the moment its refcount reaches zero. This avoids unbounded memory growth on large heterogeneous batches without needing a size-based eviction policy that could non-deterministically evict a result still needed later (a correctness risk, not just a perf one, if it forced accidental recomputation that used stale or partially-updated shared state — though today no node exposes mutable shared state, so recomputation-on-evict would still be *correct*, just wasteful; refcounting avoids relying on that fallback).

### D6: Exception memoization and replay
A node identity that raises during computation for one candidate must raise for every other candidate depending on that identity, and — per the parity requirement — must do so at the same point in each dependent candidate's own evaluation sequence as today's non-shared evaluation would. This means the context memoizes exceptions (not just successful results) keyed by identity, and re-raises a captured exception (not merely "an equivalent" exception) when a later candidate reaches that identity. The existing `StrategyEngineError`-only catch boundary in `_stream_variants`, and the uncaught `AssertionError` propagation from the projection step, are both preserved unchanged — this design does not touch that boundary.

## Risks / Trade-offs

- **[Risk] A node's `resolve()` omits a hidden effective input, causing an incorrect collision (two different computations sharing an identity).** → Mitigation: the parity harness includes explicit alias/collision probes for every known hidden-dependency category identified by the audit (timeframe aliasing, source column, side-only-when-read, declared rule order/instance_ids used only for labels vs used for computation, float multiplier normalization). No node family's memoization is enabled until its specific alias probes pass.
- **[Risk] Normalizing defaults inside `resolve()` drifts out of sync with normalization inside `compute()` over time (two places doing the same defaulting logic).** → Mitigation: `resolve()` and `compute()` for a given node should share the same normalization step/helper rather than duplicating default values; this is a design constraint on implementation, not just a hope, and is checked by the "identity equal iff outputs equal" assertion built into stage 3 of the rollout.
- **[Risk] Refcount-based eviction has an off-by-one or ordering bug, evicting a result before its last dependent has consumed it, forcing silent recomputation that could theoretically diverge if a node were ever accidentally impure.** → Mitigation: recomputation-on-miss is the existing (correct, if wasteful) fallback rather than an error, and the parity harness's heterogeneous/shuffled-order batch scenarios exercise eviction timing directly.
- **[Risk] Exception replay changes user-visible error timing or content subtly (e.g. exception object identity, traceback).** → Mitigation: parity requirement is on error *type and message/content* reaching the same point in the per-candidate stream, not on Python object identity; this is made explicit in the spec's scenarios and must be part of the golden-corpus comparison rules (compare serialized/reported error content, not `is` identity).
- **[Trade-off] This change alone does not reduce the irreducible per-candidate cost of the final projection step (1560→1560 in the audited batch), so it will not produce an order-of-magnitude wall-clock win by itself for batches dominated by projection cost rather than upstream recomputation.** → Accepted: proposal.md explicitly defers wall-clock claims to a benchmark after full rollout, and treats further optimization (parallelism, output diet) as separate, later decisions informed by that benchmark.
- **[Trade-off] Retaining node results in memory for the batch's duration has a memory cost proportional to the number of unique identities, not the number of candidates.** → Accepted as a large net improvement over today (which effectively retains nothing but pays full recomputation cost every time); D5's refcount eviction bounds retention to what is still needed.

## Migration Plan

No external migration is needed — this is an internal-only change to Strategy Engine's evaluation implementation with no HTTP contract, NDJSON schema, or Research Service change. Rollout is entirely the staged sequence in proposal.md, gated on parity at each stage, executed on the `perf/computation-reuse-audit` branch. Rollback at any stage is a revert of that stage's commits, since each stage is designed to be independently mergeable/revertible without depending on later stages having landed (later stages depend on earlier ones, not vice versa).

## Open Questions

- Exact node-family boundaries for the "exit-rule/aggregate/select" rollout stage (proposal.md groups these together; the dependency audit's finer sub-decomposition — e.g. splitting `_frame_dataframe` construction from per-rule numeric evaluation — may warrant its own sub-stage). This can be resolved during implementation planning (tasks.md) without changing this design's structure or the spec's requirements.
- Whether the shared common-array bundle (D4) should also be exposed to the single-spec (non-batch) evaluation entrypoint, or only constructed for range-batch calls. Functionally both should be correct either way (single-spec is a context of one), but this affects whether the single-spec path shares more code with the batch path immediately or only after full rollout. Does not change any spec requirement; can be decided during implementation.
