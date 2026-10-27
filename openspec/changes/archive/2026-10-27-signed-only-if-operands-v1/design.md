## Context

- Research Wk: `review/d1sweep/week.py`; D1v: `review/d1sweep/combo3.py` (`body = G·(close − open)/ATR`, `pos` = `(close − low)/range` on a
  long, `(high − close)/range` on a short) and `d1v_feat.py` (`where(body ≥ 1 & pos ≥ 0.85, D1, 9)`; 9 weighs 0, the same as missing).
- Engine parity of the raw parts (yesterday body, yesterday close position, previous-week body, D1v composed by hand):
  `/mnt/project-files/engine-tasks/ema200/parity_cc/`, exact on all entries.

## Decisions

### D1. Operand `signed`

`{"signed": {"operand", "center"}}`, both required, no other field. `center` is a finite number. The inner operand is any operand of the
layer except a constant. Value `center + g · (x − center)`; on the long side this is `x` itself, so long values are bit-identical to the
inner operand. Missing where the inner value is missing.

The short close position `(high − close)/range` equals `1 − (close − low)/range` exactly in real arithmetic; in float64 the two may differ in
the last bit. Parity reports any entry whose gate flips for this reason (expected 0).

### D2. Operand `only_if`

`{"only_if": {"operand", "require"}}`, both required. `require` is a non-empty list of `{"operand", "min", "max", "bounds"?}`, the
fields with the meaning, defaults and validation of a `range` (`empty` is not accepted). A requirement holds on a bar when its operand
value is finite and inside the bounds. The value is the inner value where every requirement holds, missing otherwise. The inner operand
and the requirement operands are operands of the layer, not constants.

Rejected: a gate in the vote (the owner's rule), or a special D1v operand (the gate is generic).

### D3. Placement and identity

Both are accepted wherever a ratio is accepted, and rejected as the operand of a `change`. Own node families `predicate.signed` and
`predicate.only_if`. Their upstream is the inner operand, plus the requirement operands for `only_if`, and their side is always set.

### D4. Parity reference

Wk: `review/d1sweep/wk_<c>.npz`. D1v: `review/d1sweep/d1v_<c>.npz`, where 9 counts as missing. Both cover all EMA200 entries of BTC, ETH
and SOL. Tolerance 1e-9 relative, NaN equal. The Engine is evaluated at the same index as the earlier parities.
