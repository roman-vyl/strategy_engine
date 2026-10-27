## 0. Baseline

- [ ] 0.1 Code starts after the owner's «apply», from `main` once PR #49 is merged (or rebased on `claude/project-thread-teko29`) and
      after `ema-slope-window-change-v1` is coded. Targeted suites for vote, setups, predicates, identity pass before and after every
      group. Never run `tests/parity/test_all_families_memo.py`. `PYTHONPATH=src:.:tests`.

## 1. Parse and validate

- [ ] 1.1 Input forms: `operand`+`direction`+`steps` | `operand`+`curve` | `count`+`steps`; `curve` only in `vote` voters. Verify: tests.
- [ ] 1.2 `curve` validation: lengths, finiteness, strictly increasing grid, `k`/`e_v` > 0, overflow bound, no booleans, unknown keys.
      Verify: acceptance and rejection tests.
- [ ] 1.3 `short.operand` validated by the predicate layer; rejected on `count`. Verify: tests.
- [ ] 1.4 `when`: non-empty list of layer predicates with their `short` overrides. Verify: tests.

## 2. Evaluate

- [ ] 2.1 Curve weight exactly as research (clip nodes, `np.interp`, `(exp(k·e) − 1)/(exp(k·e_v) − 1)`); missing → 0. Verify: unit tests
      from the scenarios, and bit equality with the research lambda on random inputs.
- [ ] 2.2 Short operand per side; gate closes weight and veto. Verify: tests.
- [ ] 2.3 Exact rational score when any curve input exists; integer path unchanged otherwise; order independence. Verify: tests with
      permuted voters.

## 3. Evidence and identity

- [ ] 3.1 Trace `input:<id>:excess`, `input:<id>:when`. Verify: tests.
- [ ] 3.2 Identity includes the new keys; vote B config identities unchanged. Verify: identity tests.
- [ ] 3.3 Feature plan / live requirements include `short` and `when` operands. Verify: tests.

## 4. Variant 8 config

- [ ] 4.1 Build the variant 8 vote config for BTC/ETH/SOL (design table; curves from the research JSON; nine vote-B vetoes; θ 1.75).
      vol1h kept as a slot until the owner decides the volume source.

## 5. Parity (on the owner's command)

- [ ] 5.1 Engine in-process on full history, all entries of BTC/ETH/SOL: blocked mask equals `review/surf/w8vote/maskwin8_<c>.npz`
      (BTC 1045, ETH 866, SOL 898); per-voter weights equal research within 1e-12. Without vol1h: compare with research's mask rebuilt
      without vol1h. Report entries with score in [θ − 1e-9, θ) (design D4).
