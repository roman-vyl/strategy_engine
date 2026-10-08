"""`change_since_entry`: a trade child of `composite_phase_condition` that
compares a feature with its own value on the trade's entry bar (OpenSpec
`entry-anchored-change-v1`, design D1-D6).

Not a predicate: the anchor depends on the trade, so the child is a trade
child valued per bar, like `mfe_r`. The operand grammar, the canonical
feature-kind resolution and the aligned plan column are the predicate
layer's own (`predicates._operand`); nothing here aligns or computes a
feature.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.indicators.contracts import PlannedFeature
from strategy_engine.strategies.ema_pullback.predicates import (
    _COMPARE_OPS,
    _mapping,
    _number,
    _only_fields,
    _operand,
)

CHANGE_SINCE_ENTRY = "change_since_entry"

_FIELDS = {"operand", "op", "value"}


@dataclass(frozen=True, slots=True)
class ChangeSinceEntry:
    feature: PlannedFeature
    op: str
    value: float

    def met(self, current: float | None, anchor: float | None) -> bool:
        """`current - anchor <op> value`; False when either point is missing
        or non-finite (design D4)."""

        if current is None or anchor is None:
            return False
        if not (math.isfinite(current) and math.isfinite(anchor)):
            return False
        return bool(_COMPARE_OPS[self.op](current - anchor, self.value))


def parse_change_since_entry(params: object, path: str) -> ChangeSinceEntry:
    """Market-data-free parse of the atom's params (design D2)."""

    payload = _mapping(params, path)
    _only_fields(payload, _FIELDS, path)
    operand = _operand(payload.get("operand"), f"{path}.operand", None)
    if operand.feature is None:
        raise InvalidRequestError(f"{path}.operand must be a feature reference")
    op = payload.get("op")
    if op not in _COMPARE_OPS:
        raise InvalidRequestError(f"{path}.op must be one of >, >=, <, <=", op=op)
    value = _number(payload.get("value"), f"{path}.value")
    return ChangeSinceEntry(operand.feature, str(op), value)


def change_since_entry_of(condition: Mapping[str, Any], path: str) -> ChangeSinceEntry | None:
    """The parsed atom when `condition` is a `change_since_entry` item."""

    if str(condition.get("component_id", "")) != CHANGE_SINCE_ENTRY:
        return None
    return parse_change_since_entry(condition.get("params", {}), f"{path}.params")
