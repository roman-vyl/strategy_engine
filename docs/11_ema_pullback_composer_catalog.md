# EMA Pullback Composer Catalog

`GET /v1/strategies/ema_pullback/composer-catalog` returns the complete BBB-compatible Workbench Composer schema. This includes UI sections, component parameter schemas, context providers, and context-consumption policies. The catalog now lives with the strategy semantics it describes.

## Generic predicate operands

The predicate and weighted-vote operand grammar now includes `interval_change`,
`scale`, and `ratio.denominator_mode`. See [wire contracts and examples](interval_series_operands_v1.md).
Validation uses the canonical predicate parser; these are operand expressions,
not standalone Composer strategy components.
