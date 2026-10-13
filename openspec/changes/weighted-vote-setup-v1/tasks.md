## 0. Baseline

- [ ] 0.1 Branch from main. The suites for setups, composites, predicates, memo, identity, feature plan and history plan pass
      unchanged before group 1 and after every group. Verify: suite run.

## 1. Parse and validate

- [ ] 1.1 `weighted_vote_setup` in the supported setups; dispatch by `component_id`; rejected as a `composite_setup` child.
      Verify: tests.
- [ ] 1.2 `params`:
  - `threshold` > 0 and finite;
  - `voters` non-empty, unique `voter_id` without `/`;
  - `role` `vote` | `veto`;
  - inputs non-empty, unique `input_id` within the setup.

  Verify: acceptance and rejection tests.
- [ ] 1.3 Inputs:
  - exactly one of `operand` + `direction` or `count.of`;
  - the operand and the predicates are validated by the predicate layer (the same accepted set as `range.operand`; `change` rejected
    as an operand);
  - `direction` rejected with `count`.

  Verify: tests, including the layer's own error for a bad operand.
- [ ] 1.4 Steps:
  - finite `level`;
  - exactly one of `weight ≥ 0` or `veto: true`;
  - unique levels;
  - integer levels in `1..len(of)` for `count`;
  - a `veto` voter has only veto steps;
  - unknown keys rejected.

  Verify: tests.

## 2. Evaluation

- [ ] 2.1 Step crossing for `at_most`, `at_least` and `count`, values exactly on a level, missing and non-finite values.
      Verify: tests against a brute-force loop on synthetic series.
- [ ] 2.2 Input weight = max over crossed steps; input veto = any crossed veto step; voter = max over inputs and any veto; order of
      steps, inputs and voters does not change results. Verify: tests, including permuted tables.
- [ ] 2.3 Score and block: sum of voter weights, `score ≥ threshold` without tolerance, veto alone, no defaults. Verify: tests on
      exact boundaries (0.75 vs 0.7499999).
- [ ] 2.4 Long and short with one table: each side reads its own operand values. Verify: test on mirrored synthetic data.
- [ ] 2.5 No lookahead: truncating or altering bars after `t` leaves every series on `≤ t` unchanged. Verify: truncation test.
- [ ] 2.6 Composition: AND with other setups; `context_consumption` applied after the local mask as for any setup. Verify: tests.

## 3. Evidence

- [ ] 3.1 Trace `input:<id>:value`, `voter:<id>:weight`, `voter:<id>:veto`, `score`, `blocked_by` (first vetoing voter in declared
      order, else `score`, else null). Verify: trace test.

## 4. Identity, sharing, cost

- [ ] 4.1 Input operands and predicates are predicate-layer nodes with existing identities; shared with composite children and
      between candidates; zero `unforeseen_consumptions`. Verify: batch tests (memo on = memo off).
- [ ] 4.2 Candidates that differ only in levels, weights, veto flags or threshold compute each operand once per side. Verify: compute
      count test.
- [ ] 4.3 Specs without a weighted vote: identical node set, identities, masks, evidence and compute counts. Verify: existing suites and
      parity corpus.

## 5. Plans

- [ ] 5.1 Feature plan: features inside vote inputs planned as composite children; unchanged plan without a vote. Verify: tests.
- [ ] 5.2 History plan: max over the inputs' requirements; fail closed on an unknown input; unchanged without a vote. Verify: planner
      tests.

## 6. Reference check against an external table (owner's Mac, after the owner's word)

- [ ] 6.1 Research supplies a reference spec with a weighted vote over existing operands, together with:
  - the expected per-entry `score`, vetoes and block flags;
  - expected cell results.

  The Engine reproduces the flags exactly and the cells to the cent. Mismatches are reported, not fixed in the table.
- [ ] 6.2 Report: parity table, wire format of `weighted_vote_setup`; stop for the owner's review.

## 7. Gate

- [ ] 7.1 ruff, mypy, affected tests without the `tests/parity` memo.
- [ ] 7.2 `openspec validate weighted-vote-setup-v1 --strict`.
