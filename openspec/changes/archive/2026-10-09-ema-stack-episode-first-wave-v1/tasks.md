## 1. Implementation

- [x] 1.1 Nearest left anchor contact from one vectorized pass
- [x] 1.2 Seed wave 1 with the lower of the running minimum and the left contact (long; short by mirror)

## 2. Tests

- [x] 2.1 Collapsing leg: origin on the left contact, peak left of the start bar, touch 1 (long and short)
- [x] 2.2 Running minimum lower than the left contact keeps the old origin
- [x] 2.3 No left contact: wave 1 unchanged
- [x] 2.4 Wave 2 origin is unchanged
- [x] 2.5 Approved drawing: wave 1 origin on the left contact bar
- [x] 2.6 ruff, mypy, full suite without `tests/parity`, `openspec validate --strict`

## 3. Parity and gate

- [x] 3.1 Mac dev Engine (6174ccf) against the previous Engine, BTC 5m full history (500/1000/2000, window 48, break 12, 213 episodes): zones, false breaks, stack breaks and waves from the second are identical; degenerate first waves 63 long and 52 short before, 0 and 1 after. A reference with the fork for counter_v6.py was not built
- [x] 3.2 Example `ema_pullback:163782b777c0c4d8cd38c79c` trade 6: S* 2026-07-14 12:30 (62923.1), P 2026-07-15 15:50 (65566.6), touch 2026-07-16 07:40; owner checked it visually: no remarks
