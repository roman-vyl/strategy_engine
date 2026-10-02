## Context

Managed stop management today:

- `managed.py` (single-trade replay, live start-after-entry) computes
  each active stop rule's candidate price per bar, picks the tightest,
  and ratchets `active_stop_price` (seeded with the initial stop);
  the change is effective from bar N+1.
- The `HistoricalManagedProjection` carries a `stop_action` rule with a
  per-bar price offset from entry (`distance_id`); Research computes
  `entry ± distance` and runs the same ratchet.
- `mfe_r` (archived `mfe-r-phase-threshold-v1`) already freezes
  `initial_risk = |entry - initial_stop|` in both evaluators.

## Decisions

### D1. One component, two modes

`r_stop` with `params.mode`:

| mode  | params            | stop_R on bar N               |
|-------|-------------------|-------------------------------|
| lock  | `lock_r >= 0`     | `lock_r`                      |
| trail | `trail_r > 0`     | `MFE_R(N) - trail_r`          |

`stop price = entry + stop_R × initial_risk` (long),
`entry - stop_R × initial_risk` (short). For `trail` this is
`mfe_price ∓ trail_r × initial_risk`, where `mfe_price` is the best
price from the entry bar through bar N (the one `mfe_r` uses).

Both modes are one family: `lock` is `trail` with the MFE term frozen
out. A lock ladder (6R → 4R, 10R → 8R) is several `r_stop` lock rules on
successive phases.

### D2. Trigger stays a phase rule

`r_stop` has no trigger parameter. `activate_when.phase_at_least` with
a phase reached by `mfe_r >= trigger_R` is exactly today's BE@6R
lifecycle. A second trigger mechanism inside the stop would be the
parallel system this change avoids.

### D3. Monotonic and never looser than the initial stop

The candidate goes through the existing tightest-candidate selection
and ratchet. In addition, an `r_stop` candidate that is not tighter
than the initial stop is discarded. This matters only for `trail`
before `MFE_R > trail_r - 1`, and it keeps Engine (ratchet seeded with
the initial stop) and Research (ratchet seeded with no stop) in exact
agreement without touching existing components.

### D4. No initial risk, no stop

Without an initial stop, or with non-positive initial risk, `r_stop`
proposes no candidate on any bar (fail closed, as `mfe_r`). The HTTP
`/managed-replay` wire carries no initial stop, so `r_stop` never moves
the stop there; live start-after-entry uses the receipt stop.

### D5. `break_even_stop` stays as shorthand

`break_even_stop` code and wire are not changed. With
`buffer_type: none, buffer: 0` and an initial stop it yields the same
price as `r_stop{lock, 0}` on every bar (both `entry ± 0`); a test
proves equal trades. It is not rewritten onto `r_stop` because its
ATR and absolute-price buffers are not R quantities, and a rewrite
would change existing projection hashes for no behavioral gain.

### D6. Projection wire

`ManagedStopActionRule.stop_basis: Literal["lock_r", "trail_r"] | None`,
serialized only when not `None`. For `r_stop` the distance series is
`lock_r` or `trail_r` on every bar (constant, like `mfe_r` thresholds).
Consumer formula by `stop_basis`:

- absent: `entry ± distance` (unchanged);
- `lock_r`: `entry ± distance × initial_risk`;
- `trail_r`: `mfe_price ∓ distance × initial_risk`.

Research dispatches on `stop_basis`, never on `component_id`.

### D7. Execution unchanged

Next-bar effectiveness, same-bar priority (`stop_loss` before
`managed_stop`) and the level fill of the managed stop are reused as
they are.

## Risks

- **Stop beyond the market at activation.** The stop is computed from
  bar N's extreme and is effective from bar N+1. If bar N retraced past
  the new level, bar N+1 opens beyond the stop and, under the accepted
  level-fill model (`research-managed-policy-consumption-v1`, "Managed
  stop execution"), fills at the level, not at the open. BE@6R has the
  same property but needs a 6R retrace inside one bar; a 2R trail needs
  only a 2R retrace, so the optimism is larger. This change keeps the
  accepted model; the owner decides whether to change it.
- Float arithmetic: Engine computes in float, Research in float on the
  same inputs, then converts with `Decimal(str(.))` as for every other
  managed stop.
