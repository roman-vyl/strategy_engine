## 0. Baseline

- [ ] 0.1 Code after the owner's «apply», on `main` after PR #49 is merged (or rebased on `claude/project-thread-teko29`, which has the
      W8 operands and `window_change`). Targeted suites (vote, setups, predicates, identity, feature plan) pass before and after every
      group. Never run `tests/parity/test_all_families_memo.py`. `PYTHONPATH=src:.:tests`.

## 1. Parse and validate

- [ ] 1.1 `between` `step`|`linear`: linear needs ≥ 2 weight steps, no veto, no `direction`. Verify: tests.
- [ ] 1.2 `weighting.exponent {k, e_v}`: > 0, finite, no booleans, overflow guard, only in `vote` voters, no veto step. Verify: tests.
- [ ] 1.3 `short.operand` validated by the predicate layer; rejected on `count`. Verify: tests.
- [ ] 1.4 `when`: non-empty list of layer predicates with their `short` overrides. Verify: tests.

## 2. Evaluate

- [ ] 2.1 Linear ladder as `numpy.interp` with end values; missing → 0. Verify: scenario tests.
- [ ] 2.2 Exponent `(exp(k·x) − 1)/(exp(k·e_v) − 1)`; bit equality with the research lambda on random values. Verify: tests.
- [ ] 2.3 Short operand per side; closed gate → weight 0, no veto. Verify: tests.
- [ ] 2.4 Exact rational score with exponent inputs; integer path unchanged otherwise; permuted voters give identical masks.

## 3. Evidence and identity

- [ ] 3.1 Trace `input:<id>:level_value`, `input:<id>:when`. Verify: tests.
- [ ] 3.2 Identity includes the new keys; vote B identities unchanged. Feature plan / live requirements include `short` and `when`
      operands. Verify: tests.

## 4. Variant 8 config

- [ ] 4.1 Vote config for BTC/ETH/SOL from the design table: black-curve corner points (negative clipped to 0), k, e_v, θ 1.75, nine
      vote-B vetoes. vol1h = slot until the owner decides the volume source.

## 5. Parity (on the owner's command)

- [ ] 5.1 Engine in-process on full history, all entries BTC/ETH/SOL: blocked mask equals `review/surf/w8vote/maskwin8_<c>.npz`
      (1045 / 866 / 898); per-voter weights equal research within 1e-12; without vol1h compare with research's mask rebuilt without
      vol1h. Report entries with score in [θ − 1e-9, θ).
