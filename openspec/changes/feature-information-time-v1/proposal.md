# Feature information time

B3S reads ATR14 4h at the close of episode peak P. Existing completed HTF
features are aligned to base candle opens, delaying the newly closed bucket
by one base row. Other researched formulas intentionally use the older value.

Add explicit generic feature `availability: bar_open | bar_close`, default
bar_open. At bar_close query completed HTF values at open + base duration,
without reading a following base row. Keep existing feature identities and
hashes unchanged by default. Close availability has separate labels/identity.
No change to ATR mathematics, episode discovery, voting weights or execution.
