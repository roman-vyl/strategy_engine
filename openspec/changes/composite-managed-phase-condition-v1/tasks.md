Each group ends in a green, verifiable state. The no-regression gate
from group 0 runs again at the end of every group.

## 0. Baseline for managed specs

- [ ] 0.1 Extend the declared-invariant gate (`tests/parity/invariants.py`,
      `record_invariants.py`, `tests/test_declared_invariants.py`) with
      managed cases recorded on `main` 7b088ae, before any code change.
      The cases have atomic phase rules only and cover all four atoms,
      stop, take and runtime rules, `long` and `short`, and an HTF
      `adx_di_threshold`. Record only what this change promises to
      keep:
      - the `/range-batch` public line, including the serialized
        `managed` projection;
      - `plan_hash` and the ordered plan labels;
      - memoized node identities and compute counts;
      - `/managed-replay` responses (events, per-bar decisions and final
        state) for fixed entries on both sides;
      - live open-trade projection results for fixed receipts.
- [ ] 0.2 The gate asserts these quantities for specs without
      `composite_phase_condition` and names the invariant each one
      protects: design D5, D6, D9, D8, and the
      `batch-computation-reuse` requirement "No compute regression for
      existing managed specs". It is not a snapshot of internal
      serializations.

## 1. Static contract and parser

- [ ] 1.1 `composite_spec.py`:
      - the structure parser takes a child parser (design D2);
      - `composite_setup` passes its current child parser, and its
        behavior and messages are unchanged;
      - add the phase child parser (`predicate` | `condition` with the
        four-atom allowlist);
      - add an optional `condition` field on `CompositeChild`.
- [ ] 1.2 `static_semantics.py`: validate every
      `composite_phase_condition` in `phase_rules` (design D1, D10):
      - structure and references;
      - predicates through `parse_predicate` with `context_refs`;
      - the atom allowlist;
      - no nesting, no setup children, no unknown fields.
      Atomic rules are not newly validated.
- [ ] 1.3 Unit tests:
      - one rejection per rule in design D1, including a bare predicate
        as `condition`, a nested composite, `mfe_r`, a setup child, an
        unreferenced child, bad `k` and `/` in ids;
      - acceptance of the owner's case and of a mixed `at_least`;
      - `composite_setup` tests stay green unchanged.

## 2. Shared fold and single-trade replay

- [ ] 2.1 Extract the `adx_di_threshold` long/short series formula from
      `historical_managed_projection.py` into one function. The atomic
      projection rule uses it, and its output stays byte-identical.
- [ ] 2.2 New `managed_composite.py`: `fold_phase_paths` (design D4).
      It builds:
      - per-child market arrays, from `evaluate_predicate` or the
        extracted series;
      - folded `require` masks, with market-only `at_least` folded in;
      - the trade `require` list;
      - mixed `at_least` terms.
- [ ] 2.3 `managed.py`:
      - composite branch reached from `_phase_met` through a per-call
        fold cache, built once per call per composite rule for the
        trade side;
      - per-bar path check in declared order;
      - `phase_changed` metadata `path_id` and `children` (design D5);
      - optional `bundle` parameter;
      - atomic conditions keep their code path.
- [ ] 2.4 Bundle wiring (design D7):
      - `live_projections/open_trade.py` passes `evaluation.contexts`;
      - `application/evaluate_managed_replay.py` builds the bundle only
        when a composite contains a `state` predicate.
- [ ] 2.5 Tests:
      - the owner's case through `/managed-replay` (HTTP) and live
        open-trade;
      - path attribution;
      - the same-bar cascade across two composite rules;
      - warm-up bars are false;
      - a `state` and a `temporal` child;
      - side override on DI.

## 3. Projection contract and builder

- [ ] 3.1 `strategies/contracts.py`:
      - `ManagedTransitionPath`, `ManagedTransitionThreshold`,
        `ManagedTransitionAtLeast`, `ManagedTransitionTerm`;
      - optional `paths` on `ManagedPhaseTransitionRule`;
      - the docstring states the three-way exclusivity (design D6).
- [ ] 3.2 `historical_managed_projection.py`:
      - a composite rule emits `paths` from `fold_phase_paths`, called
        for both sides;
      - trade children reuse the existing distance/metric code;
      - ids follow design D6;
      - optional `bundle` and memo `context` parameters.
      `evaluator.py` passes `evaluation.contexts` and the memo context.
- [ ] 3.3 `adapters/http/strategy_serialization.py`:
      - serialize `paths`;
      - omit the field when `None`;
      - atomic rule bytes are unchanged, asserted by the group 0 gate.

## 4. Planning and live history

- [ ] 4.1 `feature_plan.py`:
      - predicate children of composite phase conditions join
        `predicate_features`, planned last with the existing collision
        check;
      - atom children use the existing atom branches (design D9).
- [ ] 4.2 `live_calculation_requirements.py`: a composite contributes
      its children, through `_predicate_history` for predicates and the
      existing zero entries for atoms. Anything unknown fails closed.
- [ ] 4.3 Tests:
      - shared ADX column with `composite_setup`;
      - a collision fails closed;
      - temporal history is `bars − 1`;
      - an unknown child fails closed;
      - `plan_hash` is unchanged for atomic managed specs.

## 5. Memo pre-pass

- [ ] 5.1 `evaluation.py`:
      - add the `managed` stage to `MemoizedStageIdentities`, resolved
        after `exit_policy` by one function that the projection also
        uses;
      - add its consumptions (`local` plus `nested` per predicate child
        per side, in projection order) to `memoized_stage_consumptions`
        (design D8).
- [ ] 5.2 The projection evaluates predicate children through their
      identities under the `_memo_identities` gate. Folding and the ADX
      series are not memoized.
- [ ] 5.3 Tests:
      - batch of candidates that differ only in the `mfe_atr` threshold:
        each predicate mask is computed once and
        `unforeseen_consumptions == 0`;
      - a predicate shared with `composite_setup` is computed once;
      - memo on and memo off give identical projections.

## 6. Equivalence and cost

- [ ] 6.1 Extend `tests/test_ema_pullback_historical_managed_projection.py`:
      the reference consumer implements the `paths` rule (design D6).
      Add the composite corpus from design D12. The (bar, `rule_id`,
      `path_id`) transitions must equal `evaluate_managed_replay` for
      every side and entry.
- [ ] 6.2 Fault controls. Both must make the corpus fail:
      - a consumer that ignores the trade terms of a mixed `at_least`;
      - a consumer that ignores `thresholds`.
- [ ] 6.3 `benchmark-report.md`:
      - A/B against `main` on atomic managed specs: identical
        projection bytes and compute counts, CPU within noise;
      - composite overhead per candidate (projection build) and per
        replay call (fold);
      - projection size per path.
- [ ] 6.4 `make verify` green.

## 7. Sync and archive

- [ ] 7.1 Sync the deltas into `openspec/specs/`. Validate with
      `openspec validate --strict`.
- [ ] 7.2 Archive the change after owner approval.
