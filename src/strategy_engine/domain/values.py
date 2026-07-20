"""Decimal-text parsing and deterministic canonical JSON hashing."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Any

from strategy_engine.domain.errors import InvalidRequestError


def parse_decimal_text(value: str) -> Decimal:
    if not isinstance(value, str):
        raise InvalidRequestError("numeric value must be decimal text")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise InvalidRequestError("invalid decimal text", value=value) from exc
    if not parsed.is_finite():
        raise InvalidRequestError("decimal value must be finite", value=value)
    return parsed


def normalized_decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise InvalidRequestError("decimal value must be finite")
    text = format(value.normalize(), "f")
    return "0" if text in {"-0", ""} else text


def parse_normalized_decimal_text(value: str) -> Decimal:
    """Parse canonical plain decimal text without changing its numeric value."""

    parsed = parse_decimal_text(value)
    if value != normalized_decimal_text(parsed):
        raise InvalidRequestError("decimal text must be normalized", value=value)
    return parsed


def canonical_json_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
