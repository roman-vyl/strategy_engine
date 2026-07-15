"""Consumer-role metadata for reusable strategy components."""

from __future__ import annotations

from dataclasses import dataclass

ROLE_EXIT_POLICY_STOP_LOSS = "exit_policy.stop_loss"
ROLE_EXIT_POLICY_TAKE_PROFIT = "exit_policy.take_profit"
ROLE_EXIT_POLICY_SIGNAL_EXIT = "exit_policy.signal_exit"
ROLE_EXIT_MANAGEMENT_PHASE_CONDITION = "exit_management.phase_condition"
ROLE_EXIT_MANAGEMENT_RUNTIME_EXIT = "exit_management.runtime_exit"
ROLE_EXIT_MANAGEMENT_STOP_RULE = "exit_management.stop_rule"
ROLE_EXIT_MANAGEMENT_TAKE_RULE = "exit_management.take_rule"

EXIT_LAYER_EXIT_POLICY = "exit_policy"
EXIT_LAYER_STOP_RULE = "exit_management.stop_rule"
EXIT_LAYER_TAKE_RULE = "exit_management.take_rule"
EXIT_LAYER_RUNTIME_EXIT = "exit_management.runtime_exit"

EXIT_OWNER_EXIT_POLICY = "exit_policy"
EXIT_OWNER_EXIT_MANAGEMENT = "exit_management"


@dataclass(frozen=True)
class ConsumerRoleMetadata:
    component_id: str
    allowed_roles: frozenset[str]
    input_contract: str
    output_contract: str
    side_aware: bool
    params_schema_ref: str
    feature_requirements: tuple[str, ...] = ()
    diagnostics_contract: tuple[str, ...] = ()


def exit_owner_for_layer(exit_layer: str) -> str:
    if exit_layer == EXIT_LAYER_EXIT_POLICY:
        return EXIT_OWNER_EXIT_POLICY
    if exit_layer.startswith("exit_management."):
        return EXIT_OWNER_EXIT_MANAGEMENT
    return EXIT_OWNER_EXIT_POLICY


def validate_consumer_role(*, component_id: str, role: str) -> None:
    meta = CONSUMER_ROLE_REGISTRY.get(component_id)
    if meta is None:
        raise ValueError(f"unknown component_id {component_id!r}")
    if role not in meta.allowed_roles:
        allowed = ", ".join(sorted(meta.allowed_roles))
        raise ValueError(
            f"component {component_id!r} is not allowed in role {role!r}; "
            f"allowed roles: {allowed}"
        )


CONSUMER_ROLE_REGISTRY: dict[str, ConsumerRoleMetadata] = {
    "rsi_signal_exit": ConsumerRoleMetadata(
        component_id="rsi_signal_exit",
        allowed_roles=frozenset(
            {ROLE_EXIT_POLICY_SIGNAL_EXIT, ROLE_EXIT_MANAGEMENT_RUNTIME_EXIT}
        ),
        input_contract="exit_rule_params",
        output_contract="signal_mask",
        side_aware=True,
        params_schema_ref="rsi_signal_exit",
        feature_requirements=("rsi",),
        diagnostics_contract=("rsi", "threshold", "condition"),
    ),
    "ema_cross_loss_exit": ConsumerRoleMetadata(
        component_id="ema_cross_loss_exit",
        allowed_roles=frozenset(
            {ROLE_EXIT_POLICY_SIGNAL_EXIT, ROLE_EXIT_MANAGEMENT_RUNTIME_EXIT}
        ),
        input_contract="exit_rule_params",
        output_contract="signal_mask",
        side_aware=True,
        params_schema_ref="ema_cross_loss_exit",
        feature_requirements=("fast_ema", "slow_ema"),
        diagnostics_contract=("fast_ema", "slow_ema", "confirm_bars"),
    ),
    "atr_stop_loss": ConsumerRoleMetadata(
        component_id="atr_stop_loss",
        allowed_roles=frozenset({ROLE_EXIT_POLICY_STOP_LOSS}),
        input_contract="exit_rule_params",
        output_contract="distance_level",
        side_aware=True,
        params_schema_ref="atr_stop_loss",
        feature_requirements=("atr_distance",),
        diagnostics_contract=(),
    ),
    "atr_take_profit": ConsumerRoleMetadata(
        component_id="atr_take_profit",
        allowed_roles=frozenset({ROLE_EXIT_POLICY_TAKE_PROFIT}),
        input_contract="exit_rule_params",
        output_contract="distance_level",
        side_aware=True,
        params_schema_ref="atr_take_profit",
        feature_requirements=("atr_distance",),
        diagnostics_contract=(),
    ),
    "adx_di_threshold": ConsumerRoleMetadata(
        component_id="adx_di_threshold",
        allowed_roles=frozenset({ROLE_EXIT_MANAGEMENT_PHASE_CONDITION}),
        input_contract="phase_condition_params",
        output_contract="phase_condition_bool",
        side_aware=True,
        params_schema_ref="adx_di_threshold",
        feature_requirements=("adx", "di_plus", "di_minus"),
        diagnostics_contract=("adx", "di_plus", "di_minus"),
    ),
    "phase_runtime_exit": ConsumerRoleMetadata(
        component_id="phase_runtime_exit",
        allowed_roles=frozenset({ROLE_EXIT_MANAGEMENT_RUNTIME_EXIT}),
        input_contract="phase_runtime_exit_params",
        output_contract="market_close_trigger",
        side_aware=False,
        params_schema_ref="phase_runtime_exit",
        diagnostics_contract=("exit_price",),
    ),
    "break_even_stop": ConsumerRoleMetadata(
        component_id="break_even_stop",
        allowed_roles=frozenset({ROLE_EXIT_MANAGEMENT_STOP_RULE}),
        input_contract="stop_management_params",
        output_contract="managed_stop_price",
        side_aware=True,
        params_schema_ref="break_even_stop",
        diagnostics_contract=(),
    ),
    "lock_profit_stop": ConsumerRoleMetadata(
        component_id="lock_profit_stop",
        allowed_roles=frozenset({ROLE_EXIT_MANAGEMENT_STOP_RULE}),
        input_contract="stop_management_params",
        output_contract="managed_stop_price",
        side_aware=True,
        params_schema_ref="lock_profit_stop",
        diagnostics_contract=(),
    ),
    "take_profile_switch": ConsumerRoleMetadata(
        component_id="take_profile_switch",
        allowed_roles=frozenset({ROLE_EXIT_MANAGEMENT_TAKE_RULE}),
        input_contract="take_management_params",
        output_contract="take_profile_state",
        side_aware=False,
        params_schema_ref="take_profile_switch",
        diagnostics_contract=("take_profile",),
    ),
}
