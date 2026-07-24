"""Validate a Strategy Engine source tree or release ZIP."""

from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

_IGNORED_SOURCE_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
}
_FORBIDDEN_ARCHIVE_PARTS = _IGNORED_SOURCE_DIRS | {"dist"}
_REQUIRED_ARCHIVE_FILES = {
    "pyproject.toml",
    "src/strategy_engine/adapters/http/models.py",
    "tests/test_release_contract.py",
}


def _is_generated_package_file(path: PurePosixPath) -> bool:
    name = path.name
    return (
        name.endswith((".whl", ".tar.gz", ".tgz", ".pyc", ".pyo", ".zip"))
        or any(part.endswith(".egg-info") for part in path.parts)
    )


def _source_tree_violations(root: Path) -> list[str]:
    violations: list[str] = []
    for current, dir_names, file_names in os.walk(root):
        current_path = Path(current)
        relative_dir = current_path.relative_to(root)
        dir_names[:] = sorted(
            name for name in dir_names if name not in _IGNORED_SOURCE_DIRS
        )
        if relative_dir == Path(".") and "dist" in dir_names:
            violations.append("dist/")
            dir_names.remove("dist")
        for name in tuple(dir_names):
            if name.endswith(".egg-info"):
                violations.append((relative_dir / name).as_posix() + "/")
                dir_names.remove(name)
        for name in file_names:
            relative = relative_dir / name
            if name.endswith((".whl", ".tar.gz", ".tgz", ".pyc", ".pyo")):
                violations.append(relative.as_posix())
    return sorted(violations)


def _archive_violations(archive: Path) -> list[str]:
    violations: list[str] = []
    with ZipFile(archive) as package:
        bad_member = package.testzip()
        if bad_member is not None:
            violations.append(f"CRC failure: {bad_member}")

        files: set[str] = set()
        for member in package.infolist():
            path = PurePosixPath(member.filename)
            if path.is_absolute() or ".." in path.parts:
                violations.append(f"unsafe path: {member.filename}")
                continue
            if member.is_dir():
                continue
            files.add(path.as_posix())
            if any(
                part in _FORBIDDEN_ARCHIVE_PARTS for part in path.parts
            ) or _is_generated_package_file(path):
                violations.append(path.as_posix())

        for required in sorted(_REQUIRED_ARCHIVE_FILES - files):
            violations.append(f"missing required file: {required}")
    return sorted(violations)


def verify(path: Path) -> list[str]:
    if path.is_dir():
        return _source_tree_violations(path)
    if path.is_file() and path.suffix == ".zip":
        return _archive_violations(path)
    raise ValueError("target must be a source directory or ZIP archive")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()

    try:
        violations = verify(args.target.resolve())
    except (BadZipFile, OSError, ValueError) as exc:
        parser.error(str(exc))

    if violations:
        print("Release validation failed:")
        for violation in violations:
            print(f"- {violation}")
        return 1

    print(f"Release validation passed: {args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
