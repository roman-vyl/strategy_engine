"""`composite_setup` and `composite_phase_condition` spec parsing and
market-data-free validation.

Dependency-neutral (imports only domain errors), so the static semantic
check, the feature planner, the live history planner and the setup
evaluator all share one parse of the same `params` and can never disagree
on what a composite means (OpenSpec `composite-setup-pre-entry-predicates-v1`,
design D1, D12). `composite_phase_condition` (OpenSpec
`composite-managed-phase-condition-v1`, design D1, D2) shares the
children/paths structure parser and differs only in its child parser.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from strategy_engine.domain.errors import InvalidRequestError

COMPOSITE_SETUP = "composite_setup"

# Existing semantic setups allowed as composite children. `composite_setup`
# itself is deliberately absent: no nested composites in v1.
SEMANTIC_SETUP_CHILDREN = frozenset(
    {"untouched_anchor_setup", "ema_bounce_counter_setup", "anchor_stack_width_setup"}
)

COMPOSITE_PHASE_CONDITION = "composite_phase_condition"

# Existing managed phase atoms allowed as `composite_phase_condition`
# children (design D1). The composite itself is absent: no nesting.
PHASE_ATOM_CHILDREN = frozenset(
    {"bars_in_trade", "mfe_pct", "mfe_atr", "mfe_r", "adx_di_threshold"}
)

_ID_SEPARATOR = "/"


@dataclass(frozen=True, slots=True)
class CompositeChild:
    child_id: str
    setup: Mapping[str, Any] | None
    predicate: Mapping[str, Any] | None
    # Phase-condition children only: an existing managed atom item.
    condition: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class CompositePath:
    path_id: str
    require: tuple[str, ...]
    at_least_k: int | None
    at_least_of: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompositeSpec:
    instance_id: str
    children: tuple[CompositeChild, ...]
    paths: tuple[CompositePath, ...]

    def child(self, child_id: str) -> CompositeChild:
        for child in self.children:
            if child.child_id == child_id:
                return child
        raise KeyError(child_id)


@dataclass(frozen=True, slots=True)
class CompositePhaseCondition:
    children: tuple[CompositeChild, ...]
    paths: tuple[CompositePath, ...]

    def child(self, child_id: str) -> CompositeChild:
        for child in self.children:
            if child.child_id == child_id:
                return child
        raise KeyError(child_id)


def child_instance_key(instance_id: str, child_id: str) -> str:
    """Internal plan/instance key of a semantic setup child (design D6)."""

    return f"{instance_id}{_ID_SEPARATOR}{child_id}"


def child_setup_item(spec: CompositeSpec, child: CompositeChild) -> dict[str, Any]:
    """The ordinary setup item a semantic child is evaluated as: its own
    component and params under the internal instance key."""

    assert child.setup is not None
    return {
        "component_id": str(child.setup.get("component_id", "")),
        "instance_id": child_instance_key(spec.instance_id, child.child_id),
        "params": dict(_mapping(child.setup.get("params", {}), "params")),
    }


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidRequestError(f"{path} must be an object")
    return value


def _list(value: object, path: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise InvalidRequestError(f"{path} must be a non-empty list")
    return value


def _identifier(value: object, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise InvalidRequestError(f"{path} must be a non-empty string")
    if _ID_SEPARATOR in value:
        raise InvalidRequestError(f"{path} must not contain '{_ID_SEPARATOR}'", value=value)
    return value


def _child(raw: object, path: str) -> CompositeChild:
    payload = _mapping(raw, path)
    child_id = _identifier(payload.get("child_id"), f"{path}.child_id")
    has_setup = payload.get("setup") is not None
    has_predicate = payload.get("predicate") is not None
    if has_setup == has_predicate:
        raise InvalidRequestError(
            f"{path} must carry exactly one of setup or predicate", child_id=child_id
        )
    unknown = set(payload) - {"child_id", "setup", "predicate"}
    if unknown:
        raise InvalidRequestError(f"{path} has unknown fields", fields=sorted(unknown))
    if has_setup:
        setup = _mapping(payload.get("setup"), f"{path}.setup")
        component_id = str(setup.get("component_id", ""))
        if component_id == COMPOSITE_SETUP:
            raise InvalidRequestError("composite_setup cannot be nested", child_id=child_id)
        if component_id not in SEMANTIC_SETUP_CHILDREN:
            raise InvalidRequestError(
                "unsupported composite setup child", component_id=component_id
            )
        for forbidden in ("instance_id", "context_consumption"):
            if forbidden in setup:
                raise InvalidRequestError(
                    f"composite setup child must not declare {forbidden}", child_id=child_id
                )
        _mapping(setup.get("params", {}), f"{path}.setup.params")
        return CompositeChild(child_id, setup, None)
    predicate = _mapping(payload.get("predicate"), f"{path}.predicate")
    return CompositeChild(child_id, None, predicate)


def _phase_child(raw: object, path: str) -> CompositeChild:
    payload = _mapping(raw, path)
    child_id = _identifier(payload.get("child_id"), f"{path}.child_id")
    has_condition = payload.get("condition") is not None
    has_predicate = payload.get("predicate") is not None
    if has_condition == has_predicate:
        raise InvalidRequestError(
            f"{path} must carry exactly one of condition or predicate", child_id=child_id
        )
    unknown = set(payload) - {"child_id", "condition", "predicate"}
    if unknown:
        raise InvalidRequestError(f"{path} has unknown fields", fields=sorted(unknown))
    if has_predicate:
        predicate = _mapping(payload.get("predicate"), f"{path}.predicate")
        return CompositeChild(child_id, None, predicate)
    condition = _mapping(payload.get("condition"), f"{path}.condition")
    component_id = str(condition.get("component_id", ""))
    if component_id == COMPOSITE_PHASE_CONDITION:
        raise InvalidRequestError("composite_phase_condition cannot be nested", child_id=child_id)
    if component_id not in PHASE_ATOM_CHILDREN:
        raise InvalidRequestError(
            "unsupported composite phase condition child", component_id=component_id
        )
    unknown = set(condition) - {"component_id", "params"}
    if unknown:
        raise InvalidRequestError(f"{path}.condition has unknown fields", fields=sorted(unknown))
    _mapping(condition.get("params", {}), f"{path}.condition.params")
    return CompositeChild(child_id, None, None, condition)


def _references(value: object, path: str) -> tuple[str, ...]:
    items = _list(value, path)
    refs = tuple(_identifier(item, f"{path}[{index}]") for index, item in enumerate(items))
    if len(set(refs)) != len(refs):
        raise InvalidRequestError(f"{path} must not repeat a child_id")
    return refs


def _path(raw: object, path: str) -> CompositePath:
    payload = _mapping(raw, path)
    path_id = _identifier(payload.get("path_id"), f"{path}.path_id")
    unknown = set(payload) - {"path_id", "require", "at_least"}
    if unknown:
        raise InvalidRequestError(f"{path} has unknown fields", fields=sorted(unknown))
    require: tuple[str, ...] = ()
    if payload.get("require") is not None:
        require = _references(payload.get("require"), f"{path}.require")
    at_least_k: int | None = None
    at_least_of: tuple[str, ...] = ()
    if payload.get("at_least") is not None:
        at_least = _mapping(payload.get("at_least"), f"{path}.at_least")
        at_least_of = _references(at_least.get("of"), f"{path}.at_least.of")
        k = at_least.get("k")
        if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= len(at_least_of):
            raise InvalidRequestError(
                f"{path}.at_least.k must be an integer in 1..len(of)", k=k
            )
        at_least_k = k
    if not require and at_least_k is None:
        raise InvalidRequestError(f"{path} must declare require or at_least", path_id=path_id)
    return CompositePath(path_id, require, at_least_k, at_least_of)


def _structure(
    params: Mapping[str, Any],
    path: str,
    parse_child: Callable[[object, str], CompositeChild],
) -> tuple[tuple[CompositeChild, ...], tuple[CompositePath, ...]]:
    """Children and paths with every structural rule shared by both
    composites; `parse_child` is the role-specific child parser."""

    children = tuple(
        parse_child(raw, f"{path}.params.children[{index}]")
        for index, raw in enumerate(_list(params.get("children"), f"{path}.params.children"))
    )
    child_ids = [child.child_id for child in children]
    if len(set(child_ids)) != len(child_ids):
        raise InvalidRequestError("composite child_id values must be unique")
    paths = tuple(
        _path(raw, f"{path}.params.paths[{index}]")
        for index, raw in enumerate(_list(params.get("paths"), f"{path}.params.paths"))
    )
    path_ids = [item_.path_id for item_ in paths]
    if len(set(path_ids)) != len(path_ids):
        raise InvalidRequestError("composite path_id values must be unique")
    known = set(child_ids)
    referenced: set[str] = set()
    for composite_path in paths:
        for ref in (*composite_path.require, *composite_path.at_least_of):
            if ref not in known:
                raise InvalidRequestError(
                    "composite path references an unknown child",
                    path_id=composite_path.path_id,
                    child_id=ref,
                )
            referenced.add(ref)
    unreferenced = [child_id for child_id in child_ids if child_id not in referenced]
    if unreferenced:
        raise InvalidRequestError(
            "composite children must be referenced by a path", child_ids=unreferenced
        )
    return children, paths


def parse_composite_setup(item: Mapping[str, Any], path: str = "setup") -> CompositeSpec:
    """Parse and structurally validate one `composite_setup` item. Predicate
    children are returned unparsed; their own validation belongs to the
    predicate layer."""

    instance_id = _identifier(item.get("instance_id"), f"{path}.instance_id")
    params = _mapping(item.get("params", {}), f"{path}.params")
    children, paths = _structure(params, path, _child)
    return CompositeSpec(instance_id, children, paths)


def parse_composite_phase_condition(
    condition: Mapping[str, Any], path: str = "condition"
) -> CompositePhaseCondition:
    """Parse and structurally validate one `composite_phase_condition`
    (design D1, D2). Predicate children are returned unparsed (the predicate
    layer validates them); atom children keep their existing params, which
    their existing formulas validate at evaluation, exactly as for an atomic
    rule."""

    unknown = set(condition) - {"component_id", "params"}
    if unknown:
        raise InvalidRequestError(f"{path} has unknown fields", fields=sorted(unknown))
    params = _mapping(condition.get("params", {}), f"{path}.params")
    extra = set(params) - {"children", "paths"}
    if extra:
        raise InvalidRequestError(f"{path}.params has unknown fields", fields=sorted(extra))
    children, paths = _structure(params, path, _phase_child)
    return CompositePhaseCondition(children, paths)


def phase_rule_composites(
    exit_management: Mapping[str, Any],
) -> tuple[tuple[int, CompositePhaseCondition], ...]:
    """(phase rule index, parsed composite) for every composite phase
    condition of `exit_management.phase_rules`, in declared order."""

    rules = exit_management.get("phase_rules", ()) or ()
    if not isinstance(rules, (list, tuple)):
        return ()
    out: list[tuple[int, CompositePhaseCondition]] = []
    for index, rule in enumerate(rules):
        if not isinstance(rule, Mapping):
            continue
        condition = rule.get("condition")
        if (
            isinstance(condition, Mapping)
            and str(condition.get("component_id", "")) == COMPOSITE_PHASE_CONDITION
        ):
            out.append(
                (
                    index,
                    parse_composite_phase_condition(condition, f"phase_rules[{index}].condition"),
                )
            )
    return tuple(out)


def composite_items(setups: tuple[Mapping[str, Any], ...]) -> tuple[CompositeSpec, ...]:
    """Parsed composites among top-level setup items, in declared order."""

    return tuple(
        parse_composite_setup(item, f"setups[{index}]")
        for index, item in enumerate(setups)
        if str(item.get("component_id", "")) == COMPOSITE_SETUP
    )


def require_no_internal_key_collision(
    top_level_instance_ids: tuple[str, ...], composites: tuple[CompositeSpec, ...]
) -> None:
    """A top-level setup `instance_id` must not equal an internal child key
    (`"{instance_id}/{child_id}"`), or both would share plan columns."""

    top_level = set(top_level_instance_ids)
    for spec in composites:
        for child in spec.children:
            key = child_instance_key(spec.instance_id, child.child_id)
            if key in top_level:
                raise InvalidRequestError(
                    "setup instance_id collides with a composite child key", instance_id=key
                )
