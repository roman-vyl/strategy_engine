## Decisions

### D1. A setup component, like `composite_setup`

- It produces a `SetupMask`, may declare `context_consumption`, and is AND-composed with the other setups.
- It is not a predicate class and not a composite child.
- Motivation:
  - the vote's result is a score with a reason, not a boolean;
  - a setup already has the composition and the evidence channel it needs.

### D2. Inputs reuse what exists

- An input is any operand accepted by `range` (feature, episode, segment, ratio, candle, leg mean, price) with `at_most` or
  `at_least`.
- An input can also be `count` of a list of predicates; this is how "k of n" groups vote.
- Motivation: every future filter becomes votable as soon as it exists as an operand. The vote itself never changes.

### D3. Everything numeric comes from the spec

- `threshold`, levels, weights and veto flags have no defaults.
- Motivation:
  - the numbers are chosen and reviewed by a person outside the Engine, and they change;
  - the Engine only executes them.

### D4. Input weight = largest weight among crossed steps

- Voter weight = largest among its inputs.
- Motivation:
  - one metric must count once, even if it is described by several variants or levels;
  - "largest" does not depend on the order of steps in the file;
  - on the usual ladder (wider → deeper, growing weight) it equals the deepest crossed step.

### D5. Veto is a step, not a separate mechanism

- A crossed veto step blocks the bar regardless of the score.
- The role `veto` means "veto steps only".
- Motivation: a voter can both vote softly at moderate levels and veto at extreme ones, in one ladder.

### D6. Block rule

- blocked = any veto, or Σ voter weights ≥ threshold. Plain comparison, with no tolerance.
- A missing input crosses no step.
- Motivation:
  - one simple rule;
  - "block on missing data" stays the job of a `range` with `empty: block`.

### D7. One table for both sides

- Inputs are side-aware through their operands. The steps and the threshold are shared by long and short.
- Motivation: no side-specific tuning.

### D8. Evidence, reuse, cost

- **Trace:**
  - `input:<id>:value`;
  - `voter:<id>:weight` and `voter:<id>:veto`;
  - `score`;
  - `blocked_by`: the first vetoing voter, else `score`, else null.
- **Reuse:** operands and predicates keep their predicate-layer identities, so they are shared with composites and between
  candidates. Candidates that differ only in the table compute each operand once.
- **Cost:** O(bars × steps) on top of the operands.
- **Plans:** feature and history plans as for composite children.
- **Unchanged:** specs without the setup are unchanged.
