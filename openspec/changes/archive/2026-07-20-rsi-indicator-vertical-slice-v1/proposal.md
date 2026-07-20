# Proposal: RSI Indicator Vertical Slice v1

## Why

`ema_pullback` uses RSI in entry blockers, signal exits, managed runtime exits, diagnostics, and Workbench traces. EMA and ATR are already independent capabilities. RSI is the next dependency and must preserve BBB behavior exactly before strategy feature planning is moved.

## What changes

- register `rsi` in the indicator catalog and schema API;
- validate BBB-compatible RSI plans;
- port BBB simple rolling gain/loss mean semantics;
- support base and integral higher timeframes with completed-HTF alignment;
- allow EMA, ATR, and RSI in one plan and one MDS read;
- add direct golden parity against the copied BBB calculation module;
- preserve Decimal-text output and explicit warmup validity.

## Out of scope

- Wilder RSI/RMA;
- ADX/DMI;
- strategy FeaturePlan construction;
- RSI blockers/exits themselves;
- incremental/bar-to-bar RSI state;
- BBB cutover.
