# EMA Pullback semantic parity gate

## Purpose

This gate consolidates every copied-BBB golden parity test into one mandatory acceptance run before BBB is allowed to consume Strategy Engine over HTTP.

It proves parity for the strategy-owned side of the seam:

```text
Strategy spec
→ FeaturePlan
→ indicators
→ contexts and consumption
→ direction / blockers
→ setups
→ triggers
→ final entries
→ standard exit policy
→ managed policy decisions
```

The gate also runs public FastAPI contract tests for range evaluation and managed replay.

## Command

```bash
python scripts/run_semantic_parity_gate.py
```

The command:

1. verifies the immutable BBB copy against `legacy_source/bbb/copy_manifest.json`;
2. verifies every required parity test exists;
3. runs all required tests in one process;
4. writes `artifacts/ema_pullback_semantic_parity_report.json`;
5. exits non-zero on any mismatch.

## Boundary of the claim

A green semantic gate does **not** claim parity for execution-owned responsibilities:

- vectorbt or managed fill arbitration;
- same-bar stop/take priority;
- fees and slippage;
- trade records and PnL;
- BBB report/Workbench translation;
- future live checkpoint/replay.

Those require later integration and execution-parity work in the new Research Service.

## Consumer acceptance rule

A new consumer service SHALL NOT treat Strategy Engine semantics as accepted unless this gate is green against the immutable reference slice. Research Service integration SHALL add frozen execution fixtures that pass Strategy Engine results into the new research-owned simulator and compare resulting trades and reports.
