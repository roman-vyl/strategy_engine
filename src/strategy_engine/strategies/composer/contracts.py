"""Component catalog contracts for Strategy Composer."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ParamFieldSchema(BaseModel):
    """JSON-Schema-like field descriptor for Composer forms."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["integer", "number", "string", "boolean", "array"]
    label: str | None = None
    min: float | None = None
    max: float | None = None
    enum: list[str] | None = None
    default: Any = None


class ContextConsumptionPolicySchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_id: str
    label: str
    params_schema: dict[str, ParamFieldSchema] = Field(default_factory=dict)


class ContextConsumptionRoleSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str
    label: str
    policies: list[ContextConsumptionPolicySchema] = Field(default_factory=list)


class ContextProviderSchema(BaseModel):
    """Strategy-level context provider (not a pipeline component slot)."""

    model_config = ConfigDict(extra="forbid")

    component_id: str
    label: str
    description: str | None = None
    params_schema: dict[str, ParamFieldSchema] = Field(default_factory=dict)


class ComponentSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component_id: str
    role: Literal["direction", "setup", "trigger", "blockers", "exits", "risk", "exit_management"]
    allowed_roles: list[str] = Field(default_factory=list)
    label: str
    description: str | None = None
    params_schema: dict[str, ParamFieldSchema] = Field(default_factory=dict)
    params_storage: Literal["flat", "nested"] = "flat"
    list_slot: bool = False
    supports_context_consumption: bool = False
    context_consumption_policies: list[ContextConsumptionPolicySchema] = Field(default_factory=list)


class ComposerSectionSchema(BaseModel):
    """UI section metadata (direction, blockers, …)."""

    model_config = ConfigDict(extra="forbid")

    section_id: str
    label: str
    role: str | None = None
    list_slot: bool = False


class ComponentCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family: str
    schema_version: int = 1
    sections: list[ComposerSectionSchema]
    components: list[ComponentSchema]
    context_providers: list[ContextProviderSchema] = Field(default_factory=list)
    context_consumption_roles: list[ContextConsumptionRoleSchema] = Field(default_factory=list)
