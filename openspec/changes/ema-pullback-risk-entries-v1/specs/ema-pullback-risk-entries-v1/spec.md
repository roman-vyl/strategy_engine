# Specification: EMA Pullback Risk and Final Entries v1

## Requirement: BBB-compatible risk resolution

The engine SHALL accept `components.risk` as either a component-id string or an object containing `component_id`. Version 1 SHALL support `no_risk_filter` and SHALL reject unknown risk components.

## Requirement: Final entry composition

For each enabled side, the final entry mask SHALL be the element-wise conjunction of the existing pre-risk entry mask and the risk allow mask. For `no_risk_filter`, this SHALL preserve the pre-risk mask exactly.

## Requirement: Honest readiness

A successful range evaluation SHALL expose final long/short entry masks and mark `entries_ready=true`. It SHALL keep `decisions_ready=false` until exit semantics are ported.
