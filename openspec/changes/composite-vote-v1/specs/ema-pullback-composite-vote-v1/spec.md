## ADDED Requirements

### Requirement: Ordinary setup at the outer boundary

`composite_vote` SHALL be a setup component that produces an ordinary `SetupMask`. Its local mask SHALL be True exactly where
the entry is not blocked by the vote. It MAY declare its own `context_consumption`, applied after the local mask as for any
other setup, and its final mask SHALL be AND-composed with the other declared setups by the existing setup composition.
`composite_vote` SHALL NOT be a child of `composite_setup` and SHALL NOT contain another `composite_vote`.

#### Scenario: Vote alongside other setups

- **WHEN** a spec declares a `composite_setup` and a `composite_vote`
- **THEN** `setups_ok` SHALL equal the AND of both final masks

### Requirement: Engine holds no voting numbers

The Engine SHALL NOT define any component-specific member, level, weight, veto mark or block threshold, and SHALL NOT derive
any of them from history, outcomes or quantiles. Every number used by a vote SHALL come from the spec.

#### Scenario: Same numbers, same decision

- **WHEN** two specs differ only in the order of members, of inputs or of levels within an input
- **THEN** their masks SHALL be equal on every bar

### Requirement: Vote shape

`params` SHALL contain `members` and `block_at`, and no other key. `block_at` SHALL be a finite number greater than 0, or
`null`. `members` SHALL be a non-empty list; each member SHALL have a `member_id` unique within the vote and not containing
`/`, and a non-empty list `inputs`, and no other key. Each input SHALL be exactly one operand input or one group input.

#### Scenario: Malformed vote

- **WHEN** a vote has duplicate `member_id`s, an empty `inputs`, an input with both `operand` and `group`, a non-positive
  `block_at` or an unknown key
- **THEN** static validation SHALL reject the spec

### Requirement: Operand input shape

An operand input SHALL be `{operand, side, levels}`. `operand` SHALL be any operand accepted by the predicate layer; `side`
SHALL be `low` or `high`; `levels` SHALL be a non-empty list of `{at, weight}` or `{at, veto: true}` with a finite `at`,
distinct `at` values within the input, and a finite non-negative `weight`.

#### Scenario: Any operand

- **WHEN** an operand input names any operand kind the predicate layer accepts, including one added after this change
- **THEN** the vote SHALL accept it without a change to the vote

#### Scenario: Malformed level

- **WHEN** a level has both `weight` and `veto`, neither, a negative or non-finite weight, or repeats an `at` of its input
- **THEN** static validation SHALL reject the spec

### Requirement: Group input shape

A group input SHALL be `{group: {at_least, of}}` with exactly one of `weight` (finite, not negative) or `veto: true`. `of`
SHALL be a non-empty list of predicates accepted by the predicate layer and `at_least` an integer with
`1 ≤ at_least ≤ len(of)`.

#### Scenario: Malformed group

- **WHEN** `at_least` is 0 or greater than the number of predicates
- **THEN** static validation SHALL reject the spec

### Requirement: Operand input evaluation

For an operand input on a bar with operand value `v`:

- a level SHALL fire iff `v` is finite and `v ≤ at` for side `low`, or `v ≥ at` for side `high`;
- the input weight SHALL be the maximum `weight` over fired levels, and 0 when no weighted level fired;
- the input SHALL veto iff any fired level carries the veto mark;
- the result SHALL NOT depend on the order of the levels.

#### Scenario: Largest fired weight is taken

- **WHEN** side is `low`, the levels are `{at: 0.8, weight: 0.2}` and `{at: 0.3, weight: 0.1}`, and `v` is 0.25
- **THEN** both levels SHALL fire and the input weight SHALL be 0.2

#### Scenario: Missing value is silent

- **WHEN** the operand value is missing on a bar
- **THEN** the input SHALL have weight 0 and no veto on that bar

#### Scenario: Inclusive threshold

- **WHEN** side is `high` and `v` equals a level's `at`
- **THEN** that level SHALL fire

### Requirement: Group input evaluation

A group input SHALL fire on a bar iff at least `at_least` of its predicates are True on that bar, with predicates evaluated by
the predicate layer unchanged. A fired group SHALL yield its `weight` or veto mark; a group that does not fire SHALL yield
weight 0 without veto.

#### Scenario: Two of three

- **WHEN** `at_least` is 2 and exactly two of three predicates are True
- **THEN** the group SHALL fire

### Requirement: Member and vote decision

On each bar and side:

- a member's weight SHALL be the maximum weight over its inputs, and the member SHALL veto iff any of its inputs yields a veto;
- the vote sum SHALL be the sum of member weights;
- the entry SHALL be blocked iff any member vetoes, or `block_at` is not null and the sum is greater than or equal to
  `block_at`.

#### Scenario: Veto alone

- **WHEN** one member vetoes and the sum is below `block_at`
- **THEN** the entry SHALL be blocked

#### Scenario: Sum reaches the threshold

- **WHEN** no member vetoes and the sum equals `block_at`
- **THEN** the entry SHALL be blocked

#### Scenario: Only vetoes

- **WHEN** `block_at` is null and no member vetoes
- **THEN** the entry SHALL pass whatever the sum

#### Scenario: Veto-only member

- **WHEN** every level of a member is a veto mark and none fires
- **THEN** the member SHALL add 0 to the sum

### Requirement: Member evidence

The vote `SetupMask.trace` SHALL contain per bar `member:<member_id>:weight` and `member:<member_id>:veto`; for operand
inputs `member:<member_id>/<input_index>:value` (null where missing) and `member:<member_id>/<input_index>:level` (the taken
`at`, null when none); for group inputs `member:<member_id>/<input_index>:count` (number of True predicates).

#### Scenario: Weighting level on the chart

- **WHEN** an operand input fires two levels on a bar
- **THEN** its `level` trace on that bar SHALL be the `at` of the fired level that gave the weight

### Requirement: Vote evidence

The trace SHALL contain per bar `vote:sum` and `vote:reason`: `veto:<member_id>` of the first vetoing member in declared
order, otherwise `sum` when blocked by the sum, otherwise null.

#### Scenario: Why was the entry blocked

- **WHEN** members `m1` and `m3` both veto on a bar
- **THEN** `vote:reason` SHALL be `veto:m1`

### Requirement: Side and determinism

The same members and numbers SHALL apply to both sides; side-specific behaviour SHALL come only from the operands and
predicates. The result on bar `t` SHALL depend only on operand and predicate values on bar `t`, and SHALL be identical in batch
and live evaluation of the same bars.

#### Scenario: No lookahead

- **WHEN** bars after `t` change
- **THEN** the vote mask and trace on `t` SHALL be unchanged

### Requirement: Identity, sharing and cost

Each operand input and each group predicate SHALL resolve to the existing operand or predicate node, shared with every other
user of the same identity in the evaluation context. The vote node SHALL carry the canonical params as its identity; labels
SHALL NOT change operand or predicate identities. The vote SHALL add only vectorized work linear in bars × (levels + group
predicates). A spec without `composite_vote` SHALL have the same node set and results as before this change.

#### Scenario: Candidates differing only in numbers

- **WHEN** a batch contains candidates whose votes differ only in weights, levels or `block_at`
- **THEN** every operand and predicate node SHALL be computed once per batch per side

#### Scenario: No compute regression

- **WHEN** a spec has no `composite_vote`
- **THEN** no vote node SHALL be created
