## Context

See proposal.md. Baseline is main 337428b. Existing window_change reads max(P,t-N)..t, signs by side and supports a canonical base feature only. Existing ratio permits right > right_floor; research safe division instead tests abs(right) > epsilon. NVS3 is a consumer and a parity fixture, not an Engine capability or a source of hardcoded constants.

## Goals / Non-Goals

Goals: express causal endpoint measurements with reusable interval and arithmetic contracts; preserve old behavior and identity; support batch and live planning with the same semantics.

Non-goals: SPOT/PERP data integration, arbitrary scripting, previous-touch intervals, higher-timeframe interval inputs, interpolation or filling of missing prices, recalibration, automatic manifest publication, running or deploying a trading system.

## Decisions

### D1. New operand instead of changing window_change

`interval_change` has exactly `of`, `interval`, `operation`. `operation` is change, change_per_bar, relative_change or relative_change_per_bar. It does not implicitly sign the result. Existing signed with center 0 supplies trade direction explicitly. Existing window_change remains untouched; migrating old specs is not required.

A separate operand avoids silently changing the interval and sign of saved strategies. An internal shared endpoint evaluator is allowed only if old numeric results and identities remain unchanged.

### D2. Two interval shapes, resolved from existing facts

Fixed: `{"kind":"fixed","bars":12}` resolves a=t-12,b=t, with no episode dependency.
Episode: `{"kind":"episode","ref":"trend","leg":"impulse"}` resolves S..P; leg pullback resolves P..t. Optional last_n truncates to max(start,b-N)..b. Both refer to the current valid touch of the evaluated side. No endpoint after t, no previous touch fallback, no new wave detection. N bars means N differences and N+1 endpoint-inclusive samples, not N samples.

S and P are the values known at evaluation time t, not hindsight final wave extrema. An episode interval with an endpoint outside the acquired frame is missing. Fixed-window values may exist without an episode; if a strategy needs research eligibility it expresses that with existing only_if / episode conditions.

### D3. Bounded causal series grammar

`of` accepts feature (base timeframe only), price, const, difference, ratio, abs and scale recursively, with at least one nonconstant leaf. It rejects segment, at_point, interval_change, signed, only_if and other episode-dependent operands inside the sampled series. This prevents ambiguous historical evaluation of a touch-dependent operand at a former endpoint. Sign and eligibility wrap the final measurement instead.

Reuse the operand AST and feature-kind contract, add a structural series validator rather than a second indicator registry. Arithmetic computes a per-base-bar series first; measurement then gathers its endpoint values. No arbitrary Python or filter-specific feature kinds.

`scale: {operand, factor}` is a generic outer or series arithmetic operand with a finite factor and nonconstant operand. Scale preserves missing values, including factor zero. This makes fractions, percentages and basis points explicit rather than choosing trading-specific units in the measurement.

### D4. Operation semantics

For finite u=x[a],v=x[b],n=b-a>0: change=v-u; change_per_bar=(v-u)/n; relative_change=(v-u)/u; relative_change_per_bar=((v-u)/u)/n. Relative operations permit either sign of u but require u != 0. Nonfinite output is missing. Only endpoints matter: an interior missing series value does not invalidate two finite endpoints. No clipping or zero filling.

### D5. Signed denominator mode

Extend ratio with denominator_mode positive (default) or absolute. Positive retains the exact existing right > right_floor behavior, including legacy accepted floors. Absolute requires a finite nonnegative floor and abs(right)>floor, preserving denominator sign. Explicit positive canonicalizes to the old default identity. Do not relax all ratios globally; positive price/volume ratios keep their meaning.

### D6. Planning, identities and cache

Traverse the entire new operand tree in static validation, feature planning, predicate dependency collection, setup pre-consumption accounting and live requirements. Fixed windows require the input series history at t-N, not merely the maximum of warm-up and N: extend the leaf history by N base intervals. Episode measurements require the existing episode history horizon plus sufficient leaf warm-up at its earliest recoverable endpoint. A truncated window on an impulse still needs the historical P, not just the latest N bars.

Use canonical immutable interval keys and one shared expression node per expression identity and market frame. Measurement identity includes interval, operation, input and side when episode resolution depends on side. Scale includes factor; absolute ratio includes its mode. Do not append default fields to old identity tuples. Do not merge whole strategy hashes merely because two explicit specs are semantically equivalent.

Work per expression is O(history length), independent of interval length, plus endpoint gathers; no per-entry loops over variable-length legs. Histories beyond the existing recoverable episode horizon remain missing, never replaced with the first available sample.

### D7. Examples (illustrative spec values, never defaults)

Hourly EMA100 slope in bp/bar, signed for the trade:

```json
{"signed":{"center":0,"operand":{"scale":{"factor":10000,"operand":{"interval_change":{"of":{"feature":{"kind":"ema","params":{"period":100}}},"interval":{"kind":"fixed","bars":12},"operation":"relative_change_per_bar"}}}}}}
```

For a normalized gap, build D=scale(ratio(difference(EMA100,EMA200),EMA200),10000), then signed(interval_change(D, fixed 24, change_per_bar)). This is not slope(EMA100)-slope(EMA200).

For impulse acceleration build signed(scale(interval_change(EMA, impulse last_n 48, relative_change_per_bar),10000)) divided by the corresponding full impulse measurement, with absolute denominator mode and an explicitly configured floor. No filter IDs participate.

## Risks / Trade-offs

- Different endpoint or sign conventions → hand-derived tests on both sides and reference arrays including the entry candle.
- Insufficient live warm-up → prefix versus batch parity after declared history requirements, including historical impulse endpoints.
- Division near zero → strict boundary and finite-mask tests; no inferred epsilon.
- Existing features can have seed differences → report maximum error, finite-mask differences and threshold crossings separately; tolerance cannot hide changed blocking decisions.
- Expanded grammar can defeat memo accounting → batch shared-node tests and old identity regression tests.

## Migration Plan

Implement and validate additive primitives in stages: scale/ratio mode; interval resolution; series measurement; planning and caching integration; real-data parity. Old strategies require no migration. Build demonstration specs without replacing NVS3 surfaces. Release/deployment and full manifest integration are separate work. Rollback new specs by removing the opt-in components; old specs remain executable throughout.
