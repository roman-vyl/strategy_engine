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

- [ ] 3.1 Mac: reference with the same fork, full history BTC and ETH, both sides, wave 1 only; the other entities equal to before
- [ ] 3.2 Example `ema_pullback:163782b777c0c4d8cd38c79c` trade 6 shows the long leg
