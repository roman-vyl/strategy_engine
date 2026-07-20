# Design

Add `GET /v1/strategies/{strategy_id}/composer-catalog`. For `ema_pullback`, return the BBB-compatible `ComponentCatalog` DTO including sections, component schemas, context providers, and context-consumption policies. Unknown strategies return the standard 404 error envelope.
