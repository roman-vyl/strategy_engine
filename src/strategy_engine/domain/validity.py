"""Validity metadata shared by indicator and strategy results."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Validity:
    valid_from_ms: int | None
    warmup_bars: int
    complete: bool
    reason: str | None = None
