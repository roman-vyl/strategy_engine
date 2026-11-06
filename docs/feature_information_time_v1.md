# Feature availability

A feature request may specify `availability: "bar_close"` alongside kind,
timeframe, source and params. The default is `"bar_open"`, preserving historical
completed HTF reads. Close means the close of the selected base candle, not
the end of a still-forming HTF bucket. Native base features retain their normal
closed-candle calculation. Derived features inherit their dependency timing.

B3S uses:

```json
{"at_point":{"episode":"trend","point":"peak","operand":{"feature":{
  "kind":"atr_wilder","timeframe":"4h","params":{"period":14},
  "availability":"bar_close"
}}}}
```

Both feature variants can coexist. Their output labels, canonical payloads and
cache identities differ. Existing requests retain original labels and hashes.
