"""Canonical, bit-exact encoding of evaluator outputs.

`encode()` turns any evaluator output (frozen dataclasses, tuples, dicts,
numpy arrays, floats, Decimals, ...) into a JSON-able tree whose leaves are
either exact scalars or references into a content-addressed `ArrayStore`:

- float64 values are never stored as Python float reprs. Scalars are the
  8 raw little-endian IEEE-754 bytes (hex); sequences are float64 numpy
  arrays whose `.tobytes()` is what gets compared (NaN payloads included).
- `None` inside a float sequence is kept distinct from NaN via a separate
  boolean "none" position mask.
- bool / int / str sequences become bool / int64 / categorical arrays.
- Decimals are kept as `str(Decimal)` (exponent/representation preserved).

Container type (tuple vs list vs ndarray) is deliberately NOT recorded:
design.md allows representation-equivalent output changes (e.g. float tuple
-> float64 array) as long as element semantics are bit-identical.

Arrays are keyed by sha256(kind, dtype, shape, bytes), so identical series
shared by many candidates (indicators, masks) are stored once.
"""

from __future__ import annotations

import dataclasses
import gzip
import hashlib
import json
import struct
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np

FORMAT_VERSION = 1


def f64_hex(value: float) -> str:
    return struct.pack("<d", float(value)).hex()


def hex_f64(text: str) -> float:
    return float(struct.unpack("<d", bytes.fromhex(text))[0])


class ArrayStore:
    """Content-addressed array store (sha256 of kind/dtype/shape/bytes)."""

    def __init__(self, arrays: dict[str, np.ndarray] | None = None) -> None:
        self.arrays: dict[str, np.ndarray] = dict(arrays or {})

    @staticmethod
    def key_for(kind: str, array: np.ndarray) -> str:
        digest = hashlib.sha256()
        digest.update(kind.encode())
        digest.update(array.dtype.str.encode())
        digest.update(repr(array.shape).encode())
        digest.update(array.tobytes())
        return f"{kind}-{digest.hexdigest()[:40]}"

    def put(self, kind: str, array: np.ndarray) -> str:
        array = np.ascontiguousarray(array)
        key = self.key_for(kind, array)
        self.arrays.setdefault(key, array)
        return key

    def get(self, key: str) -> np.ndarray:
        return self.arrays[key]

    def update(self, other: ArrayStore) -> None:
        for key, value in other.arrays.items():
            self.arrays.setdefault(key, value)

    def save(self, path: Path) -> None:
        np.savez_compressed(path, **self.arrays)

    @classmethod
    def load(cls, path: Path, *, verify: bool = True) -> ArrayStore:
        with np.load(path, allow_pickle=False) as data:
            arrays = {key: data[key] for key in data.files}
        store = cls(arrays)
        if verify:
            for key, array in arrays.items():
                kind = key.split("-", 1)[0]
                if cls.key_for(kind, array) != key:
                    raise ValueError(f"golden array store corrupted at {key}")
        return store


def _is_bool(value: object) -> bool:
    return isinstance(value, (bool, np.bool_))


def _is_float(value: object) -> bool:
    return isinstance(value, (float, np.floating))


def _is_int(value: object) -> bool:
    return isinstance(value, (int, np.integer)) and not _is_bool(value)


def _encode_ndarray(array: np.ndarray, store: ArrayStore) -> Any:
    if array.dtype == np.bool_:
        return {"bool": store.put("bool", array.astype(np.bool_))}
    if np.issubdtype(array.dtype, np.floating):
        return {"f64": store.put("f64", array.astype(np.float64)), "none": None}
    if np.issubdtype(array.dtype, np.integer):
        return {"i64": store.put("i64", array.astype(np.int64))}
    return _encode_sequence(list(array.tolist()), store)


def _encode_sequence(items: list[Any], store: ArrayStore) -> Any:
    if not items:
        return {"seq": []}
    if all(_is_bool(item) for item in items):
        return {"bool": store.put("bool", np.asarray(items, dtype=np.bool_))}
    if all(item is None or _is_float(item) for item in items) and any(
        _is_float(item) for item in items
    ):
        none_mask = np.fromiter((item is None for item in items), dtype=np.bool_, count=len(items))
        values = np.fromiter(
            (np.nan if item is None else float(item) for item in items),
            dtype=np.float64,
            count=len(items),
        )
        return {
            "f64": store.put("f64", values),
            "none": store.put("bool", none_mask) if none_mask.any() else None,
        }
    if all(_is_int(item) for item in items) and all(
        -(2**63) <= int(item) < 2**63 for item in items
    ):
        return {"i64": store.put("i64", np.asarray([int(item) for item in items], dtype=np.int64))}
    if all(isinstance(item, str) for item in items):
        levels: dict[str, int] = {}
        codes = np.fromiter(
            (levels.setdefault(item, len(levels)) for item in items),
            dtype=np.int32,
            count=len(items),
        )
        return {"str": {"levels": list(levels), "codes": store.put("i32", codes)}}
    if all(item is None for item in items):
        return {"nones": len(items)}
    return {"seq": [encode(item, store) for item in items]}


def encode(value: Any, store: ArrayStore) -> Any:
    """Canonical encoding; raises TypeError on anything unrecognized so a
    new output type can never be silently skipped."""

    if value is None or isinstance(value, str):
        return value
    if _is_bool(value):
        return bool(value)
    if _is_int(value):
        return int(value)
    if _is_float(value):
        return {"f": f64_hex(float(value))}
    if isinstance(value, Decimal):
        return {"dec": str(value)}
    if isinstance(value, np.ndarray):
        return _encode_ndarray(value, store)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            "dc": type(value).__qualname__,
            "v": {
                field.name: encode(getattr(value, field.name), store)
                for field in dataclasses.fields(value)
            },
        }
    if isinstance(value, Mapping):
        return {"map": [[encode(key, store), encode(item, store)] for key, item in value.items()]}
    if isinstance(value, (tuple, list)):
        return _encode_sequence(list(value), store)
    raise TypeError(f"parity snapshot cannot encode {type(value).__module__}.{type(value)!r}")


# -- golden I/O ------------------------------------------------------------


def write_json_gz(path: Path, payload: Any) -> None:
    raw = json.dumps(payload, sort_keys=False, separators=(",", ":")).encode("utf-8")
    path.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))


def read_json_gz(path: Path) -> Any:
    return json.loads(gzip.decompress(path.read_bytes()))
