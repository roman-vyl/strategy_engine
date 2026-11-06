# Recursive RSI and level extrema

`rsi_ewm` is a generic feature (`source:close`, `params:{period:168}`). It uses
zero-seeded gain/loss averages with alpha=1/period. The existing `rsi` remains
a rolling-mean RSI. Both zero averages mean missing; no epsilon or flat RSI50
is inserted. An invalid candle invalidates subsequent recursive values for
that input prefix. HTF buckets remain completed-only; C6 uses base candles.

The existing `segment` now accepts level min/max, `include_start:false`, and
`empty_policy:"end"` for a coincident current peak/entry. Endpoints are causal,
end-inclusive; start exclusion precedes last_n. Missing interior values are
not skipped. Previous peak→next_origin requires strict ordering and a previous
wave in the same episode. Nondefault policies have distinct cache identities.

`examples/c6-original.json` is an executable observation spec, NOT a calibrated
filter or a deployed strategy. It subtracts previous from current segment min
using the existing side-signed series behavior. Long is current RSI min minus
previous min. Short is min(-current RSI)-min(-previous RSI), hence previous
RSI max minus current max. No new side switch or C6 runtime dispatch is needed.
The explicit alternative uses `of.by_side` with the same RSI feature for both
sides to suppress implicit mirroring, and separate min/max formulas. Both
compositions are checked by the real-data parity harness.

For original C6, intervals are `(previous P,current S]` and `(P,entry]`;
entry=P uses the current candle alone. There is no previous-wave value on the
first touch. Recursive history starts at the supplied input prefix, before
report slicing. Execution market time axis and input market-data hash identify
that prefix; acceptance records its first open timestamp and source hashes.
Finite live history uses a gain/loss seed-decay budget of 1e-12 plus the previous
close, composed with the episode history requirements. This is NOT a bound on
RSI output error near a zero denominator and NOT a claim of exact full-history
seed equivalence. Exact comparisons require the same prefix or equivalent state.

Run `.venv/bin/python tools/c6_parity.py --research-root ../research_service`.
Reference paths can be changed with `--data-root` and `--output`. The tool uses
frozen episode points to isolate formula parity; ordinary pipeline and synthetic
episode tests cover integration separately. It is not a full strategy replay.
Research inputs are acceptance-only, never production dependencies.
