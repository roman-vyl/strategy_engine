# ADX/DMI Indicator Vertical Slice v1 Specification

## Requirement: coupled calculation

ADX, DI+, and DI- SHALL use one shared calculation for each timeframe/period pair and SHALL match the copied BBB implementation bar for bar.

## Requirement: validation

Each feature SHALL use kind `adx`, `di_plus`, or `di_minus`, source `close`, one positive integer `period`, and no dependencies or extra parameters.

## Requirement: warmup and HTF completion

DI series SHALL preserve BBB's explicit first-`period` null warmup. ADX SHALL preserve the Wilder-over-DX warmup. Higher-timeframe results SHALL become visible on the base grid only after the HTF bucket closes.

## Requirement: compatibility

The existing Indicator range API, Decimal-text serialization, deterministic plan hash, and caller-owned output IDs SHALL remain unchanged.
