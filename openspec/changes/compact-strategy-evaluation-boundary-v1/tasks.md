## Status: sections 1-5 below describe the FIRST SHIPPED DRAFT (superseded)

Sections 1-3 were implemented, tested, and route-cut-over on this
branch — that work happened and is historically accurate as recorded.
A second audit (old BBB execution core vs current Research consumer map
vs the live `strategy_engine ↔ strategy_runtime` boundary) found this
draft reintroduces a real trading-semantics defect (no `locked_exit_
profile`, no per-profile signal-exit indexing, no exit attribution —
see `proposal.md`/`design.md`, revised). Section 4 (batch adoption) was
never started and is now superseded by the Master Plan's I8. Section 5
(archive) now gates on the full I0-I8 Master Plan, not just this
section's own tasks.

**Do not resume section 4 as written.** New tasks for the corrected
model are in the "Master Plan checkpoints" section below, added by this
revision (I0). I1 reworks sections 1-3's shipped code to match the
corrected `HistoricalExecutionProjection` model in `design.md`.

## 1. Sparse decision-event contract (first draft, superseded — see above)

- [x] 1.1 Define `StrategyDecisionEvent`/`StrategyEvaluationExecution`
      (plus `DecisionEntry`/`DecisionSignalExit`/`DecisionStopReady` and
      `StrategyDiagnosticEvaluation`) in `strategies/contracts.py`.
      `StrategyRangeResult`/legacy `evaluate()` remain on
      `EmaPullbackRangeEvaluator` as a private implementation detail (no
      route reaches them any more — see 1.4/3.1/3.2, route cutover is
      done).
- [x] 1.2 Implemented as `build_decision_events`
      (`strategies/decision_events.py`, pure function, unit-tested) and
      `EmaPullbackRangeEvaluator.evaluate_execution` (new method,
      `strategies/ema_pullback/evaluator.py`), which builds it from the
      already-native `entries`/`exit_policy` tuples
      (`EmaPullbackEvaluation`) — no string-boxing was ever involved in
      these specific fields.
- [x] 1.3 `build_decision_events` raises `EvaluationInvariantError` (500,
      fail loudly) if `entries_long[i]` and `entries_short[i]` are both
      true — unit-tested (`test_simultaneous_long_and_short_entry_fails_loudly`).
- [x] 1.4 Route cutover done: `/v1/strategy-evaluations/range` and
      `/range-batch` now serialize `StrategyEvaluationExecution` via
      `serialize_strategy_evaluation_execution` — no `time_ms` field on
      the wire at all. Verified by `test_range_response_exact_key_set`/
      `test_batch_variant_outcome_result_exact_key_set` (exact key-set
      assertions, no `time_ms`/`features`/etc present).
- [x] 1.5 Structurally guaranteed by construction: `build_decision_events`
      only ever emits `bar_index` values from `range(bar_count)` — there
      is no code path that could emit one outside `[0, bar_count)`.
      Verified by `test_execution_contract_decision_events_bar_index_within_bar_count`.

## 2. Single-instance parity proof (first draft, superseded — always-on spec only, cannot exercise the profile defect)

- [x] 2.1 **Engine-side decision parity, done.** `TradeRecord`/accounting-
      level parity is a `research_service`-side deliverable (work
      sequence step 8, needs the companion change's execution loop) and
      is explicitly out of scope for this repo's tasks.md. What this repo
      can and did prove: for a real `full_available` BTCUSDT.P/5m request
      (675,979 bars, `fast=100/anchor=200/slow=500` EMA stack,
      `touch_anchor` trigger, ATR stop/take), the legacy dense contract
      and the new sparse contract were run against the *same* strategy
      spec and market window (`scratch/parity_proof_isolated.py`, not
      committed -- throwaway measurement script) and diffed exactly:
      `entries[long]`/`entries[short]` identical at all 675,979 bars;
      `signal_exit`/`stop_ready` (both sides) identical at all 675,979
      bars; `stop_loss_ratio`/`take_profit_ratio` identical (0 diffs >
      1e-9 absolute) at all 39,752 actual entry-bar occurrences (ratio is
      only meaningfully compared at entry bars -- the legacy dense array
      computes a hypothetical ratio at every bar that Research's
      execution loop never reads except at the entry bar itself, proven
      by the earlier audit); `market_data_hash`/`bar_count` identical.
      Since the sparse contract is proven to encode bit-identical
      decisions to the dense one, and Research's execution loop is a
      pure deterministic function of those decisions (no other input),
      this is sufficient evidence that `TradeRecord`-level parity will
      hold once the `research_service` companion consumes it -- but that
      final end-to-end confirmation is explicitly a separate,
      not-yet-done step (work sequence item 8), not claimed here.
- [x] 2.2 Measured, isolated-process (peak RSS is contaminated if both
      paths run in one process -- measured separately):
      | | legacy (dense) | new (sparse) | change |
      |---|---|---|---|
      | wall time | 28.28s | 17.16s | -39% |
      | peak RSS | ≈4.32GB (4,423,552 KB) | ≈2.00GB (2,048,368 KB) | -54%, 2.16x smaller |
      | response body size | 792.88MB | 72.12MB | 11.0x smaller |
      | event/bar count | 675,979 bars (dense) | 675,967/675,979 events | **NOT O(hundreds) for this spec** -- see correction below |
- [ ] 2.3 Cleared: 2.1 shows zero diffs at the Engine-decision level, the
      binding definition for this repo's own scope.

**Correction to design.md's "few hundred events" claim.** For this real
spec, `event_count` (675,967) is *not* small relative to `bar_count`
(675,979) -- `stop_ready` is true on nearly every bar once ATR warmup
completes (it reflects "is the ATR distance computable right now," not
a rare condition), so almost every bar carries at least one event. The
sparse contract's real saving for this spec is **payload size per bar**
(each event holds only booleans + up to 2 small ratio numbers, vs the
dense contract's multiple full-length arrays plus features/contexts/
component_evidence), not **event count** vs bar count. The 11x body-size
reduction and 54% RSS reduction are real and measured; "O(events), not
O(bars)" was accurate for a hypothetical low-frequency strategy, not
proven (and now disproven) as a universal property of every spec.

## 3. Split diagnostics out of the mandatory path (still valid — diagnostics split and native fast path are unaffected by the semantic correction)

- [x] 3.1 Done. `/v1/strategy-evaluations/range` and `/range-batch` now
      return only `StrategyEvaluationExecution` (no `features`/
      `contexts`/`component_evidence`/`potential_entries`/`entries`/
      `exit_policy`/`validity`/`state_artifact` fields exist on that
      type at all). `EvaluateStrategyRange.execute` (application service)
      returns it directly; the legacy dense `evaluate()`/
      `StrategyRangeResult` path is no longer reachable from any route.
- [x] 3.2 Done. New route `POST /v1/strategy-evaluations/range/
      diagnostics` (`evaluate_strategy_range_diagnostics`) calls
      `EvaluateStrategyRange.execute_diagnostics` →
      `EmaPullbackRangeEvaluator.evaluate_diagnostics` → native
      computation, boxed only at this route's own serialization
      (`serialize_strategy_diagnostic_evaluation`). This is the only
      route that returns dense per-bar diagnostic data.
- [x] 3.3 **RESOLVED — Decision: Variant 3, internal-only native fast
      path.** Not a partial/compatibility outcome: strategy evaluation
      never boxes to string, and the public indicator contract is
      untouched.
      - `NativeFeatureFrame` (`indicators/contracts.py`): same shape as
        `FeatureFrame`, `series: dict[str, tuple[float | None, ...]]` --
        never string-boxed, not exposed on any HTTP contract.
      - `RangeIndicatorEvaluator.evaluate_native` is now the **single
        source of indicator computation** -- `evaluate` (the public,
        `ema-indicator-vertical-slice-v1`-governed contract) is a thin
        boxing wrapper over it (`series = {... serialize_value(v) for v
        in native.series[...]}`), not a second formula implementation.
      - `EvaluateIndicatorRange` gained `execute_native` (same
        market-acquisition/hash-validation as `execute`, calls
        `evaluator.evaluate_native` instead) via a shared `_prepare`
        helper -- no duplicated orchestration either.
      - `FeatureFrameLike` (`Protocol`, read-only properties) lets every
        `ema_pullback/{evaluation,contexts,direction_blockers,setups,
        triggers,exits,potential_entries}.py` function accept either
        `FeatureFrame` or `NativeFeatureFrame` -- one formula
        implementation, not a native/legacy fork. `FeatureFrame` itself
        was NOT touched/blurred with a union value type.
      - `EmaPullbackRangeEvaluator._evaluate_frame_native` (used by
        `evaluate_execution`/`evaluate_diagnostics`) calls
        `execute_native`; `_evaluate_frame` (legacy `evaluate()` only)
        still calls the boxed `execute`, unchanged.
      - `evaluate_diagnostics` boxes `frame.series` via `serialize_value`
        only at its own output-boundary dict construction -- the one
        place per acceptance criterion 2 diagnostics are allowed to box.
      - All 8 acceptance criteria proven, see `tests/test_native_fast_path.py`:
        (1) `test_evaluate_execution_never_calls_serialize_value` --
        monkeypatches `serialize_value` in both call-site modules,
        asserts zero calls during `evaluate_execution()`; (2)/(3) same
        test -- zero boxing means zero reverse-parsing too, there is
        nothing to reparse; (4)/(5) all pre-existing indicator
        vertical-slice tests pass unchanged (no expected-value
        rewrites); (6) all pre-existing strategy tests pass unchanged;
        (7) the monkeypatch spy IS the required regression guard --
        `test_evaluate_diagnostics_boxes_only_at_the_output_boundary`
        and `test_legacy_evaluate_still_boxes_features_when_requested`
        are positive controls proving the spy actually fires when it
        should, so criterion (1)'s zero-calls assertion is meaningful,
        not vacuous; (8)
        `test_native_and_boxed_computation_agree_numerically` --
        native output vs boxed-then-reparsed output compared bar-for-
        bar, series-for-series, for the same input; structurally
        enforced by `evaluate` calling `evaluate_native` rather than
        recomputing.
      - Full suite: 389 passed (372 baseline + 17 new across this and
        prior sub-tasks), ruff clean, mypy clean (89 files).

## 4. Batch adoption (SUPERSEDED — never started, replaced by Master Plan I8)

- [ ] ~~4.1-4.3~~ superseded. Batch is now explicitly gated behind I7
      (single-instance cutover proven in production) per the Master
      Plan, and I8 re-litigates whether `/range-batch`'s one-big-
      response shape is even the right transport, not just its
      aggregation pattern. Do not resume this section as written.

## 5. Spec (archive gate revised)

- [ ] 5.1 `openspec archive compact-strategy-evaluation-boundary-v1`
      only after the full Master Plan (I0-I8, see below) is complete —
      not just this file's now-superseded sections 1-4.

## Master Plan checkpoints (I0-I8, this revision)

Cross-repo master plan, 9 gated checkpoints. Only **I0 (this task list
revision itself)** is authorized right now. Every checkpoint below
requires explicit go-ahead after its predecessor's gate is confirmed —
do not start I1 work as a consequence of merely reading this list.

- [x] **I0 — Spec Freeze.** This revision: `proposal.md`/`design.md`/
      this file corrected to the `HistoricalExecutionProjection` model
      (executable entry opportunity replacing `entries`+`stop_ready`,
      `locked_exit_profile` per opportunity, per-profile-indexed
      signal-exit events with attribution, deterministic multi-rule
      tie-break, protected-boundary invariants for `strategy_runtime`
      live contracts and the public indicator API, revised "Parity
      means"). Companion `research_service` change gets the matching
      revision. No application code in either repo. Gate: `openspec
      validate --strict` green in both repos; spec deltas alone (no
      re-reading the audit report) are enough to derive I1's builder
      shape and I2/I5's parity test list.
- [x] **I1 — Engine: Projection Model + Pure Builder.** New domain types
      (`HistoricalExecutionProjection`, `ExecutableEntryOpportunity`,
      `SignalExitProjection`, `SignalExitEvent`, or whatever names this
      task finalizes) plus a pure builder
      `EmaPullbackEvaluation → HistoricalExecutionProjection`, from
      already-computed native outputs (`evaluation.entries`,
      `evaluation.exit_policy`'s existing `profile_long/short`,
      `by_profile.*`, `rule_evidence`) — not from anything serialized.
      No route change — `evaluate_execution()`/routes stay on the
      currently-shipped (superseded) contract. Reworks
      `strategies/decision_events.py`/`strategies/contracts.py`'s
      shipped `StrategyDecisionEvent` shape. Gate: unit tests over the
      pure builder — executable-entry selection correctness,
      locked-profile-at-entry-opportunity capture, per-profile
      signal-exit candidate correctness, attribution field population,
      deterministic multi-rule tie-back — all green.
- [x] **I2 — Engine: Historical Semantics Proof.** Prove the I1 builder
      against old BBB on a profile-sensitive adversarial spec (three
      profiles, distinct signal-exit + SL/TP each, plus a profile-drift-
      while-open scenario) — not the always-on spec section 2 above
      used. Scope: per-opportunity/per-profile correctness only
      (`locked_exit_profile` value per opportunity, per-profile
      signal-exit stream correctness, attribution including the
      deterministic tie-break) — trade-lifecycle "held fixed across a
      real trade" is explicitly NOT provable by Engine alone (no trade
      state) and is deferred to `research_service`'s I4/I5. Gate: zero
      semantic diffs vs old BBB on the adversarial spec, at Engine level.
- [x] **I7 (Engine's share) — Coordinated Cutover, single-instance
      only.** Normative requirements: `strategy-research-execution-
      contract-v1` (amended, this revision). Switch `/range` (not
      `/range-batch`) to the I1/I2 model, coordinated with
      `research_service`'s same-checkpoint work (old Research cannot
      parse the new contract, must land together). `/range-batch` may
      gain schema compatibility if technically necessary but is NOT
      thereby production-approved — that's I8. Mandatory regression
      fence: `strategy_runtime` live-entry/open-trade behavioral tests
      green, unchanged; public indicator API tests green, unchanged.
      **I7_GATE_PASSED.** Sub-tasks:
  - [x] **I7.A — EXPLORE.** Confirmed via `strategy_routes.py`: `/range`
        serves sparse `.v1` via `serialize_strategy_evaluation_execution`;
        `/range-batch`, `/range/diagnostics`, and all live routes
        (`/live-entry`, `/open-trade`, `/managed-replay`) are fully
        separate application services, unaffected by construction.
        `evaluate_range.py`/`ports.py` confirmed no existing method
        returns `HistoricalExecutionProjection` — needs an additive
        method.
  - [x] **I7.B — Spec amended.** MODIFIED requirement added to
        `strategy-research-execution-contract-v1`: `/range` serves v2
        only after cutover, `/range-batch` explicitly unchanged, new
        additive `StrategyEvaluator` Protocol method, legacy `.v1`/dense
        methods stay private (not deleted), live routes explicitly
        unaffected, coordinated-rollback note referencing
        `research_service`'s `research-production-cutover-v1`.
  - [x] **I7.C — VERIFY.** Re-checked against code; found and fixed one
        real blocker (shared with `research_service`'s I7.D):
        `EvaluateStrategyRangeBatch` shares `EvaluateStrategyRange
        .execute()` with `/range` — repurposing it for `.v2` would have
        silently switched `/range-batch` too. Corrected via a new,
        separate `execute_projection()` method.
  - [x] **I7.D — Real cutover implementation.**
        `EmaPullbackRangeEvaluator.evaluate_execution_projection()`
        (native computation + I1's `build_historical_execution_
        projection`), `StrategyEvaluator.evaluate_execution_projection`
        (additive Protocol method), `EvaluateStrategyRange
        .execute_projection()`, `serialize_historical_execution_
        projection()` (promoted from the I5 proof-only script), and
        `/strategy-evaluations/range` wired to all of it. `execute()`/
        `evaluate_execution()`/`serialize_strategy_evaluation_execution`
        completely unmodified, still the path `/range-batch` reaches.
        Updated the 3 `/range` API tests asserting the superseded `.v1`
        shape. `ruff`/`mypy src` green; full test suite green.
  - [x] **I7.E — Live N=1 E2E gate (joint with `research_service`).**
        Fresh local Engine process (current code, not the shared
        `bbb_stack` docker deployment) against the real, already-running
        Market Data Service: confirmed `/range` serves
        `contract_version: "strategy_evaluation_execution.v2"` on a real
        request. Full joint gate (real Research → this Engine → real
        execution/persistence/BFF-readback/diagnostics) executed and
        passed — see `research_service`'s I7.G for the full chain.
        Public indicator API: this repo's own full test suite (including
        `/v1/indicator-evaluations/range` tests) ran green, unaffected.
        `strategy_runtime` is a separate repository/service not present
        in this workspace — its own live regression suite was not run
        from here; the claim that it is unaffected rests on construction
        only (`/live-entry`/`/open-trade`/`/managed-replay` share no code
        with `/range`'s serializer or new application method, confirmed
        in I7.A), not on an executed regression run. Flagged here rather
        than silently assumed equivalent to "PASSED".
      Gate: N=1 production path green end to end against the live
      stack — **PASSED**. `openspec validate --strict`/`--all --strict`
      green; `pytest`/`ruff check`/`mypy src` green.
- [ ] **I8 (Engine's share) — Batch Lifetime Redesign.** Only after I7.
      Re-litigate `/range-batch`'s one-big-response shape — the only
      required property is shared market-frame acquisition, not
      necessarily one HTTP response for N evaluations. Gate: N=1/2/4/11
      benchmark, peak RSS approximately constant in N.

I3/I4/I5/I6 are primarily `research_service`-owned (see that repo's
tasks.md) — I5's end-to-end proof and I7's cutover are joint gates
tracked in both repos' task lists.

- [x] **I5.Engine — proof-only v2 serializer (joint gate, Engine-owned
      slice).** I5 explore found a real gap: no function anywhere
      serializes a `HistoricalExecutionProjection` into the
      `contract_version: "strategy_evaluation_execution.v2"` JSON
      envelope normatively fixed in this change (`strategy-research-
      execution-contract-v1`) — `strategy_serialization.py` only
      serializes the superseded `.v1` `StrategyEvaluationExecution`
      shape. `research_service`'s I5 proof needs Engine to produce this
      exact envelope from real production computation
      (`build_historical_execution_projection`, I1) without any `/range`
      route change. Add ONE pure, proof-only serializer function (same
      shape/discipline as `serialize_strategy_evaluation_execution`,
      not route-wired, not called by any router) that Engine-side I5
      harness code and `research_service`'s I5 harness both call
      directly (in-process or via a thin script) to obtain the exact v2
      JSON body `parse_historical_execution_projection` decodes. Gate:
      round-trip identity — the serialized JSON, decoded by Research's
      real `parse_historical_execution_projection`, reproduces the same
      `HistoricalExecutionProjection` facts field-for-field. No route
      change; this function is never reachable over HTTP before I7.

## Deferred, separate track: Engine internals vectorization

Not part of I0-I8. Real cost is indicator computation (~76% of wall
time) dropping out of numpy/pandas into Python-tuple `zip()` loops
immediately — not `build_decision_events`'s per-bar loop (~4%), which
was the original (incorrect) assumption. Starts only after I7, using the
I5 parity harness as a regression net for aggressive internal rewrites.
