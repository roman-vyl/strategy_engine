"""Semantic node identity (`NodeSpec`) for evaluation-path computation nodes.

OpenSpec change `batch-computation-reuse`, group 3 (design.md D2). A
`NodeSpec` is the frozen, hashable identity of one computation node, built
by that node family's `resolve()` from the *same* normalized inputs its
`compute()` uses:

- `kind` + `version`: the node kind and its implementation version tag;
- `params`: normalized effective local parameters (post-defaults), each
  value canonicalized into a type-tagged, bit-exact form (see `canonical`);
- `upstream`: the identities (recursively, never the values) of the nodes
  this node reads, under named roles;
- `side`: present only when the node's own computation reads the side.

The market/range identity is deliberately *not* repeated here: it is the
scope of the (future) per-range evaluation context that owns the memo, so
identities from different ranges can never meet. Nothing in this module
memoizes or consumes identities; it only defines the value.

This identity is never derived from a feature-plan `output_id` -- that
label collides distinct computations and splits identical ones.

Identity contract (spec "Semantic node identity"): equivalent normalized
inputs/dependencies produce the same identity; distinct computation never
produces the same identity; the same identity implies a bit-identical
result. It is defined over normalized inputs and dependency structure,
never inferred from output values.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

# A canonical parameter value: a type-tagged tuple, so values that compare
# equal in Python but may compute differently never merge (`True == 1`,
# `1 == 1.0`, `0.0 == -0.0`, and `nan != nan` all break naive keys).
Canonical = tuple[object, ...]


def canonical(value: object) -> Canonical:
    """Type-tagged, bit-exact canonical form of one normalized parameter.

    Callers pass values that have already been through the node's shared
    normalization helper (e.g. `int(params.get("lookback", 50))`), so the
    type here is the effective type the computation uses. Floats are keyed
    by their exact bit pattern (`float.hex`), so `-0.0`/`0.0` stay distinct
    and every NaN is the same value. Unsupported types fail closed.
    """

    if value is None:
        return ("none",)
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, int):
        return ("int", value)
    if isinstance(value, float):
        return ("float", value.hex())
    if isinstance(value, str):
        return ("str", value)
    if isinstance(value, tuple):
        return ("tuple", tuple(canonical(item) for item in value))
    if isinstance(value, frozenset):
        return ("set", tuple(sorted((canonical(item) for item in value), key=repr)))
    raise TypeError(f"unsupported NodeSpec parameter type: {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class NodeSpec:
    kind: str
    version: int
    params: tuple[tuple[str, Canonical], ...]
    upstream: tuple[tuple[str, Upstream], ...]
    side: str | None

    def param(self, name: str) -> Canonical:
        for key, value in self.params:
            if key == name:
                return value
        raise KeyError(name)

    def dependency(self, role: str) -> Upstream:
        for key, value in self.upstream:
            if key == role:
                return value
        raise KeyError(role)


# One upstream slot: a single dependency, an absent one (`None`), or an
# order-insensitive, duplicate-insensitive set -- only valid for inputs
# combined by a commutative, idempotent operation (logical AND/OR, min).
Upstream = NodeSpec | None | frozenset[NodeSpec]


def node_spec(
    kind: str,
    *,
    version: int,
    params: Mapping[str, object] | None = None,
    upstream: Mapping[str, NodeSpec | None | Iterable[NodeSpec]] | None = None,
    side: str | None = None,
) -> NodeSpec:
    """Build a `NodeSpec` with a canonical (key-sorted) layout.

    An iterable upstream value (anything other than a `NodeSpec` or `None`)
    becomes a `frozenset`: callers use that only for commutative, idempotent
    combinators, where declared order and duplicates cannot change the
    result.
    """

    if side is not None and side not in {"long", "short"}:
        raise ValueError(f"NodeSpec side must be long, short, or None: {side!r}")
    normalized_upstream: list[tuple[str, Upstream]] = []
    for role, dependency in sorted((upstream or {}).items()):
        if dependency is None or isinstance(dependency, NodeSpec):
            normalized_upstream.append((role, dependency))
        else:
            normalized_upstream.append((role, frozenset(dependency)))
    return NodeSpec(
        kind=kind,
        version=version,
        params=tuple((key, canonical(value)) for key, value in sorted((params or {}).items())),
        upstream=tuple(normalized_upstream),
        side=side,
    )
