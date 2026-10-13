# Review of the V2.2 OpenSpec change (research side, 2026-10-13)

- **Reviewer:** the research thread (Mac). The owner put it in charge of reviewing the V2.2 and C5 Engine tasks.
- **Reviewed:** commits c3e7a8d and b73c853 on `claude/v2-force-ratio-o4hb54` — the proposal, the design, the spec deltas and the tasks.
- **Reference:** `research/analysis/BTCUSDT.P/book_metrics_v6/v2/v2_engine_ref.py`, `v2_engine_task.md` and `v2_parity_{btc,eth}.json`.

## Verdict

**Approved.** The definition matches the research reference. Implementation may start.

Confirmed against `v2_engine_ref.py`:
- **D2 / D5:**
  - `F[u] = (close[u] − close[u−1]) × volume[u]`;
  - bar 0 of the data window has force 0;
  - the first impulse bar reads `close[S*−1]`.
- **D4:** both means are taken over all bars of the leg on the side-signed force:
  - `mean_imp = g·ΣF[S*..P] / n_imp`;
  - `mean_pb = −g·ΣF[P+1..t] / n_pb`.
- **D3:**
  - `imp ≤ 0` makes the value missing, and the entry passes;
  - a negative `pb` stays a value;
  - both bounds are inclusive;
  - a missing value passes.
- **Legs:** impulse `[S*, P]`, pullback `[P+1, t]`; `t = P` makes the value missing.
- **D1:** extending `leg_mean.field` instead of adding a new operand is the right reuse.

## Comments (no blocker)

1. **Missing bars (D2).** Research forward-fills the close and turns a missing volume into 0, so a gap bar has force 0 and the leg is not missing. The Engine makes the leg missing.
   - The BTC and ETH parity windows have no missing 5m candles, so parity is not affected.
   - Keep the Engine rule, and state it in the parity report as a known convention difference.
2. **4.3 Engine runs.** Run every cell in `v2_parity_{btc,eth}.json`, not only "none" and "≥ 10":
   - BTC: ≤ 0.007, ≤ 0.027, ≥ 5, ≥ 8, ≥ 10, ≥ 16;
   - ETH: ≤ 0.007, ≤ 0.027, ≥ 8, ≥ 10, ≥ 16;
   - plus one run with both bounds null, which must equal "none".
3. **Parity window.** ETH candles keep being appended to `market.sqlite3`. Run each coin on `window_from_ms .. window_to_ms` from its parity json, or the ETH numbers will drift.
4. **D7 trace.** `sum = mean × count` is fine for the trace.
   - In 4.1, compare `force_sum_imp_signed` and `force_sum_pb_signed` to 1e-9 relative.
   - If the rounding of mean × count exceeds that, report the maximum difference instead of changing the code.
5. **Optional.** Add a spec scenario for `t = P`: an empty pullback, so the value is missing and the entry passes. It mirrors task 2.2.

## Next review points

- **Implementation PR:** tests for tasks 2.1–2.5 and the identity checks of 3.1–3.2.
- **Parity report 4.1–4.5:**
  - values against the reference files;
  - block counts;
  - cells to the cent, on the json windows.
