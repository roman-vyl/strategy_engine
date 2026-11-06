# Implementation

Implemented optional body/range selector, distinct range node identity, causal prefix extrema, frozen preceding-bucket ATR, missing-prefix handling and recursive history requirements. Legacy omitted/body semantics remain unchanged. Added runnable examples/forming-candle-range.json and docs/forming_candle_range_v1.md.

Acceptance: acceptance/parity.json and three NPZ files reproduce HIST:d3cr_4h on frozen BTC/ETH/SOL entries with zero finite-mask mismatches, zero value mismatches and max absolute difference 0. This isolates operand calculation using existing aligned Engine Wilder ATR and frozen eligibility; it is not a full independently detected NVS3 backtest. Reproduction: .venv/bin/python tools/forming_range_parity.py (local research/data archives required).

Validation: targeted forming candle, D1 pipeline, intervals, live requirements, plan window and weighted-vote suites pass. Mypy passes for 118 source files; strict OpenSpec validation passes. Existing dependency deprecation warning remains. No deployment or research verdict/weight changes.
