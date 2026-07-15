# Design
`POST /v1/strategies/ema_pullback/authoring-config/validate` accepts `{instances:[...]}` in the existing Workbench instance shape. The adapter converts authoring fields into canonical `StrategySpecEnvelope` raw specs, then invokes the existing `ValidateStrategySpec`. It returns stable per-instance paths and hashes. No market data is read.
