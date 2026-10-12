"""Range maximum and minimum by a sparse table (shared by the segment and candle operands)."""

from __future__ import annotations

import numpy as np


def window_extreme(
    values: np.ndarray, low: np.ndarray, high: np.ndarray, largest: bool
) -> np.ndarray:
    """max / min of `values[low..high]` per query by a sparse table whose
    depth is bounded by the longest window: O(n log n) build, O(1) per query."""

    reduce = np.maximum if largest else np.minimum
    length = high - low + 1
    depth = int(np.log2(length.max())) if len(length) else 0
    levels = [values]
    for j in range(1, depth + 1):
        previous = levels[-1]
        half = 1 << (j - 1)
        levels.append(reduce(previous[:-half], previous[half:]))
    level = np.floor(np.log2(length)).astype(np.int64)
    out = np.empty(len(low))
    for j in np.unique(level):
        pick = level == j
        table = levels[int(j)]
        out[pick] = reduce(table[low[pick]], table[high[pick] - (1 << int(j)) + 1])
    return out
