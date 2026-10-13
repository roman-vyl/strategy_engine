## 0. Baseline

- [ ] 0.1 Branch from main 652c084. Existing setup, composite and predicate suites pass unchanged after every group (no memo test). Verify: suite run.

## 1. Parse and validate

- [ ] 1.1 `composite_vote` setup component registered; `params` shape per spec (`members`, `block_at`); unknown keys rejected. Verify: tests.
- [ ] 1.2 Operand input accepts every operand kind of the predicate layer through the existing operand parser (no per-kind code). Verify: parametrised test over all operand kinds.
- [ ] 1.3 Group input accepts predicates through the existing predicate parser; `at_least` range checked. Verify: tests.
- [ ] 1.4 Rejections: duplicate member ids, empty inputs/levels, both or neither of weight/veto, negative or non-finite weight, repeated `at`, non-positive `block_at`, `composite_vote` as a composite child or nested. Verify: tests.

## 2. Evaluation

- [ ] 2.1 Operand input: inclusive fire per side, deepest fired level taken, order of levels irrelevant, missing value silent, non-monotone weights take the deepest level. Verify: tests against a brute-force loop on synthetic arrays.
- [ ] 2.2 Group input: fires at `at_least`, predicate masks reused unchanged. Verify: tests.
- [ ] 2.3 Member max over inputs, veto any; vote sum; block on veto or `sum ≥ block_at`; `block_at` null = vetoes only; member and input order irrelevant. Verify: tests.
- [ ] 2.4 Setup composition: local mask = not blocked, AND with other setups, `context_consumption` applied as for any setup. Verify: tests.
- [ ] 2.5 No lookahead: changing later bars leaves earlier masks and traces unchanged. Verify: truncation test.

## 3. Trace, identity, cost

- [ ] 3.1 Trace keys per spec, including `vote:reason` ordering. Verify: trace test.
- [ ] 3.2 Operand and predicate nodes shared with other setups and across candidates that differ only in vote numbers; `unforeseen_consumptions` stays 0. Verify: batch tests with node-call counts.
- [ ] 3.3 A spec without `composite_vote` has an identical node set and results. Verify: existing suites.

## 4. Parity with the research replay (owner's Mac, on the owner's word)

- [ ] 4.1 A check config supplied by research (members, levels, weights, veto marks, `block_at`) for one strategy, with a per-entry reference (member weights, vetoes, sum, blocked). Values and decisions equal on every entry, long and short separately.
- [ ] 4.2 Engine runs of the check config on the cells named by research, trades, win rate and net to the cent.
- [ ] 4.3 Report: parity table and wire format; stop for review.

## 5. Gate

- [ ] 5.1 ruff, mypy, affected tests without the `tests/parity` memo test.
- [ ] 5.2 `openspec validate composite-vote-v1 --strict`.
