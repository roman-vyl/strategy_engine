# Interval series operands v1

These are generic `ema_pullback` operand expressions. Use them in a `range`,
`compare`, weighted-vote input, or an existing arithmetic wrapper. They do not
contain NVS3 filter IDs, voting thresholds or fitted coefficients. SPOT/PERP
acquisition and expressions are outside this change.

## Wire contract

```json
{"interval_change": {
  "of": {"feature": {"kind": "ema", "params": {"period": 50}}},
  "interval": {"kind": "fixed", "bars": 24},
  "operation": "relative_change_per_bar"
}}
```

`of` samples base-timeframe `feature`, `price`, `const`, `difference`, `ratio`,
`abs`, `scale` recursively. At least one nonconstant series is required.
Feature names and parameters use the existing feature registry. Stateful or
nested interval expressions, `at_point`, `signed`, and episode operands are
not sampled-series leaves. Put `signed` **outside** the measurement.
Inside this bounded grammar `abs` can wrap arithmetic including ratios; the
legacy outer `abs` parser restrictions are unchanged.

| Interval | Start a | End b |
|---|---|---|
| `{"kind":"fixed","bars":N}` | t−N | t |
| `{"kind":"episode","ref":"trend","leg":"impulse"}` | current S | current P |
| `{"kind":"episode","ref":"trend","leg":"pullback"}` | current P | t |

Episode intervals allow optional `last_n:N`, replacing a with max(a,b−N).
Fixed intervals never clamp to P and require no episode. N counts differences,
so N+1 endpoint-inclusive samples span the interval. The evaluated entry candle
is included. Episode points come from the current touch as known at t, on the
requested side. Missing/out-of-history/future or degenerate endpoints produce
NaN. Missing interior samples do not affect finite endpoints.

For u=x[a], v=x[b], n=b−a:

| operation | output |
|---|---|
| `change` | v−u |
| `change_per_bar` | (v−u)/n |
| `relative_change` | (v−u)/u |
| `relative_change_per_bar` | (v−u)/u/n |

Relative operations require u≠0; negative u is valid. Results must be finite.
There is no implicit side sign or basis-point multiplier.

`{"scale":{"operand":expression,"factor":10000}}` supplies explicit units.
Factor is finite, including zero and negative values, but not a boolean. A
constant-only operand is rejected. Missing input stays missing even at factor 0.

`ratio` accepts `denominator_mode:"absolute"`: abs(right)>right_floor, with a
nonnegative finite floor. Division retains the denominator sign. Invalid or
nonfinite results are missing. Omitting the mode or specifying `positive`
retains the original right>floor behavior and **the same legacy node identity**,
including historically permitted negative floors. No change to `window_change`.

## Examples and execution

The three complete specs in `examples/interval-series/` demonstrate fixed EMA
slope, normalized EMA-gap velocity, and pullback/impulse slope ratio. Their
range bounds are intentionally open; they demonstrate operand evaluation, not
approved trading filters. They are normal strategy specs for the existing
Engine API, with all scales and ratio floors in configuration. The corresponding
ASTs and 31 actual NVS3 formula mappings are saved in the change acceptance folder.

A normalized-gap velocity measures change in `(EMAfast−EMAslow)/EMAslow`.
It is not the difference between two relative EMA slopes. The gap is normalized
at each endpoint before taking its difference.

## History, identity and limitations

Feature requests are collected recursively. The history planner adds fixed
endpoint displacement to indicator warm-up. Episode measurements retain the
**full declared episode history horizon**, even when `last_n` is small: P can
be historical. A fixed measurement evaluated with `at_point` requires the
episode horizon plus that displacement. Temporal predicates add their window.
The existing empirical episode horizon and EMA seed-convergence policy are
unchanged; this is not a guarantee for arbitrarily old episodes or exact
finite-prefix recursive-indicator equality. Missing endpoints fail closed.

Node identities include operation, interval, underlying expression, scale and
absolute-denominator mode. Episode nodes are side-specific; fixed measurements
without side-dependent wrappers share nodes. The evaluator gathers endpoints
in O(history) regardless of leg length. Existing range/child/vote value traces
expose the new values without a new response envelope.

## Reproduce checks

```sh
.venv/bin/python -m pytest tests/test_interval_series_operands.py
.venv/bin/python tools/interval_series_parity.py --research-root ../research_service
openspec validate interval-series-operands-v1 --strict
```

The real-data check deliberately injects the frozen research entry bars, S/P
points and EMA seed convention to isolate operand semantics. It compares 31
expressions on BTC/ETH/SOL with saved corrected arrays, then substitutes them
into frozen calibration and votes. Other inputs remain frozen research values,
including excluded volume inputs. This is **hybrid substitution parity**, not
full-system NVS3 Engine backtesting or an executable live NVS3 manifest.
