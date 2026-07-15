# EMA Pullback setups v1

The independent engine now owns the three setup implementations used by the current BBB strategy:

- `untouched_anchor_setup`;
- `ema_bounce_counter_setup`;
- `anchor_stack_width_setup`.

The range pipeline now ends at:

```text
direction AND blockers
→ pre_setup_allowed
→ all setup rules, each optionally context-gated
→ setups_ok
→ pre_trigger_allowed
```

`pre_trigger_allowed` is not an entry. Trigger and risk stages remain unported.

The stateful bounce counter is replayed sequentially inside one range request. This preserves the future conceptual seam for a bar-to-bar runtime wrapper without introducing a network request per bar.
