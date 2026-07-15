# EMA Pullback Risk and Final Entries v1

This slice ports the remaining BBB entry-composition boundary.

Current BBB semantics contain one risk component, `no_risk_filter`, whose allow mask is true for every evaluated bar. The final side entry signal is therefore the existing pre-risk mask unchanged, but the explicit risk stage remains part of the contract so future risk components have a stable owner and API evidence shape.

Pipeline:

```text
direction
AND blockers
AND setups
AND trigger
= pre_risk_entry_allowed

pre_risk_entry_allowed
AND risk_allowed
= final entry mask
```

`POST /v1/strategy-evaluations/range` now returns `entries.long` and/or `entries.short` for enabled sides and risk evidence under `component_evidence.risk_entries`. The evaluation stage is `entries_ready`. Exit and managed-exit decisions remain unported, therefore `decisions_ready` remains false.
