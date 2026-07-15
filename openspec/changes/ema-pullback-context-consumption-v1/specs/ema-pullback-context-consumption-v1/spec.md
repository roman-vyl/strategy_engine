# EMA Pullback Context Consumption v1 Specification

## Requirement: Side-relative regime

For long, raw `up` SHALL resolve to `aligned` and raw `down` to `countertrend`. For short, the mapping SHALL be reversed. Unknown or neutral state SHALL resolve to `neutral`.

## Requirement: HTF regime gate

A configured `htf_regime_gate` SHALL require a non-empty `allowed_regimes` list containing only `aligned`, `countertrend`, or `neutral`. The engine SHALL return the resolved regime and allow mask for every evaluated side.

## Requirement: Exit profiles

`exit_profile_by_htf_state` SHALL return long and short profile series. Disabled sides SHALL receive `neutral` for every bar.

## Requirement: Scope

This change SHALL NOT apply local blocker/setup logic or claim that trading decisions are ready.
