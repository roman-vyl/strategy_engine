"""`weighted_vote_setup` spec parsing and market-data-free validation
(OpenSpec `weighted-vote-setup-v1`).

Dependency-neutral like `composite_spec`: the static semantic check, the
feature planner, the live history planner and the setup evaluator share one
parse of the same `params`. Operands and `count.of` predicates are returned
as raw predicate items; their own validation belongs to the predicate layer.
An operand input is carried as a `range` over that operand with no bounds,
so the predicate layer validates, plans, identifies and evaluates the
operand exactly as it does for a `range` child (design D2).

Weights and the threshold are exact decimals held as integers in units of
10**-9 (design D6): sums and the threshold comparison are exact and never
depend on voter order or on binary floating point.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from strategy_engine.domain.errors import InvalidRequestError

WEIGHTED_VOTE_SETUP = "weighted_vote_setup"

WEIGHT_DIGITS = 9
WEIGHT_SCALE: int = 10**WEIGHT_DIGITS
# Upper bound of a weight and of the threshold. Keeps every voter sum far
# inside int64 (at most 10**15 scaled per voter) for any realistic voter count.
WEIGHT_MAX = 10**6

_ROLES = frozenset({"vote", "veto"})
_DIRECTIONS = frozenset({"at_most", "at_least"})
_ID_SEPARATOR = "/"


@dataclass(frozen=True, slots=True)
class VoteStep:
    level: float | int
    # Exact weight in units of 10**-9, None for a veto step.
    weight: int | None

    @property
    def veto(self) -> bool:
        return self.weight is None


@dataclass(frozen=True, slots=True)
class VoteInput:
    input_id: str
    steps: tuple[VoteStep, ...]
    # Exactly one of: an operand input (a bound-free `range` predicate item
    # over the operand, plus its direction) or the `count.of` predicate items.
    operand_predicate: Mapping[str, Any] | None
    direction: str | None
    count_of: tuple[Mapping[str, Any], ...] = ()

    def predicates(self) -> tuple[Mapping[str, Any], ...]:
        """The raw predicate items this input reads, in declared order."""

        if self.operand_predicate is not None:
            return (self.operand_predicate,)
        return self.count_of


@dataclass(frozen=True, slots=True)
class Voter:
    voter_id: str
    role: str
    inputs: tuple[VoteInput, ...]


@dataclass(frozen=True, slots=True)
class WeightedVoteSpec:
    instance_id: str
    threshold: int  # units of 10**-9
    voters: tuple[Voter, ...]

    def inputs(self) -> tuple[VoteInput, ...]:
        return tuple(item for voter in self.voters for item in voter.inputs)


def operand_range_item(operand: object) -> dict[str, Any]:
    """The bound-free `range` predicate item an operand input is read
    through. It never blocks; only its operand value is used."""

    return {"kind": "range", "operand": operand, "min": None, "max": None}


def scaled_to_float(value: int) -> float:
    """Nearest float of an exact 10**-9 scaled integer (true division of
    two integers is correctly rounded)."""

    return value / WEIGHT_SCALE


def scaled_to_text(value: int) -> str:
    """Canonical exact decimal string of a 10**-9 scaled integer."""

    text = format(Decimal(value).scaleb(-WEIGHT_DIGITS), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidRequestError(f"{path} must be an object")
    return value


def _list(value: object, path: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise InvalidRequestError(f"{path} must be a non-empty list")
    return value


def _only(payload: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = set(payload) - allowed
    if unknown:
        raise InvalidRequestError(f"{path} has unknown fields", fields=sorted(unknown))


def _identifier(value: object, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise InvalidRequestError(f"{path} must be a non-empty string")
    if _ID_SEPARATOR in value:
        raise InvalidRequestError(f"{path} must not contain '{_ID_SEPARATOR}'", value=value)
    return value


def _real(value: object, path: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidRequestError(f"{path} must be a number", value=value)
    if not math.isfinite(value):
        raise InvalidRequestError(f"{path} must be finite", value=value)
    return value


def exact_decimal(value: object, path: str) -> int:
    """A JSON number as an exact decimal in units of 10**-9: the decimal of
    its shortest round-trip representation (Python `repr`), at most nine
    digits after the point (design D6)."""

    number = _real(value, path)
    try:
        exact = Decimal(repr(number)) if isinstance(number, float) else Decimal(number)
    except InvalidOperation as exc:  # pragma: no cover - finite reals always parse
        raise InvalidRequestError(f"{path} must be a decimal number", value=value) from exc
    if abs(exact) > WEIGHT_MAX:
        raise InvalidRequestError(f"{path} must not exceed {WEIGHT_MAX} in magnitude", value=value)
    exponent = exact.as_tuple().exponent
    assert isinstance(exponent, int)
    if exponent < -WEIGHT_DIGITS:
        raise InvalidRequestError(
            f"{path} must have at most {WEIGHT_DIGITS} digits after the decimal point",
            value=value,
        )
    return int(exact.scaleb(WEIGHT_DIGITS))


def _step(raw: object, path: str, *, count_of: int | None) -> VoteStep:
    payload = _mapping(raw, path)
    _only(payload, {"level", "weight", "veto"}, path)
    if "level" not in payload:
        raise InvalidRequestError(f"{path}.level is required")
    level = _real(payload["level"], f"{path}.level")
    if count_of is not None and (not isinstance(level, int) or not 1 <= level <= count_of):
        raise InvalidRequestError(
            f"{path}.level of a count input must be an integer in 1..len(of)", level=level
        )
    has_weight, has_veto = "weight" in payload, "veto" in payload
    if has_weight == has_veto:
        raise InvalidRequestError(f"{path} must carry exactly one of weight or veto")
    if has_veto:
        if payload["veto"] is not True:
            raise InvalidRequestError(f"{path}.veto must be the literal true")
        return VoteStep(level, None)
    weight = exact_decimal(payload["weight"], f"{path}.weight")
    if weight < 0:
        raise InvalidRequestError(f"{path}.weight must not be negative")
    return VoteStep(level, weight)


def _input(raw: object, path: str) -> VoteInput:
    payload = _mapping(raw, path)
    _only(payload, {"input_id", "steps", "operand", "direction", "count"}, path)
    input_id = _identifier(payload.get("input_id"), f"{path}.input_id")
    has_operand, has_count = "operand" in payload, "count" in payload
    if has_operand == has_count:
        raise InvalidRequestError(
            f"{path} must carry exactly one of operand or count", input_id=input_id
        )
    raw_steps = _list(payload.get("steps"), f"{path}.steps")
    if has_operand:
        direction = payload.get("direction")
        if direction not in _DIRECTIONS:
            raise InvalidRequestError(
                f"{path}.direction must be at_most or at_least", direction=direction
            )
        steps = tuple(
            _step(item, f"{path}.steps[{index}]", count_of=None)
            for index, item in enumerate(raw_steps)
        )
        result = VoteInput(input_id, steps, operand_range_item(payload["operand"]), str(direction))
    else:
        if "direction" in payload:
            raise InvalidRequestError(f"{path}.direction is not allowed with count")
        count = _mapping(payload["count"], f"{path}.count")
        _only(count, {"of"}, f"{path}.count")
        of = tuple(
            _mapping(item, f"{path}.count.of[{index}]")
            for index, item in enumerate(_list(count.get("of"), f"{path}.count.of"))
        )
        steps = tuple(
            _step(item, f"{path}.steps[{index}]", count_of=len(of))
            for index, item in enumerate(raw_steps)
        )
        result = VoteInput(input_id, steps, None, None, of)
    levels = [float(step.level) for step in steps]
    if len(set(levels)) != len(levels):
        raise InvalidRequestError(f"{path}.steps levels must be unique", input_id=input_id)
    return result


def _voter(raw: object, path: str) -> Voter:
    payload = _mapping(raw, path)
    _only(payload, {"voter_id", "role", "inputs"}, path)
    voter_id = _identifier(payload.get("voter_id"), f"{path}.voter_id")
    role = payload.get("role")
    if role not in _ROLES:
        raise InvalidRequestError(f"{path}.role must be vote or veto", role=role)
    inputs = tuple(
        _input(item, f"{path}.inputs[{index}]")
        for index, item in enumerate(_list(payload.get("inputs"), f"{path}.inputs"))
    )
    if role == "veto" and any(not step.veto for item in inputs for step in item.steps):
        raise InvalidRequestError(
            f"{path}: a veto voter must have only veto steps", voter_id=voter_id
        )
    return Voter(voter_id, str(role), inputs)


def parse_weighted_vote_setup(item: Mapping[str, Any], path: str = "setup") -> WeightedVoteSpec:
    """Parse and structurally validate one `weighted_vote_setup` item."""

    instance_id = _identifier(item.get("instance_id"), f"{path}.instance_id")
    params = _mapping(item.get("params", {}), f"{path}.params")
    _only(params, {"threshold", "voters"}, f"{path}.params")
    if "threshold" not in params:
        raise InvalidRequestError(f"{path}.params.threshold is required")
    threshold = exact_decimal(params["threshold"], f"{path}.params.threshold")
    if threshold <= 0:
        raise InvalidRequestError(f"{path}.params.threshold must be greater than 0")
    voters = tuple(
        _voter(raw, f"{path}.params.voters[{index}]")
        for index, raw in enumerate(_list(params.get("voters"), f"{path}.params.voters"))
    )
    voter_ids = [voter.voter_id for voter in voters]
    if len(set(voter_ids)) != len(voter_ids):
        raise InvalidRequestError("weighted vote voter_id values must be unique")
    input_ids = [item.input_id for voter in voters for item in voter.inputs]
    if len(set(input_ids)) != len(input_ids):
        raise InvalidRequestError("weighted vote input_id values must be unique")
    return WeightedVoteSpec(instance_id, threshold, voters)


def weighted_vote_items(
    setups: tuple[Mapping[str, Any], ...],
) -> tuple[WeightedVoteSpec, ...]:
    """Parsed weighted votes among top-level setup items, in declared order."""

    return tuple(
        parse_weighted_vote_setup(item, f"setups[{index}]")
        for index, item in enumerate(setups)
        if str(item.get("component_id", "")) == WEIGHTED_VOTE_SETUP
    )
