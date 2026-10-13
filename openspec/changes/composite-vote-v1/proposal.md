## Why

Research combines many atomic pre-entry components into one entry decision by weighted voting: each component may block an
entry on its own (veto) or add a weight to a sum that blocks the entry when it reaches a threshold. The Engine has atomic
operands (one number per bar, missing where it cannot be computed), `range` predicates and `composite_setup` with
`require` / `at_least k of n`, but no weights and no veto. Today a vote can only be replayed outside the Engine.

The owner asked on 2026-10-13 for a voting module in the Engine that is a pure executor: it plugs in any operand, present or
future, and takes every number (levels, weights, veto marks, block threshold) from the strategy spec. How the numbers were chosen
is not the Engine's business: the module knows no component by name, holds no default weight or threshold, and computes nothing
from history (no quantiles, no outcome statistics).

## What Changes

- **New setup component `composite_vote`.** It is an ordinary setup: its local mask is True where the entry is not blocked,
  and it is AND-composed with the other setups like `composite_setup`.
- **Members.** `params.members` is a list of voters. A member has one or more inputs:
  - an operand input: any operand the predicate layer accepts, a cut side (`low` or `high`) and a ladder of levels; each level
    is an absolute threshold with either a numeric weight or a veto mark;
  - a group input: `at_least k` of a list of predicates, with either a numeric weight or a veto mark.
- **Evaluation on each bar and side.**
  - An operand input fires the levels its value has crossed (`value ≤ at` for `low`, `value ≥ at` for `high`); the input
    takes the deepest fired level. A missing value fires nothing.
  - A group input fires when at least `k` of its predicates are True.
  - A member's weight is the maximum weight over its inputs; a member vetoes when any input's taken level or group is a veto.
  - The entry is blocked when any member vetoes or the sum of member weights is at least `params.block_at`.
- **Roles come from the data only.** A member whose levels are all veto marks is veto-only; one with numeric weights is a
  voter; both kinds in one ladder are allowed. A member is switched off by leaving it out.
- **Trace.** Per member: input values, taken level, weight, veto; per bar: the sum and the reason (`veto:<member_id>`, `sum`
  or none).
- **Cost and identity.** Operands are shared with every other user of the same operand node; the vote itself is vectorized
  and linear in bars × levels. Changing a weight, a level or `block_at` recomputes only the vote node.

Not in this change: any component, any calibration, default weights or thresholds, catalog and Research manifest bindings,
deploy. Long and short use the same members and numbers; the operands already carry the trade side.
