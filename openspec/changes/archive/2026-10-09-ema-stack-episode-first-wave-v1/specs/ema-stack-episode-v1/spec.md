## MODIFIED Requirements

### Requirement: Wave geometry

Wave `k ≥ 1` is the move that ends at the touch of zone `k`. For the long side:

- the interval of wave `k > 1` SHALL run from the touch of zone `k−1` to the bar before the touch of zone `k`; its origin `S*_k` SHALL be the lowest low in the interval, the earliest bar on ties;
- the origin `S*_1` of wave 1 SHALL be the lower of two candidates, a tie going to the running lowest low:
  - the lowest low from the episode start bar to the bar before the touch of zone 1;
  - the low of the nearest bar left of the episode start bar whose range covers the anchor (`low ≤ anchor ≤ high` with a finite anchor), searched back without a bound; a bar wholly above or wholly below the anchor SHALL NOT be a candidate, and when no such bar exists the first candidate SHALL apply;
- the peak `P_k` SHALL be the highest high from the bar of `S*_k` to the bar before the touch of zone `k`, the earliest bar on ties; for wave 1 it MAY lie left of the episode start bar;
- up leg `k` SHALL be the range from the bar of `S*_k` to the bar of `P_k`;
- down leg `k` SHALL be the range from the bar of `P_k` to the touch bar of zone `k`.

The bars SHALL satisfy `bar(S*_k) ≤ bar(P_k) ≤ touch_k`. The same rule SHALL apply whether or not the interval contains a false break. The origin of wave 1 MAY precede the episode start bar. Only bars up to the current bar SHALL be read.

While the touch of zone `k` has not happened, wave `k` SHALL be forming:

- its origin SHALL be the running lowest low of the interval (for wave 1: the lower of that and the left contact low);
- its peak SHALL be the running highest high after that origin, reset whenever a new low is made;
- its down leg SHALL end on the current bar.

Wave `k` SHALL be final from the touch of zone `k`. A wave forming when the stack breaks SHALL stay non-final. A wave's `touch_price` SHALL be the low of the touch bar (short: the high). If touch 1 falls on the episode start bar, wave 1 SHALL NOT exist.

The short side SHALL mirror highs and lows, with leg ranges positive.

#### Scenario: Origin inside a false break

- **WHEN** after touch 2 a false break makes the lowest low of the interval and price then rallies to a peak before touch 3
- **THEN** wave 3's origin SHALL be that false-break low
- **AND** up leg 3 SHALL run from it to the peak.

#### Scenario: Peak before the false break is ignored

- **WHEN** the highest high of the interval occurs before its lowest low
- **THEN** `P_k` SHALL be the highest high after the lowest low
- **AND** `bar(S*_k) ≤ bar(P_k)` SHALL hold.

#### Scenario: Waves at the second touch

- **WHEN** zone 2 opens on bar `t`
- **THEN** wave 2 SHALL be final with `known_at` equal to `t`
- **AND** its down leg SHALL end on bar `t`.

#### Scenario: Pullback lower than every bar since the start

- **WHEN** the stack forms on bar `s`, the nearest anchor contact left of `s` is bar `j` with `low[j]` below every low since `s`, and the pullback before touch 1 makes a lower low than every bar since `s`
- **THEN** `S*_1` SHALL be bar `j`
- **AND** `P_1` SHALL be the highest high from `j` to the bar before touch 1
- **AND** up leg 1 SHALL NOT collapse to the pullback bar.

#### Scenario: Running minimum below the left contact

- **WHEN** a bar since the episode start has a lower low than the nearest left contact
- **THEN** `S*_1` SHALL be the lowest low since the episode start, as for any wave.

#### Scenario: No contact left of the start

- **WHEN** no bar left of the episode start bar covers the anchor
- **THEN** wave 1 SHALL be computed from the episode start bar only.

#### Scenario: Gap is not a contact

- **WHEN** the bars left of the start bar are wholly above or wholly below the anchor until an older contact bar
- **THEN** only that older contact bar SHALL be the candidate.
