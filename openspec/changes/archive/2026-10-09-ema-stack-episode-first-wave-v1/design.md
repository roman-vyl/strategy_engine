## Context

`_project_long` keeps one forming wave (`s_bar`, `p_bar`, `d_low`, `d_high`) and resets it at the start bar and at every touch. At the start bar it is seeded by `reset_forming(start)`: the origin is the start bar itself, then the running minimum moves it down.

## D1 Candidate 2: the nearest left contact

For every bar `j` with a finite anchor, `contact[j] = low[j] ≤ anchor[j] ≤ high[j]`. The projection computes `latest_contact[t]`, the greatest `j ≤ t` with a contact, in one vectorized pass (`maximum.accumulate`). At a start bar `i` the candidate is `latest_contact[i−1]`, the nearest contact strictly left of `i`. There is no search bound: the candidate is the first contact found going left, down to the first bar with a finite anchor. A bar wholly above or wholly below the anchor, and a gap, is never a candidate. Using only bars left of `i` keeps the projection causal.

## D2 The fork

At the start bar, the origin is the candidate `j` when `low[j] < low[i]` (long), else the start bar. The test is strict, so the running minimum keeps ties. The short side is the mirror (`high[j] > high[i]`).

When `j` wins:

- the origin is `j` with the price `low[j]`;
- the peak is the first bar of the highest high over `[j, i]`, so it may be left of the start bar;
- the down leg runs from the peak, its low is the lowest low over `[peak, i]`, its high the peak high.

Bars between `j` and `i` are not origin candidates, even when their lows are lower than `low[j]`.

After the seed, the machine runs unchanged: a later low strictly below the origin price replaces the origin with that bar, exactly as the running minimum does today. So the origin of wave 1 is, at every bar, the lower of the left contact's low and the running minimum since the start (ties keep the earlier origin).

## D3 What does not change

The seed applies to wave 1 only. At every touch the forming wave is reset from the touch bar, so waves `k > 1` are as before. Zones, false breaks and stack breaks do not read the forming wave.

## D4 Versioning

The episode node version and `params_hash` are unchanged. The episode feature was merged on 2026-10-08 and the history route on 2026-10-09; no consumer cached or persisted wave 1 geometry. A later change of these results must bump the node version.

## Risks

- A long run of bars without contact left of the start (a strong trend) makes the candidate far from the start, so wave 1 can be long. The search bound can be revisited from data; the owner asked for no bound first.
- The Mac reference `counter_v6.py` does not implement this fork. Its parity for wave 1 must be rechecked with a reference that has the fork.
