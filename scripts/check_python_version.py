"""Fail fast when Strategy Engine uses an unsupported Python interpreter."""

from __future__ import annotations

import sys

MINIMUM_PYTHON = (3, 12)


def main() -> None:
    current = sys.version_info[:2]
    if current < MINIMUM_PYTHON:
        required = ".".join(str(part) for part in MINIMUM_PYTHON)
        raise SystemExit(
            f"Strategy Engine requires Python {required}+, got {sys.version.split()[0]}"
        )


if __name__ == "__main__":
    main()
