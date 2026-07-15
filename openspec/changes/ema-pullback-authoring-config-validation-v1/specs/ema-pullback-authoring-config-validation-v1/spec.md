# Requirements
- Strategy Engine SHALL own validation of ema_pullback instance semantics.
- The endpoint SHALL accept the existing Workbench authoring shape.
- Validation SHALL translate to and reuse the canonical strategy validator.
- Invalid instances SHALL return `valid=false` with an `instances[N]` path.
