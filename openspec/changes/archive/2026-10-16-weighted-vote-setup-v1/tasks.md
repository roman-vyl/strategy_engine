## 0. Baseline

- [x] 0.1 Branch from main. The suites for setups, composites, predicates, memo, identity, feature plan and history plan pass (the memo and tests/parity suites were not run: the owner forbids them, 2026-10-14)
      unchanged before group 1 and after every group. Verify: suite run.

## 1. Parse and validate

- [x] 1.1 `weighted_vote_setup` in the supported setups; dispatch by `component_id`; rejected as a `composite_setup` child.
      Verify: tests.
- [x] 1.2 `params`:
  - `threshold` > 0 and finite;
  - `voters` non-empty, unique `voter_id` without `/`;
  - `role` `vote` | `veto`;
  - inputs non-empty, unique `input_id` within the setup.

  Verify: acceptance and rejection tests.
- [x] 1.3 Inputs:
  - exactly one of `operand` + `direction` or `count.of`;
  - the operand and the predicates are validated by the predicate layer (the same accepted set as `range.operand`; `change` rejected
    as an operand);
  - `direction` rejected with `count`.

  Verify: tests, including the layer's own error for a bad operand.
- [x] 1.4 Steps:
  - finite `level`;
  - exactly one of `weight ≥ 0` or `veto: true`;
  - unique levels;
  - integer levels in `1..len(of)` for `count`;
  - a `veto` voter has only veto steps;
  - booleans rejected in `threshold`, `level` and `weight`; `veto` only as literal `true`;
  - weights and threshold with more than 9 decimal digits rejected;
  - unknown keys rejected.

  Verify: tests.

## 2. Evaluation

- [x] 2.1 Step crossing for `at_most`, `at_least` and `count`, values exactly on a level, missing and non-finite values.
      Verify: tests against a brute-force loop on synthetic series.
- [x] 2.2 Input weight = max over crossed steps; input veto = any crossed veto step; voter = max over inputs and any veto; order of
      steps, inputs and voters does not change results. Verify: tests, including permuted tables.
- [x] 2.3 Score and block in exact decimal arithmetic (integers in 10⁻⁹ units): sum of voter weights, `score ≥ threshold` exact,
      veto alone, no defaults. Verify: 0.3 + 0.25 + 0.2 vs 0.75 in every voter order; 0.1 + 0.7 vs 0.8 (blocked; binary float gives 0.7999999999999999); 0.749999999 vs 0.75.
- [x] 2.3a `count` with partly missing operands: a missing operand makes a default range False and an `empty: pass` range True; the
      count counts True only. Verify: test.
- [x] 2.4 Long and short with one table: each side reads its own operand values. Verify: test on mirrored synthetic data.
- [x] 2.5 No lookahead: truncating or altering bars after `t` leaves every series on `≤ t` unchanged. Verify: truncation test.
- [x] 2.6 Composition: AND with other setups; `context_consumption` applied after the local mask as for any setup. Verify: tests.

## 3. Evidence

- [x] 3.1 Trace:
  - `input:<id>:value`, `input:<id>:weight`, `input:<id>:veto`;
  - `voter:<id>:weight`, `voter:<id>:veto`;
  - `score` as the nearest float of the exact sum;
  - `blocked_by`: the first vetoing voter in declared order, else `score`, else null.

  Verify: a trace test, and a test that permuting the voters changes only `blocked_by`.

## 4. Identity, sharing, cost

- [x] 4.1 Vote node identity: (memo on = memo off not run: the owner forbids the memo suites, 2026-10-14)
  - kind `setup.weighted_vote` and version;
  - normalized config (exact decimal strings, ids, declared order);
  - upstream operand and predicate identities;
  - side;
  - market/range.

  Input operands and predicates keep their predicate-layer identities and are shared with composite children and between
  candidates; zero `unforeseen_consumptions`. Verify: identity tests (a changed `voter_id` changes only the vote node) and batch
  tests (memo on = memo off).
- [x] 4.2 Candidates that differ only in levels, weights, veto flags or threshold compute each operand once per side. Verify: compute
      count test.
- [x] 4.3 (parity corpus not run: owner's ban 2026-10-14; existing suites pass) Specs without a weighted vote: identical node set, identities, masks, evidence and compute counts. Verify: existing suites and
      parity corpus.

## 5. Plans

- [x] 5.1 Feature plan: features inside vote inputs planned as composite children; unchanged plan without a vote. Verify: tests.
- [x] 5.2 History plan: max over the inputs' requirements; fail closed on an unknown input; unchanged without a vote. Verify: planner
      tests.

## 5a. End-to-end parity across call paths

- [x] 5a.1 One spec with a weighted vote evaluated through: (memo on against memo off not run: the owner forbids the memo suites, 2026-10-14)
  - `/range` against `/range-batch`;
  - memo on against memo off;
  - live entry against the historical decision on the same bar.

  Masks, decisions and the serialized evidence (content and order) are identical; bounded history is sufficient for the live
  decision. Verify: integration tests.
- [x] 5a.2 The existing regression corpus of specs without a weighted vote: results, identities and evidence unchanged. Verify: (the memo and tests/parity suites were not run: the owner forbids them, 2026-10-14)
      parity corpus run.

## 6. Reference check against an external table (owner's Mac, after the owner's word)

- [x] 6.1 Research supplies a reference spec with a weighted vote over existing operands, together with:
  - the expected per-entry `score`, vetoes and block flags;
  - expected cell results.

  The Engine reproduces the flags exactly and the cells to the cent. Mismatches are reported, not fixed in the table.
- [x] 6.2 Report: parity table, wire format of `weighted_vote_setup`; stop for the owner's review.

## 7. Gate

- [x] 7.1 ruff, mypy, affected tests without the `tests/parity` memo.
- [x] 7.2 `openspec validate weighted-vote-setup-v1 --strict`.
