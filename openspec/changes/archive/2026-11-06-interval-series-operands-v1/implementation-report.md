# Implementation acceptance — interval-series-operands-v1

Implemented locally against Strategy Engine main `337428b`. No deployment,
manifest publication, frontend surface changes, SPOT/PERP work or recalibration.

## Delivered

- Generic `interval_change`: fixed / current impulse / current pullback;
  optional episode truncation; four endpoint operations; entry candle included.
- Generic `scale` with missing-value propagation.
- Opt-in `ratio.denominator_mode=absolute`, preserving signed denominators and
  strict magnitude floor. Default and explicit positive retain legacy identity
  and numeric behavior, including negative-floor semantics.
- Recursive parsing, feature collection, node/memo accounting, diagnostics,
  weighted-vote use, base-window history plus warm-up. Historical `at_point`
  composition includes endpoint displacement behind the episode horizon.
- [Public contract](../../../docs/interval_series_operands_v1.md), three executable
  example specs, independent numerical tests and reproducible real-data audit.

## Automated validation

Final affected suite: **738 passed, 2 skipped**, 8.80 seconds. Two existing
parameterized band tests intentionally skip combinations rejected by validation.
One dependency deprecation warning from FastAPI/Starlette's httpx test client.

- Ruff: all changed Python files pass.
- Mypy: all **118 source files** pass.
- `git diff --check`: clean.
- `openspec validate interval-series-operands-v1 --strict`: valid.
- New tests cover four operations, both sides, fixed versus clipped intervals,
  short/long legs, missing/zero/negative endpoints, finite boundaries, sampled
  grammar, default identities, live warm-up, uncached/batch equivalence, vote
  integration and execution of all three documented example specs.

The bare `pytest` entrypoint initially failed collection of an existing `tests.*`
import; `python -m pytest` supplies the repository import path and passes. A
first prefix assertion used a tighter tolerance than the existing EMA warm-up
policy. The final test derives its bound from `(1-alpha)^warmup`, price bounds
and the measurement formula; the production convergence policy was not changed.

## Frozen research comparison

31 selected EMA/normalized-gap expressions × BTC, ETH, SOL. See
[formula mapping](acceptance/formula_mapping.json) and
[machine-readable results and source hashes](acceptance/parity.json).

| Coin | Entries | Eligible | Value / finite-mask discrepancies | Changed blocks |
|---|---:|---:|---:|---:|
| BTC | 2824 | 2815 | 0 / 0 | 0 |
| ETH | 2542 | 2534 | 0 / 0 | 0 |
| SOL | 2232 | 2226 | 0 / 0 | 0 |

Raw values match exactly (maximum absolute error 0). Maximum individual weight
error is 1.82e-12; maximum summed score error 2.05e-12. The existing Engine uses
`exp(x)-1`; the research uses `expm1(x)`. This floating-point difference changes
no masks. Coefficients, curves, family maxima and threshold were frozen.

**Scope of evidence:** endpoint/operand parity deliberately uses the same
research S/P points and EMA seeds. Frozen curves feed the existing exponent
implementation; the hybrid final score substitutes the matched operands and
retains every other input from research. This proves the new operands preserve
that calculation, not full NVS3 simulation with independently detected Engine
episodes or live data acquisition. Excluded volume inputs remain unimplemented
in this change. Full manifest parity remains a separate integration task.

## Reproduction

```sh
.venv/bin/python tools/interval_series_parity.py --research-root ../research_service
.venv/bin/python -m pytest tests/test_interval_series_operands.py
.venv/bin/mypy
openspec validate interval-series-operands-v1 --strict
```

The parity script accepts `--data-root` for the frozen entry/bundle files and
`--output` for a separate result directory. It never overwrites research inputs.
