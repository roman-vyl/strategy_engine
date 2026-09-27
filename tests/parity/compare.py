"""Parity comparison rules (OpenSpec `batch-computation-reuse`, task 1.5).

Strategy Engine intermediates / projection / NDJSON: bit-exact.

- float64: `.tobytes()` equality (never `==` / `np.isclose`), after first
  checking None-position and NaN-position masks so drift is reported by
  its most specific cause.
- bool / int / categorical-string sequences: exact.
- failures: category (exception type) + code + message + payload/details +
  evaluation-sequence position (variant index, variant id, stage path) +
  caught-vs-propagated disposition. Never Python exception object identity
  or traceback identity (neither is recorded).
- NDJSON: exact bytes per line, same line count, same stream termination.

Downstream Research Service artifacts (design.md D7): semantic-content
equality after excluding non-deterministic metadata -- see
`compare_research_artifacts_semantic` (interface for task 5.4).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from parity.snapshot import ArrayStore, hex_f64


@dataclass(frozen=True, slots=True)
class Mismatch:
    path: str
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.rule}] {self.path}: {self.detail}"


def _indices(mask: np.ndarray, limit: int = 5) -> list[int]:
    return [int(index) for index in np.flatnonzero(mask)[:limit]]


def _f64_repr(value: float) -> str:
    return f"{value!r} (0x{np.float64(value).tobytes()[::-1].hex()})"


# -- array / scalar rules --------------------------------------------------


def compare_missing_positions(
    path: str, golden: np.ndarray, actual: np.ndarray, *, what: str
) -> list[Mismatch]:
    """Positions of None (or NaN) must match exactly, not just values."""

    if golden.shape != actual.shape:
        return [Mismatch(path, f"{what}-positions", f"shape {golden.shape} != {actual.shape}")]
    differ = golden != actual
    if not differ.any():
        return []
    return [
        Mismatch(
            path,
            f"{what}-positions",
            f"{int(differ.sum())} bar(s) differ in {what} position; first at "
            f"{_indices(differ)} (golden {what}={golden[differ][:5].tolist()}, "
            f"actual {what}={actual[differ][:5].tolist()})",
        )
    ]


def compare_float64_bitwise(
    path: str,
    golden: np.ndarray,
    actual: np.ndarray,
    *,
    golden_none: np.ndarray | None = None,
    actual_none: np.ndarray | None = None,
) -> list[Mismatch]:
    """Bitwise float64 comparison via `.tobytes()` (never `==`/isclose)."""

    golden = np.ascontiguousarray(golden, dtype=np.float64)
    actual = np.ascontiguousarray(actual, dtype=np.float64)
    if golden.shape != actual.shape:
        return [Mismatch(path, "float64-bitwise", f"length {golden.shape} != {actual.shape}")]
    empty = np.zeros(golden.shape, dtype=np.bool_)
    none_mismatch = compare_missing_positions(
        path,
        empty if golden_none is None else golden_none,
        empty if actual_none is None else actual_none,
        what="None",
    )
    if none_mismatch:
        return none_mismatch
    nan_mismatch = compare_missing_positions(path, np.isnan(golden), np.isnan(actual), what="NaN")
    if nan_mismatch:
        return nan_mismatch
    if golden.tobytes() == actual.tobytes():
        return []
    golden_bits = golden.view(np.uint64)
    actual_bits = actual.view(np.uint64)
    differ = golden_bits != actual_bits
    first = int(np.flatnonzero(differ)[0])
    finite = differ & np.isfinite(golden) & np.isfinite(actual)
    max_abs = float(np.max(np.abs(golden[finite] - actual[finite]))) if finite.any() else 0.0
    return [
        Mismatch(
            path,
            "float64-bitwise",
            f"{int(differ.sum())}/{golden.size} value(s) not bit-identical; first at "
            f"bar {first}: golden={_f64_repr(float(golden[first]))} "
            f"actual={_f64_repr(float(actual[first]))}; max |diff|={max_abs!r}",
        )
    ]


def compare_bool_exact(path: str, golden: np.ndarray, actual: np.ndarray) -> list[Mismatch]:
    if golden.shape != actual.shape:
        return [Mismatch(path, "bool-exact", f"length {golden.shape} != {actual.shape}")]
    differ = golden.astype(np.bool_) != actual.astype(np.bool_)
    if not differ.any():
        return []
    return [
        Mismatch(
            path,
            "bool-exact",
            f"{int(differ.sum())}/{golden.size} bar(s) differ "
            f"(golden True={int(golden.sum())}, actual True={int(actual.sum())}); "
            f"first at {_indices(differ)}",
        )
    ]


def compare_int_exact(path: str, golden: np.ndarray, actual: np.ndarray) -> list[Mismatch]:
    if golden.shape != actual.shape:
        return [Mismatch(path, "int-exact", f"length {golden.shape} != {actual.shape}")]
    differ = golden != actual
    if not differ.any():
        return []
    first = int(np.flatnonzero(differ)[0])
    return [
        Mismatch(
            path,
            "int-exact",
            f"{int(differ.sum())} value(s) differ; first at {first}: "
            f"golden={int(golden[first])} actual={int(actual[first])}",
        )
    ]


# -- structural walker over snapshot encodings ------------------------------


def _describe(node: Any) -> str:
    if isinstance(node, dict):
        if "f" in node:
            return _f64_repr(hex_f64(node["f"]))
        return "{" + ",".join(sorted(node)) + "}"
    text = repr(node)
    return text if len(text) <= 120 else text[:117] + "..."


def _node_kind(node: Any) -> str:
    if isinstance(node, dict):
        for key in ("f", "dec", "dc", "map", "seq", "bool", "f64", "i64", "str", "nones"):
            if key in node:
                return key
        return "dict?"
    if node is None:
        return "None"
    return type(node).__name__


def _map_key_label(key: Any) -> str:
    if isinstance(key, str):
        return repr(key)
    return _describe(key)


def compare_encoded(
    path: str,
    golden: Any,
    actual: Any,
    golden_store: ArrayStore,
    actual_store: ArrayStore,
) -> list[Mismatch]:
    """Walk two `snapshot.encode` trees and apply the per-leaf rules."""

    golden_kind = _node_kind(golden)
    actual_kind = _node_kind(actual)
    if golden_kind != actual_kind:
        # A float sequence with no finite element can legitimately only be
        # a None-run on one side; still a mismatch, reported structurally.
        return [
            Mismatch(
                path,
                "structure",
                f"kind {golden_kind} != {actual_kind} "
                f"(golden={_describe(golden)}, actual={_describe(actual)})",
            )
        ]
    if not isinstance(golden, dict):
        if golden != actual or type(golden) is not type(actual):
            return [Mismatch(path, "scalar-exact", f"golden={golden!r} actual={actual!r}")]
        return []
    if golden_kind == "f":
        if golden["f"] != actual["f"]:
            return [
                Mismatch(
                    path,
                    "float64-bitwise",
                    f"golden={_describe(golden)} actual={_describe(actual)}",
                )
            ]
        return []
    if golden_kind == "dec":
        if golden["dec"] != actual["dec"]:
            return [Mismatch(path, "decimal-exact", f"{golden['dec']} != {actual['dec']}")]
        return []
    if golden_kind == "nones":
        if golden["nones"] != actual["nones"]:
            return [Mismatch(path, "None-positions", f"{golden['nones']} != {actual['nones']}")]
        return []
    if golden_kind == "bool":
        return compare_bool_exact(
            path, golden_store.get(golden["bool"]), actual_store.get(actual["bool"])
        )
    if golden_kind == "i64":
        return compare_int_exact(
            path, golden_store.get(golden["i64"]), actual_store.get(actual["i64"])
        )
    if golden_kind == "f64":
        golden_none = golden_store.get(golden["none"]) if golden.get("none") else None
        actual_none = actual_store.get(actual["none"]) if actual.get("none") else None
        return compare_float64_bitwise(
            path,
            golden_store.get(golden["f64"]),
            actual_store.get(actual["f64"]),
            golden_none=golden_none,
            actual_none=actual_none,
        )
    if golden_kind == "str":
        golden_values = np.asarray(golden["str"]["levels"], dtype=object)[
            golden_store.get(golden["str"]["codes"])
        ]
        actual_values = np.asarray(actual["str"]["levels"], dtype=object)[
            actual_store.get(actual["str"]["codes"])
        ]
        if golden_values.shape != actual_values.shape:
            return [
                Mismatch(
                    path, "str-exact", f"length {golden_values.shape} != {actual_values.shape}"
                )
            ]
        differ = golden_values != actual_values
        if differ.any():
            first = int(np.flatnonzero(differ)[0])
            return [
                Mismatch(
                    path,
                    "str-exact",
                    f"{int(differ.sum())} value(s) differ; first at {first}: "
                    f"golden={golden_values[first]!r} actual={actual_values[first]!r}",
                )
            ]
        return []
    if golden_kind == "dc":
        if golden["dc"] != actual["dc"]:
            return [Mismatch(path, "structure", f"type {golden['dc']} != {actual['dc']}")]
        mismatches: list[Mismatch] = []
        golden_fields, actual_fields = golden["v"], actual["v"]
        if list(golden_fields) != list(actual_fields):
            return [
                Mismatch(
                    path, "structure", f"fields {list(golden_fields)} != {list(actual_fields)}"
                )
            ]
        for name in golden_fields:
            mismatches += compare_encoded(
                f"{path}.{name}",
                golden_fields[name],
                actual_fields[name],
                golden_store,
                actual_store,
            )
        return mismatches
    if golden_kind == "map":
        golden_keys = [json_key(key) for key, _ in golden["map"]]
        actual_keys = [json_key(key) for key, _ in actual["map"]]
        if golden_keys != actual_keys:
            return [
                Mismatch(
                    path,
                    "structure",
                    f"mapping keys/order {golden_keys} != {actual_keys}",
                )
            ]
        mismatches = []
        for (key, golden_value), (_, actual_value) in zip(
            golden["map"], actual["map"], strict=True
        ):
            mismatches += compare_encoded(
                f"{path}[{_map_key_label(key)}]",
                golden_value,
                actual_value,
                golden_store,
                actual_store,
            )
        return mismatches
    if golden_kind == "seq":
        if len(golden["seq"]) != len(actual["seq"]):
            return [
                Mismatch(path, "structure", f"length {len(golden['seq'])} != {len(actual['seq'])}")
            ]
        mismatches = []
        for index, (golden_item, actual_item) in enumerate(
            zip(golden["seq"], actual["seq"], strict=True)
        ):
            mismatches += compare_encoded(
                f"{path}[{index}]", golden_item, actual_item, golden_store, actual_store
            )
        return mismatches
    return [Mismatch(path, "structure", f"unknown encoded node {golden!r}")]


def json_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


# -- failures ---------------------------------------------------------------

FAILURE_FIELDS = (
    "disposition",  # "ok" | "caught" | "propagated"
    "category",  # exception type, module-qualified
    "code",  # StrategyEngineError.code (None otherwise)
    "message",
    "details",  # encoded payload
    "variant_index",
    "variant_id",
    "stage",  # evaluation-sequence position inside the candidate
)


def compare_failure(
    path: str, golden: Mapping[str, Any], actual: Mapping[str, Any]
) -> list[Mismatch]:
    """Failure parity: category + message/payload + sequence position +
    caught-vs-propagated. Exception object / traceback identity is never
    recorded, so it can never be (wrongly) required."""

    mismatches = []
    for name in FAILURE_FIELDS:
        if golden.get(name) != actual.get(name):
            mismatches.append(
                Mismatch(
                    f"{path}.{name}",
                    "failure",
                    f"golden={golden.get(name)!r} actual={actual.get(name)!r}",
                )
            )
    return mismatches


# -- NDJSON -----------------------------------------------------------------


def compare_ndjson(
    path: str, golden: Mapping[str, Any], actual: Mapping[str, Any]
) -> list[Mismatch]:
    mismatches: list[Mismatch] = []
    golden_lines: list[str] = golden["lines"]
    actual_lines: list[str] = actual["lines"]
    if len(golden_lines) != len(actual_lines):
        mismatches.append(
            Mismatch(path, "ndjson-bytes", f"line count {len(golden_lines)} != {len(actual_lines)}")
        )
    for index, (golden_line, actual_line) in enumerate(
        zip(golden_lines, actual_lines, strict=False)
    ):
        golden_bytes = golden_line.encode("utf-8")
        actual_bytes = actual_line.encode("utf-8")
        if golden_bytes != actual_bytes:
            first = next(
                (
                    offset
                    for offset, (left, right) in enumerate(
                        zip(golden_bytes, actual_bytes, strict=False)
                    )
                    if left != right
                ),
                min(len(golden_bytes), len(actual_bytes)),
            )
            window = slice(max(0, first - 60), first + 60)
            mismatches.append(
                Mismatch(
                    f"{path}.line[{index}]",
                    "ndjson-bytes",
                    f"first differing byte at offset {first} "
                    f"(len {len(golden_bytes)} vs {len(actual_bytes)}): "
                    f"golden=...{golden_bytes[window]!r}... actual=...{actual_bytes[window]!r}...",
                )
            )
    if golden["termination"] != actual["termination"]:
        mismatches.append(
            Mismatch(
                f"{path}.termination",
                "failure",
                f"golden={golden['termination']!r} actual={actual['termination']!r}",
            )
        )
    return mismatches


# -- whole case -------------------------------------------------------------


def compare_case(
    golden: Mapping[str, Any],
    actual: Mapping[str, Any],
    golden_store: ArrayStore,
    actual_store: ArrayStore,
) -> list[Mismatch]:
    """Compare one recorded batch case (see `harness.record_case`)."""

    name = golden["case"]
    mismatches: list[Mismatch] = []
    if golden["request_payload"] != actual["request_payload"]:
        mismatches.append(Mismatch(name, "input", "request payload differs from golden"))
        return mismatches
    mismatches += compare_ndjson(f"{name}.ndjson", golden["ndjson"], actual["ndjson"])
    golden_candidates = golden["candidates"]
    actual_candidates = actual["candidates"]
    if len(golden_candidates) != len(actual_candidates):
        mismatches.append(
            Mismatch(
                f"{name}.candidates",
                "structure",
                f"evaluated candidate count {len(golden_candidates)} != {len(actual_candidates)}",
            )
        )
    for golden_candidate, actual_candidate in zip(
        golden_candidates, actual_candidates, strict=False
    ):
        where = f"{name}.variant[{golden_candidate['variant_index']}]" + (
            f"={golden_candidate['variant_id']}"
        )
        mismatches += compare_failure(
            f"{where}.outcome", golden_candidate["outcome"], actual_candidate["outcome"]
        )
        for section in ("plan", "frame", "evaluation", "projection"):
            mismatches += compare_encoded(
                f"{where}.{section}",
                golden_candidate[section],
                actual_candidate[section],
                golden_store,
                actual_store,
            )
    return mismatches


def format_report(mismatches: Iterable[Mismatch], *, limit: int = 40) -> str:
    items = list(mismatches)
    lines = [f"{len(items)} parity mismatch(es):"]
    lines += [f"  {item}" for item in items[:limit]]
    if len(items) > limit:
        lines.append(f"  ... {len(items) - limit} more")
    return "\n".join(lines)


# -- downstream Research Service artifacts (design.md D7; used by task 5.4) --

NON_DETERMINISTIC_ARTIFACT_FIELDS: frozenset[str] = frozenset(
    {
        "run_id",
        "artifact_path",
        "created_at",
        "created_at_utc",
        "started_at_utc",
        "completed_at_utc",
        "finished_at_utc",
        "updated_at_utc",
    }
)


def compare_research_artifacts_semantic(
    golden: Any,
    actual: Any,
    *,
    exclude_fields: frozenset[str] = NON_DETERMINISTIC_ARTIFACT_FIELDS,
    exclude: Callable[[str, str], bool] | None = None,
    path: str = "artifact",
) -> list[Mismatch]:
    """Semantic-content equality of persisted Research Service artifacts
    (trades, fills, fees, PnL, cumulative R, metrics, provenance such as
    market-data/config hashes) after dropping non-deterministic metadata
    keys, at any depth. Never a byte-identical full-artifact comparison.

    Interface defined in task 1.5; exercised end to end by task 5.4, which
    is expected to extend `exclude_fields` / pass `exclude(path, key)` for
    artifact-specific fields once real pre/post-change runs exist.
    """

    def dropped(key: str) -> bool:
        return key in exclude_fields or (exclude is not None and exclude(path, key))

    if isinstance(golden, Mapping) and isinstance(actual, Mapping):
        golden_keys = {key for key in golden if not dropped(str(key))}
        actual_keys = {key for key in actual if not dropped(str(key))}
        mismatches: list[Mismatch] = []
        if golden_keys != actual_keys:
            mismatches.append(
                Mismatch(
                    path,
                    "artifact-semantic",
                    f"keys only in golden={sorted(map(str, golden_keys - actual_keys))} "
                    f"only in actual={sorted(map(str, actual_keys - golden_keys))}",
                )
            )
        for key in sorted(golden_keys & actual_keys, key=str):
            mismatches += compare_research_artifacts_semantic(
                golden[key],
                actual[key],
                exclude_fields=exclude_fields,
                exclude=exclude,
                path=f"{path}.{key}",
            )
        return mismatches
    if isinstance(golden, list) and isinstance(actual, list):
        if len(golden) != len(actual):
            return [Mismatch(path, "artifact-semantic", f"length {len(golden)} != {len(actual)}")]
        mismatches = []
        for index, (golden_item, actual_item) in enumerate(zip(golden, actual, strict=True)):
            mismatches += compare_research_artifacts_semantic(
                golden_item,
                actual_item,
                exclude_fields=exclude_fields,
                exclude=exclude,
                path=f"{path}[{index}]",
            )
        return mismatches
    if type(golden) is not type(actual) or golden != actual:
        return [Mismatch(path, "artifact-semantic", f"golden={golden!r} actual={actual!r}")]
    return []
