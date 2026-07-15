"""Half-open aligned range contracts."""

from __future__ import annotations

from dataclasses import dataclass

from strategy_engine.domain.errors import InvalidRequestError


def timeframe_duration_ms(timeframe: str) -> int:
    try:
        count = int(timeframe[:-1])
        unit = timeframe[-1]
    except (ValueError, IndexError) as exc:
        raise InvalidRequestError("unsupported timeframe", timeframe=timeframe) from exc
    multipliers = {"m": 60_000, "h": 3_600_000, "d": 86_400_000, "w": 604_800_000}
    if count <= 0 or unit not in multipliers:
        raise InvalidRequestError("unsupported timeframe", timeframe=timeframe)
    return count * multipliers[unit]


@dataclass(frozen=True, slots=True)
class TimeRange:
    from_ms: int
    to_ms: int

    def validate_alignment(self, timeframe: str) -> None:
        if self.from_ms < 0 or self.to_ms <= self.from_ms:
            raise InvalidRequestError(
                "range must be a positive half-open interval",
                from_ms=self.from_ms,
                to_ms=self.to_ms,
            )
        step_ms = timeframe_duration_ms(timeframe)
        if self.from_ms % step_ms or self.to_ms % step_ms:
            raise InvalidRequestError(
                "range boundaries must align to timeframe grid",
                timeframe=timeframe,
                from_ms=self.from_ms,
                to_ms=self.to_ms,
            )
