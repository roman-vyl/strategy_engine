## Why

Research metric **C3.2 "how many times deeper this pullback is than the previous one"** (group C of the almanac): C3.1 of the
current touch divided by the same depth share of the previous pullback of the same episode.

In **vote B** for EMA200 it is a veto at C3.2 ≥ 3.43 (threshold set by the owner). On the working zones it cuts 1 BTC entry (a stop),
none on ETH and SOL; on all entries 18 / 5 / 7. Reviewed with the owner on 2026-10-22: a broken trend rhythm, earlier pullbacks were
shallow and this one falls through.

## What Changes

- **`pullback_depth` gains an optional `touch`** field, `current` (default, C3.1 unchanged) or `previous`:
  - `previous`, on a bar `t` whose current touch has a valid wave and is not the first of its episode:
    `g · (P0_price − ext0) / |P0_price − S0_price|`, with `S0`, `P0` the origin and peak of the previous touch row and `ext0` the
    lowest low (long) or highest high (short) of the bars `[P0, S*]`, `S*` the origin of the current touch.
  - Missing on the first touch of an episode, when `S* ≤ P0`, the previous impulse height is 0 or a price of `[P0, S*]` is not finite.
- **C3.2** is `ratio(pullback_depth(current), pullback_depth(previous), right_floor 1e-6)`; vote B puts `3.43 → veto` and the floor
  into its config. The Engine holds no threshold.
- **Identity**: `touch` is part of the node params only when `previous`, so existing C3.1 specs keep their node identity.

Not in this change: the other vote B components, catalog and manifest bindings, deploy.
