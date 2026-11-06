## Context

See proposal.md. Inspected local Engine: `indicators/implementations/rsi.py` explicitly implements rolling means and rejects extra parameters. `ema_pullback/predicates.py` already supports `segment.touch=previous`, `peak→next_origin`, same-episode previous-row selection, level sum/mean, and min/max for from_start. `window_extreme.py` supplies efficient range extrema. Current level segments include both endpoints. The missing behavior is not a new episode model.

Reference: Research Service `research/c6r_wave_memory/build.py` independently checks frozen `HIST:c6r` against RSI168 recursive values. Authoritative original calculation must additionally be checked in `/Users/mcroma/BBB_data/tmp/v3e200_20261020/code/altvals.py`. Frozen inputs: three stage0 studies' `inputs/feature_values.npz`, entry labels, entry CSVs and recovered MDS snapshots. Paths are acceptance inputs only, never runtime dependencies.

## Goals / Non-Goals

Goals: exact original C6 on identical market history and episode points; reusable indicator and segment primitives; preserve entry candle and causality; executable manifest example.
Non-goals: experimental relative retracement RSI, adapting RSI periods, new voting parameters, filter selection, ATR4h/B3S, spot/perp, live deployment.

## Decisions

### Separate feature kind

Use `rsi_ewm`, parameters `{period:168}`, source close, no dependencies. Existing `rsi` remains rolling and unchanged. A smoothing option on existing rsi was considered but conflicts with its strict single-parameter contract and creates accidental migration/cache risks. A period-generic RSI variant is not a C6-specific feature.

For full input prefix starting at k0: delta[k0]=0, U[k0]=D[k0]=0; for t>k0, delta=close[t]-close[t-1], U=(1-1/N)Uprev+max(delta,0)/N, D=(1-1/N)Dprev+max(-delta,0)/N. RSI=100*U/(U+D). Both zero => missing, U>0,D=0 =>100, U=0,D>0 =>0. No simple-mean seed, no RSI50 substitution, no epsilon, no min_periods=N gate. Invalid close produces missing thereafter until a fresh explicit calculation prefix; never bridge a gap silently.

### Reuse segment, add narrow explicit semantics

Add level min/max to existing aggregate grammar. Add `include_start` boolean (default true) and `empty_policy` enum `missing|end` (default missing), initially supported only with level min/max. These new optional fields are omitted from legacy identities when at defaults; old AST identities and behavior stay identical. Invalid combinations rejected.

The end is always inclusive. First resolve existing episode endpoints, then exclude start if requested, then apply existing last_n against actual included samples. `empty_policy=end` applies ONLY to valid coincident start=end with excluded start: evaluate that one end candle. It does not repair reversed, missing, future or unavailable endpoints. For previous peak→next_origin retain existing strict ordering; coincident previous endpoints remain missing. Any included nonfinite sample invalidates the result, matching reference min/max behavior.

C6 configuration:
- current: episode trend, touch current, from peak, to current, value level, aggregate min for long / max for short, include_start false, empty_policy end;
- previous: episode trend, touch previous, from peak, to next_origin, value level, aggregate min for long / max for short, include_start false, empty_policy missing;
- long = current_min - previous_min;
- short = previous_max - current_max.

For acceptance, use separate explicit long/short operand expressions and existing arithmetic. For a single two-sided manifest, use plain side-signed RSI segments: min(current signed RSI) - min(previous signed RSI). On short min(-RSI)=-max(RSI), so this is exactly previous_max-current_max without a forbidden operand override. Existing plain segment series are implicitly negated on short: configure `of.by_side` with the SAME rsi_ewm feature on both sides to explicitly obtain unmirrored RSI levels. This reuses existing by_side semantics and avoids double sign reversal. No implicit side normalization in rsi_ewm. Current is the evaluated candle, not a stale first-touch bar. At entry=P the current sample is RSI(entry). First touch lacking a previous wave is missing. No borrowing a touch from another episode.

### History is part of parity

Recursive equality requires the same starting prefix or equivalent persisted recursive state. Do not claim exact full-history parity from an arbitrary finite warm-up. Acceptance loads the identical complete MDS prefix used by the reference, records its first bar/hash, and computes RSI before slicing the report period. Runtime uses the actual supplied calculation prefix and exposes/documents its origin through existing execution metadata; extending the report end cannot alter earlier values for the same prefix. Planner must include episode lookback plus recursive warm-up according to explicit Engine history policy; docs must distinguish convergence from exact seed equality. This change does not promise invariance when the input start itself changes or introduce a new state persistence subsystem.

### Integration

Register the new feature through ordinary feature planning/catalog/schema/evaluation paths, including point samples and segment collection. Preserve completed-HTF visibility for generic feature use; C6 uses the base candles. Include feature kind, period, timeframe, source, segment aggregate and nondefault boundary policies in identities. Reuse range-extreme utility, with finite-prefix counts to enforce missing semantics. No repeated slice scan per candidate if avoidable.

## Risks / Trade-offs

- Different seed prefix masquerades as formula mismatch → record input origin; separate same-prefix parity from production warm-up sensitivity.
- Existing min/max names belong to from_start → test legal dispatch explicitly; do not fall through existing mean branch.
- Peak exclusion loses entry=P → explicit end fallback only for current coincident endpoints.
- Research arrays and Engine waves differ → validate timestamps/side and point mappings before comparing feature values; report missing mismatches, not only finite errors.
- Additive feature kind increases catalog surface → retain strict generic contract and one documented formula, no filter IDs.

## Migration Plan

No automatic migration. Existing manifests stay valid and unchanged. Provide an opt-in C6 example using rsi_ewm and explicit boundaries. Rollback consists of removing that opt-in manifest; production configuration is not changed by this work. Require parity evidence before claiming C6 support.
