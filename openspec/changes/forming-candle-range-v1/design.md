## Context

The current operand requires episode, timeframe and an atr_wilder feature of the same timeframe. It computes signed (close-current_bucket_open)/aligned_ATR, gated by valid touch points. See proposal.md for motivation. Reference case 178 is recorded in research_service/research/nvs3_remaining_operands_audit and historical altvals.py.

## Goals / Non-Goals

**Goals:** represent case 178 through a generic scalar range mode, preserve old manifests, and prove parity on BTC/ETH/SOL.

**Non-Goals:** expose an OHLC object, change all HTF alignment, alter legacy body behavior, implement other missing filters, or change research verdicts and weights. Additional raw OHLC fields can be proposed separately.

## Decisions

1. Extend forming_candle with optional field enum body|range. Omitted/body are canonical equivalents. Range returns (running_high-running_low)/previous_bucket_ATR, without side sign. Existing episode validity gating remains. This is smaller and compatible compared with adding a case-178 operand or returning an OHLC object.
2. Use existing timeframe boundaries and existing Wilder ATR computation. Range explicitly selects the previous bucket's ATR; do not shift the whole feature series or use a future base row. For 5m evaluation at 11:55 in the 08:00–12:00 bucket, numerator includes 11:55 and denominator is ATR through the 04:00–08:00 bucket. At 12:00 numerator resets and denominator advances to the 08:00–12:00 bucket.
3. Accumulate high/low causally from bucket start through the evaluation candle. Missing bucket-start history, gaps or invalid highs/lows in that prefix produce missing range, not a partial range. Zero range is valid; missing/nonpositive ATR is missing. Use closed base candles under the existing evaluation contract.
4. Cache identity distinguishes range from body; feature dependency collection reuses ATR. History planning requests ATR warmup plus complete current bucket prefix. Full and sufficiently warmed prefix evaluations must agree within the existing ATR numerical policy. Evidence records field and normalization semantics.

## Risks / Trade-offs

- Accidental inclusion of the final HTF candle's ATR → explicit boundary tests at first, middle, last and next bucket bars.
- Future high/low leakage from a complete resampled candle → mutation tests on future base bars.
- Legacy D1 regression → preserve evaluator semantics and omitted/body canonical identity; run existing D1 tests.
- Truncated live history → require full bucket prefix and report missing rather than understated range.

## Migration Plan

Additive schema extension; existing manifests need no migration. Publish an example manifest using field range and existing atr_wilder period 14/timeframe 4h after implementation. No frozen research artifacts are replaced. Rollback removes new-mode usage; legacy manifests remain usable.
