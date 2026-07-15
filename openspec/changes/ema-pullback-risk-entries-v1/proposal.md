# Proposal: EMA Pullback Risk and Final Entries v1

Port the remaining BBB entry-composition layer: resolve the configured risk component, evaluate its side-aligned allow mask, and combine it with the already-ported direction, blockers, setups, and trigger outputs to produce final long/short entry masks.

The current BBB strategy supports `no_risk_filter`; this change preserves that exact behavior and rejects unknown risk components instead of inventing semantics.
