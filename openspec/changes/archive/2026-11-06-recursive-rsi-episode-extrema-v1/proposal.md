## Why

The original C6 research formula cannot yet be reproduced faithfully: Engine `rsi` uses simple rolling means, while C6 uses recursive gain/loss averages. Existing `segment` already resolves current and previous waves, but lacks explicit level extrema with the required open-start boundary. C6 should be composed from reusable features and operands, not implemented as a filter-specific component.

## What Changes

- Add generic `rsi_ewm` feature with period-based recursive averages and explicit zero-seed semantics, preserving existing `rsi` behavior and identities.
- Extend existing `segment` with level `min`/`max` and explicit start-boundary / coincident-endpoint policy; reuse previous-wave resolution and the range-extreme utility.
- Make calculation history and seed origin explicit for reproducibility; test prefix invariance and full-prefix reference parity.
- Provide a normal strategy example composing original C6 from features, segments and existing difference/scale operands, and a BTC/ETH/SOL parity harness.
- Exclude experimental wave ratios, voting calibration, SPOT/PERP, ATR changes, and deployment.

## Capabilities

### New Capabilities

- `recursive-rsi-feature-v1`: Recursive RSI feature, validation, identity, history and API semantics.
- `segment-level-extrema-v1`: Generic level extrema and interval-boundary policies on existing episode segments.

### Modified Capabilities

None. Existing `rsi` and legacy segment defaults retain their contracts. New segment combinations and explicit options are additive.

## Impact

Indicator registry/calculation/catalog/schema, feature planning/history/cache identity, ema_pullback segment parser/AST/evaluation/identity, docs/examples/tests. Existing `window_extreme` and current/previous touch resolution are reused. Research reference data remain outside production runtime and manual reviews remain unchanged.
