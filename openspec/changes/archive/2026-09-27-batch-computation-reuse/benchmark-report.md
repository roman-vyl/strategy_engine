# Benchmark and follow-up decision (Group 6)

This documents the evidence already gathered during implementation (Groups 4.8's compute-count instrumentation and a dedicated wall-clock A/B benchmark run on HEAD `9fa0f8a`, unaffected by the later single-spec cutover or docstring-only commits) and records the follow-up decisions built on it. No new production changes and no new heavy benchmark runs were performed to produce this document; where the task wording asks for something not directly measured, that gap is called out explicitly rather than papered over.

## 6.1 — Compute-count results vs the pre-implementation architecture audit

### What was actually measured

All counts below are from Group 4.8's all-families-memoized instrumentation (`tests/parity/test_all_families_memo.py`), run against real Research Service sweep artifacts (`research_service/results/lab_3d_w0*_lb_ratio/request.json`). "OFF" and "ON" are actual `EvaluationContext`-recorded compute-call totals across every memoized node family (indicators, direction, blockers, triggers, setup components, mask compositions, exit-rule/aggregate/select nodes); "unique" is the number of distinct semantic identities.

| Real batch | Candidates | Total memoized-node computations OFF | ON (= unique) |
|---|---|---|---|
| 3D grid subset (width × lookback × ratio) | 27 | 1,863 | 118 |
| Width-only sweep | 35 | 2,240 | 269 |
| Untouched-lookback-only sweep | 22 | 1,364 | 243 |
| TP/SL-only sweep | 13 | 897 | 138 |

The 27-candidate 3D-grid result (**1,863 → 118**) is the headline number referenced throughout this change's review history.

Per-family breakdown is available for the 3D-grid subset specifically (from Group 4.8's report): indicator 162→8, direction 54→2, blocker 54→1, trigger 54→2, setup 162→10, mask 432→67, exit.distance 54→4, exit.aggregate 567→12, exit.select 324→12.

### Comparison against the pre-implementation architecture audit

The audit (done before any of this was implemented, on a hypothetical full 1,560-candidate grid — 3 widths × ~40 lookbacks × 13 ratios) predicted:

| Computation | Audit: current | Audit: unique |
|---|---|---|
| EMA | 4,680 | 3 |
| ATR | 1,560 | 1 |
| ATR distance | 3,120 | 14 |
| direction/trigger | 3,120 | 2 |
| setup components | 6,240 | 38 |
| setups_ok/entries | 3,120 | 240 |
| exit numeric | 1,560 | 13 |
| projection root | 1,560 | 1,560 (irreducible) |

**What matches structurally, scaled to the real 27-candidate subset:**
- EMA: audit predicts 3 unique regardless of batch size (unique count depends on the number of distinct EMA definitions requested, not candidate count) — the measured subset gives EMA 81→3, an exact structural match.
- ATR: audit predicts 1 unique; measured subset gives ATR 27→1 (the width setup's ATR(48) and the exit's ATR(48) share one identity), an exact structural match.
- ATR distance: audit predicts 3,120→14 on the full grid; the measured TP/SL-only sweep (the sweep that actually varies the full 13-point ratio axis) gives exactly 14 unique ATR-distance identities — an exact structural match on the dimension that actually drives this count.
- direction/trigger: audit lumps these into one row (3,120→2); the implementation correctly keeps them as separate identities, each independently collapsing to 2 on the 27-candidate subset (direction 54→2, trigger 54→2) — consistent once un-lumped.

**Where the audit's predictions are not directly comparable, and why (not forced to match):**
- **Setup components (audit: 6,240→38).** The real implementation's node model is finer-grained than the audit's single "setup components" row: the width setup is split into a side-free prefix (fast/slow/ATR/lookback) and a threshold-dependent suffix as two independent identities (per the audit's own granularity recommendation), and `untouched_anchor`/`ema_bounce_counter` are tracked as further separate identities. On the measured subset this gives setup 162→10 (prefix + suffix + untouched, combined). Attempting to reconstruct the audit's implied full-grid axes (3 widths × ~40 lookbacks × 13 ratios) to check against 38 produces an inconsistency: 40 distinct lookback values alone would already imply at least 40 unique `untouched_anchor` identities under either the audit's or the implementation's granularity, which is larger than the audit's own predicted total of 38 for the whole setup-component category. This means either the audit's assumed axis cardinality (40 lookbacks) does not match what "38" was actually derived from, or the audit was counting a coarser notion of "setup component" than the implementation's per-parameter identity. This is a real discrepancy in the audit's own arithmetic or methodology, not a defect in the implementation — it is flagged here rather than resolved, since resolving it would require the audit's original working, which this task does not have.
- **setups_ok/entries (audit: 3,120→240).** The measured subset's proportional equivalent (9 unique width×lookback combinations × 2 sides = 18 `setups_ok` nodes) is structurally consistent with the audit's "one setups_ok per (swept-parameter combination) × side" model, but the implementation additionally tracks `pre_setup`, `pre_trigger`, `pre_risk_entry_allowed`, `blockers_ok`, and the gated masks as their own separate identities (per the "granularity, not a single combined mask" requirement established during Group 4.6's review) — these did not exist as separate rows in the audit's coarser model. The measured `mask.*` total on the 3D-grid subset is 432→67, which has no single corresponding audit row to compare against; it is additional finer-grained information the audit's category didn't capture, not a discrepancy.
- **Exit numeric (audit: 1,560→13).** The audit treated one exit policy per candidate as a single unit. The implementation splits it into distance rules, per-profile aggregates, and profile-selects as three separate identity families. On the sweep that actually varies the exit-relevant dimension (TP/SL-only, 13 candidates), this gives 14 distance / 42 aggregate / 42 select unique identities — the audit's "13" is closest to the distance-rule count (14, off by one because the audit's model didn't separately distinguish the shared stop-loss rule from the swept take-profit rules), but the aggregate/select counts are additional detail the audit's single-row model did not represent.
- **Projection root (audit: 1,560→1,560).** Confirmed unchanged in structure: the projection is not memoized in this change (by design — see design.md's trade-off notes), so it remains one-per-candidate. Measured subset: 27→27 (implicit; not separately re-stated in the table above since it is definitionally 1:1).

**No number here was adjusted to force agreement with the audit.** Where the real, finer-grained NodeSpec model diverges from the audit's coarser categories, the divergence is explained by the granularity difference itself (a design.md-documented consequence of "find the minimal reasonable semantic unit of computation" rather than assuming the audit's row boundaries were the correct cache-unit boundaries) or, in the case of setup components, flagged as an unresolved inconsistency in the audit's own arithmetic.

### Coverage gap, called out explicitly

Task 6.1's wording asks for counts on "width, untouched, TP/SL, combined 3D grid" — all four of these were in fact measured (see the table above), so there is no coverage gap for the batch shapes named in the task. What was NOT measured is the audit's full hypothetical 1,560-candidate grid; only a 27-candidate representative subset plus three single-dimension sweeps of realistic size (13–35 candidates) were used, per Group 4.8's original scope decision to keep the parity/count gate fast to run repeatedly. Re-deriving exact counts on the full 1,560-candidate grid was not performed for this write-up and is not necessary to satisfy 6.1's actual requirement (which is to measure real counts and compare against audit predictions, not to reproduce the audit's exact candidate count) — if the full-grid count is wanted for its own sake, that is a minimal, non-production, test-only re-run of the existing `test_all_families_memo.py`-style instrumentation against the full `lab_3d_w01`–`w08` artifact set combined, not a new measurement mechanism.

## 6.2 — Wall-clock benchmark (already measured, HEAD `9fa0f8a`)

Measured via a dedicated, non-production A/B script driving the real `EvaluateStrategyRangeBatch` evaluator in-process, with `memo_enabled=False` vs `memo_enabled=True` as the only variable — same process, same codebase, same market data, same request, same candidate order.

**Workload:** BTCUSDT.P 5m, real full-history market data fetched from the local Market Data Service (684,309 bars at the time of the run; MDS ingests continuously so the exact bar count and `market_data_hash` will differ run to run, which is expected and does not affect the validity of the OFF-vs-ON comparison since both sides used the identical fetched response). Candidates: real Research Service 3D-grid sweep artifacts (`lab_3d_w0{1..8}_lb_ratio/request.json`), evenly strided for N=10/50, and the full 195-candidate `lab_3d_w01_lb_ratio` request in request order for the largest run — not N copies of one identical spec.

**Environment:** native arm64 (Apple M5, 10 cores, 24 GB RAM), Python 3.12.13, repo `.venv`. This is explicitly NOT the same environment as the pre-implementation audit's `46.6s + 7.23s×N` baseline model, and is not claimed to be directly comparable to it, because:
- the audit's fixed-cost term likely included the MDS HTTP fetch; this benchmark excluded it (market data was fetched once, saved, and replayed via a mock transport, so only in-process JSON→`MarketFrame` parsing — about 2.3s — is included in the measured fixed cost);
- this benchmark's OFF baseline already includes Group 2's shared `MarketArrays` bundle on both sides of the A/B (i.e. OFF still means "no cross-candidate memoization," not "the pre-Group-2 evaluator") — it is not the same pre-change evaluator the original audit measured;
- the market range/hash differs (today's MDS history vs. the audit's range at the time it was run);
- the production-deployed Strategy Engine container image is amd64 running under Rosetta on Apple Silicon, a third environment distinct from both this benchmark's native run and the audit's own native-arm64 conditions.

**Results:**

| N | OFF wall (median) | ON wall (median) | OFF s/candidate | ON s/candidate | Speedup |
|---|---|---|---|---|---|
| 1 (control) | 6.88 s | 6.18 s | 6.88 | 6.18 | 1.11x |
| 10 | 45.24 s | 28.53 s | 4.52 | 2.85 | 1.59x |
| 50 | 218.95 s | 115.52 s | 4.38 | 2.31 | 1.90x |
| 195 (real chunk) | 845.9 s | 390.2 s | 4.34 | 2.00 | **2.17x** |

**Marginal candidate cost** (linear slope between N=50 and N=195): OFF ≈ **4.32 s/candidate**, ON ≈ **1.89 s/candidate**.

**N=1 control note:** even a single candidate shows 1.11x, not exactly 1.0x, because one candidate can still consume some identities more than once within its own evaluation (e.g. multiple exit-node reads of the same underlying rule); this is expected and consistent with the memoization mechanism, not measurement noise.

**Correctness held throughout the benchmark:** NDJSON output was byte-identical between OFF and ON at every N; `EvaluationContext` stats showed `unforeseen_consumptions == 0` and `live_entries == 0` at the end of every run.

**What this number is not:** the 1,863→118 compute-count reduction (a ~15.8x reduction in memoized-node computation count) is not the same thing as, and must not be read as implying, a 15.8x wall-clock speedup. The measured wall-clock speedup tops out at **2.17x** on the largest real batch measured (N=195), because a substantial, non-memoized, per-candidate cost remains — most visibly the projection step (irreducible, one per candidate by design) and the per-candidate DataFrame/array materialization work the original audit already identified as separate from the memoizable computation nodes (e.g. `_frame_dataframe`, `_optional_floats` conversions) — none of which this change touches. The residual ~1.9–2.0 s/candidate at large N is the size of that remaining, non-memoized, per-candidate work, not measurement error.

## 6.3 — Conclusions and follow-ups

### Main proven conclusion

Universal, semantics-driven computation reuse (a NodeSpec identity + batch-scoped `EvaluationContext` memo, with no special-casing of which experiment parameter a sweep varies) delivers real, batch-size-growing wall-clock speedup on realistic Research Service parameter sweeps — measured at **2.17x** on a real 195-candidate sweep, with the marginal per-candidate cost dropping from ~4.3s to ~1.9s — while preserving:
- **Bit-exact Strategy Engine parity**: every intermediate (indicator values, masks, entries, exit-policy fields, projection, NDJSON bytes) proven byte-identical between the pre-reuse and reuse-enabled evaluator across the full golden/parity corpus (homogeneous, partially-shared, fully heterogeneous, shuffled-order, duplicated-spec batches), including the deliberately-preserved legacy EMA source-collision behavior.
- **Semantic-content parity of downstream Research Service artifacts**: proven end-to-end against a real 195-candidate batch run through the real Research Service pipeline, comparing 1,560 persisted run files (188,229 trades, 376,458 execution events) between the pre-change and post-change Strategy Engine — zero differences after excluding only genuinely non-deterministic fields (run_id, its timestamp, and the run-id-derived artifact path).
- **One evaluation path**: `/range` and `/range-batch` now both flow through the identical `EvaluationContext` mechanism (a context of one root vs. N roots), with no per-experiment-dimension branching anywhere in the reuse logic.

### Deliberately deferred follow-ups (explicitly NOT part of this change)

1. **Profile the memo-ON residual cost (~1.9–2.0 s/candidate at large N)** before deciding on any further optimization. This change did not investigate where that residual time goes (projection loop vs. per-candidate DataFrame/array conversions vs. something else) — that profiling is the natural next step, not a continuation of this change.
2. **Output diet** (removing computation of currently-unread outputs — `potential_entries`, unused exit traces, unused distance aggregates, etc., which the original audit flagged and every Group 4 stage explicitly declined to touch) — only after the residual-cost profile above identifies it as worth doing.
3. **Parallelism** across independent candidates/identities — only after the residual-cost profile; not evaluated at all in this change.
4. **ARM64 / native deployment image migration** — a separate, purely operational/infrastructure decision, unrelated to this change's code.
5. **`EvaluationContext` cleanup of retained entries after an uncaught mid-batch exception** (Group 4.8's observation: roots that never started keep their predicted entries until the abandoned context is garbage-collected — not a correctness bug, just lifecycle hygiene under abnormal termination). Left open, not fixed here.
6. **Legacy `.v1` surface removal** (`EvaluateStrategyRange.execute()`/`evaluate_execution()`/`serialize_strategy_evaluation_execution`) — confirmed unreachable from any production route, but explicitly required to be retained by the separate `strategy-research-execution-contract-v1` spec. Any future removal needs its own change with an explicit delta to that spec and a cross-repo impact audit; out of scope here.

None of these six items were implemented, profiled, or otherwise acted on as part of finishing this change — they are recorded here as the follow-up backlog this change's evidence supports, not as work already started.
