# Managed policy replay

> **Boundary clarification:** There is no direct Strategy Engine → Abi contract. The approved direction is Strategy Engine → Strategy Runtime → Abi Executor. The phrase "Runtime/Abi path" below describes that mediated path. The exact current-point decision contract remains an implementation gate and is not defined by this replay endpoint.


`POST /v1/strategy-evaluations/managed-replay` evaluates strategy-owned management for one already-open trade.

It returns phase transitions, tighten-only managed stop changes, take-profile changes and runtime-exit decisions. All management updates are end-of-bar decisions effective from the next bar.

It intentionally does not return actual fills or closed trades. BBB simulation or the future Runtime/Abi path applies the returned decisions to execution facts.
