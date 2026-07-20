# Design

The shared seam maps `run_strategy_spec`, `run_managed_execution_loop`, managed provider methods and `build_signal_trace_from_spec` one-to-one across Strategy Engine outputs and Research Service consumers. No compatibility execution, legacy fallback or duplicate policy calculation is allowed.
