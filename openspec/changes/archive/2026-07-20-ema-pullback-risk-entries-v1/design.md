# Design: EMA Pullback Risk and Final Entries v1

The new stage consumes `SideTriggerEvaluation.pre_risk_entry_allowed` and the canonical `components.risk` field. For `no_risk_filter`, the risk allow mask is all true on the evaluation grid. Final entries are the element-wise AND of the pre-risk mask and the risk mask.

The Strategy API returns final `entries.long` and `entries.short`, plus risk evidence. The evaluation stage becomes `entries_ready`. Exit decisions remain unported, so `decisions_ready` remains false.
