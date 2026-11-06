# Design

Carry availability on PlannedFeature (also HTTP plan model) and operand feature
requests. Keep it outside indicator-specific params. Query the completed HTF
series at base open + base duration for bar_close; restore base row labels.
This includes a bucket closing exactly at that instant and excludes forming
buckets. Base-timeframe calculations are already based on their own closed bar.
Derived features inherit the dependency timing; explicit nondefault timing on
a dependency-bearing feature is rejected. Semantic identity and output labels
separate the two variants; default canonical payload/identity stays unchanged.

For B3S select bar_close on ATR inside at_point(peak), not on the whole B3S
expression. No future row lookup or universal shift is used.
