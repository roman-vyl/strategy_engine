# Proposal: ATR Indicator Vertical Slice v1

## Why

`ema_pullback` depends on ATR for stop/take distances, setup normalization, managed rules, and diagnostics. The independent Indicator Engine currently supports EMA only. ATR must be ported next with exact BBB parity before strategy feature planning can move.

## What changes

- add `atr` to the indicator catalog and schema API;
- validate BBB-compatible ATR plans;
- port BBB true-range and rolling-mean ATR semantics;
- support base and integral higher timeframes with completed-HTF alignment;
- allow EMA and ATR features in one indicator plan and one MDS read;
- add direct golden parity against the copied BBB calculations module;
- preserve Decimal-text API output and warmup metadata.

## Out of scope

- ATR-distance derived features;
- RSI, ADX, DI, strategy FeaturePlan construction;
- incremental/bar-to-bar ATR state;
- BBB cutover.
