# ema_pullback

Исследовательская strategy family для EMA pullback после Step 11 и Step 12.

## Exit Policy v1 (current)

Слой exits мигрирован на `strategy.trade_management.exit_policy`:

- legacy путь `strategy.exits` fail-fast отклоняется в loader;
- HTF provider config живёт в `strategy.contexts[<context_ref>]` (`component_id: htf_context`);
- exit policy потребляет контекст через `trade_management.exit_policy.context_consumption` (policy `exit_profile_by_htf_state`);
- legacy `trade_management.exit_policy.context` **не поддерживается** loader (one-off: `scripts/migrate_exit_context_to_strategy_contexts.py`);
- активные правила на сделке: `always_on + profile(side + htf_context.state)`;
- сигнальные exits внутри активной группы агрегируются через OR;
- distance exits внутри активной группы агрегируются через min;
- signal trace / Bar Inspector получают диагностику `htf_context` (`state`, `fast/anchor/slow`, `meta`) только когда BFF получает `context_overlay_ref` (Chart передаёт effective ref: picker, exit consumption ref, или единственный ключ в `strategy.contexts`);
- Chart HTF EMA dashed lines (`htf_fast` / `htf_anchor` / `htf_slow`) — из `signal_trace.htf_context`, не из BFF `chart_overlay_ema`; полный контракт: `openspec/specs/workbench-chart-htf-context-overlays/spec.md`;
- `context_consumption_trace` в signal trace: per-consumer `role`, `context_ref`, `policy_id`, `context_applied` (Phase 4);
- новые run reports: `report_schema_version: 5` с `entry_context_consumption` / `exit_context_consumption` на closed trades (отдельно от `entry_context_state`);
- v3/v4 reports остаются read-only; Composer не авторит `exit_policy.context` (только `strategy.contexts` + `context_consumption`).

### Context diagnostics: wiring vs causal

| Layer | Where | Answers |
|-------|--------|---------|
| **Wiring** | `trade_records.entry_context_consumption` / `exit_context_consumption` | Which consumer and `policy_id` were configured; entry `applied` = `htf_regime_gate` allow on **entry bar** (when bundle available at extract) |
| **Causal** | `signal_trace.context_consumption_trace` + `htf_context.state[]` | Per-bar `context_applied` (gate allow/block), HTF `state`, exit `outcome.profile_*` |

Chart **trade diagnostics** show both: configured consumer + **Entry/Exit bar decision** from loaded signal trace. Bar Inspector remains per-click bar. See `openspec/changes/trade-context-causal-diagnostics-v1/`.

Spike по entry-lock semantics задокументирован в `docs/research/17_exit_policy_entry_lock_spike.md`.

После загрузки внешнего experiment-файла runner строит финальный `ExecutionConfig`
через `execution_config_from_external(...)`: `family`, `symbol`, `timeframe` и
опциональные поля `execution.*` берутся из конфига; при отсутствии
`execution.init_cash` / `fees` / `slippage` подставляются модульные дефолты
`DEFAULT_INIT_CASH` / `DEFAULT_FEES` / `DEFAULT_SLIPPAGE`. Рынок (`symbol`,
`timeframe`) всегда из загруженного спека, не из `config.py`. Отдельного
«рыночного дефолта» в модуле нет. CLI может задать только переопределение `db_path`.

Активный pipeline:

```text
EmaPullbackStrategySpec
→ FeaturePlan
→ calculated features
→ Component Registry
→ direction / blockers / setup / trigger / exits / risk
→ entry signals composer
→ execution exit-layer
→ vectorbt (OHLC-aware: `open`/`high`/`low` + `close` в `Portfolio.from_signals` для реалистичных стопов)
→ JSON report
```

После parsing/validation внешних параметров typed-construction выполняется через
`component_builders.py`: это единый слой `params -> spec dataclasses` без работы
с `DataFrame`, indicator-расчётов или runtime execution.

Стратегии для прогона задаются **только** внешним YAML/JSON (см. `research/experiments/config_loader.py` и `instance_loader.py`). Typed-сборка из dict выполняется через `make_ema_pullback_strategy_spec(...)` / builders; отдельного «списка активных спеков в Python» нет.

Текущая модель держит все выходы в `trade_management.exit_policy`:
`always_on` + профильные группы (`aligned/countertrend/neutral`) с правилами
`ExitRuleSpec`. `signals.py` собирает только входы, а `execution/exits.py`
собирает активные выходы/дистанции для vectorbt.

`variant` — это человекочитаемый label собранного `StrategySpec`. Если caller не
задаёт его явно, имя генерируется из фактических периодов `anchor_stack`:

```text
ema_pullback_fast{fast.period}_anchor{anchor.period}_slow{slow.period}
```

## Структура каталога

| Путь | Назначение |
|------|------------|
| `config.py` | `ExecutionConfig`, `DEFAULT_INIT_CASH` / `DEFAULT_FEES` / `DEFAULT_SLIPPAGE`, `execution_config_from_external` |
| `spec.py` | Dataclass-контракты `EmaPullbackStrategySpec` и вложенных spec-частей |
| `component_builders.py` | Typed builders для `anchor/trigger/blockers/trade_sides/components/trade_management` |
| `spec_instances.py` | `make_ema_pullback_strategy_spec`, `variant_from_spec` |
| `run.py` | CLI: только `--config` (experiment file) и опционально `--db-path` |
| `features/plan.py` | `FeaturePlan` из `EmaPullbackStrategySpec` без расчёта данных |
| `features/calculations.py` | Расчёт только features, объявленных в `FeaturePlan` |
| `components/*.py` | Ступени пайплайна + `registry.py` для новых role ids |
| `execution/data_loader.py` | Загрузка DB candles в `LoadedCandles` (`ohlcv` + metadata диапазона) |
| `execution/backtest.py` | Backend `run_strategy_spec(...)` через vectorbt; в `from_signals` передаются `open`/`high`/`low` из enriched OHLCV (fail-fast, если колонок нет — см. Step 15 в `docs/research/15_ohlc_aware_vectorbt_plan.md`) |
| `execution/report_table.py` | Stdout comparison table с `fast / anchor / slow` |
| `execution/runner.py` | `run_strategy_specs_from_config`: loader → финальный `ExecutionConfig` → backtest → таблица → JSON |
| `execution/result_models.py` | Dataclass-контракты `LoadedCandles`, `VariantMetrics`, `VariantResult` |
| `execution/signals.py` | Композитор `entries/short_entries` из spec + plan + Component Registry |
| `execution/exits.py` | Exit Policy compiler: `trade_management.exit_policy` → profile-aware `exits/short_exits/sl_stop/tp_stop` |
| `execution/results.py` | JSON payload schema v3, `latest.json` / `runs/<run_id>.json` |

## StrategySpec factory (Python)

`spec_instances.py` экспортирует фабрику `make_ema_pullback_strategy_spec(...)` для тестов,
`instance_loader` и ручных сценариев в коде — **не** как альтернативный пользовательский runner.

Числовые research-параметры задаются в `make_ema_pullback_strategy_spec(...)` и
внутри фабрики собираются через builders (`anchor_stack_from_periods(...)`,
`component_stack(...)`, `exits_atr_default(...)`, `trade_sides(...)`,
`untouched_anchor_setup_spec(...)`, `exit_policy(...)`). Если caller не задаёт `variant`, он выводится из фактических
`fast / anchor / slow` периодов; внешний config может передать человекочитаемый
variant label, а semantic uniqueness остаётся за `config_id`:

```text
variant = ema_pullback_fast{fast.period}_anchor{anchor.period}_slow{slow.period}

anchor_stack:
  fast   = EMA close/base/{fast.period}
  anchor = EMA close/base/{anchor.period}
  slow   = EMA close/base/{slow.period}

components:
  direction = ema_anchor_stack_trend
  blockers  = (BlockerRuleSpec(no_blockers),)
  setup     = untouched_anchor_setup
  trigger   = ReclaimTriggerSpec()  # component_id reclaim_anchor
  risk      = no_risk_filter

trade_sides:
  enabled = ("long",)

external config также принимает:
  trade_sides = ["long", "short"]
  trade_sides = {enabled = ["long", "short"]}
  trade_sides = {long = true, short = false}

trade_management:
  exit_policy:
    context: htf_context
    always_on:
      exits: [atr_stop_loss, atr_take_profit]
    profiles:
      aligned.exits: []
      countertrend.exits: []
      neutral.exits: []
```

`config_id` считается только из canonical serialization `EmaPullbackStrategySpec`
через `strategy_spec_config_id(spec)`. `trade_sides` входит в serialization, поэтому
long-only и long+short specs получают разные `config_id`.

## Side Semantics

Default active spec остаётся long-only. Если factory получает
`enabled_sides=("long", "short")`, текущие component ids исполняются с `side`
context:

```text
long:
  direction = fast > anchor > slow
  setup     = armed regime: anchor untouched lookback bars, then active through
              first touch and active_bars window (close > anchor while armed)
  trigger   = reclaim_anchor: close crosses above anchor
              touch_anchor: low touches anchor и close закрепилась выше anchor

short:
  direction = fast < anchor < slow
  setup     = armed regime mirror (close < anchor while armed)
  trigger   = reclaim_anchor: close crosses below anchor
              touch_anchor: high touches anchor и close закрепилась ниже anchor
```

`execution/signals.py` возвращает только entry-серии: `entries` и
`short_entries`. Disabled side заполняется `False`. `execution/exits.py`
отдельно собирает `exits`, `short_exits`, `sl_stop`, `tp_stop`, а
`execution/backtest.py` передаёт все серии в `vectorbt.Portfolio.from_signals(...)`.

Несколько `blockers` объединяются через AND. Несколько сигнальных exit rules
объединяются через OR внутри exit-layer. ATR stop/take остаются такими же
семантическими exit rules и только в execution-слое становятся `sl_stop/tp_stop`.

SL/TP и signal exits конфигурируются только через `trade_management.exit_policy.*.exits` (`ExitRuleSpec`).
ATR-выходы используют вложенный объект `distance` (как раньше). **Константная дистанция в USD**
(численно те же единицы, что у `close` на рынках вида `*USDT`: сдвиг цены в «долларах движения», не риск от `init_cash`)):
`component_id: constant_usd_stop_loss` / `constant_usd_take_profit` и поле `usd_distance` (строго `> 0`).
Execution-слой по-прежнему переводит это в `sl_stop` / `tp_stop` как отношение к `close`. Для этих компонентов **не** создаются ATR-колонки в `FeaturePlan`.
`trade_management.exit_policy` — единственный владелец exit graph.

Пример YAML (`strategy.trade_management.exit_policy`):

```yaml
trade_management:
  exit_policy:
    context:
      component_id: htf_context
      timeframe: 4h
      source: close
      fast_period: 100
      anchor_period: 200
      slow_period: 1000
    always_on:
      exits:
        - instance_id: sl_usd
          component_id: constant_usd_stop_loss
          usd_distance: 500.0
        - instance_id: tp_usd
          component_id: constant_usd_take_profit
          usd_distance: 1200.0
    profiles:
      aligned: { exits: [] }
      countertrend: { exits: [] }
      neutral: { exits: [] }
```

## External Params -> Builders -> Spec

Типовой путь для внешнего dict-конфига:

```python
from research.strategies.ema_pullback.component_builders import exits_atr_default
from research.strategies.ema_pullback.spec_instances import make_ema_pullback_strategy_spec

params = {
    "symbol": "BTCUSDT",
    "base_timeframe": "1h",
    "fast_period": 100,
    "anchor_period": 200,
    "slow_period": 1000,
    "atr_period": 14,
    "stop_atr_multiplier": 1.5,
    "take_atr_multiplier": 4.0,
}

spec = make_ema_pullback_strategy_spec(**params)
assert spec.trade_management.exit_policy.always_on.exits == exits_atr_default(
    atr_period=14,
    stop_atr_multiplier=1.5,
    take_atr_multiplier=4.0,
)
```

## Live components (Step 12)

Family-local registry (`components/registry.py`) включает, среди прочего:

```text
direction: ema_anchor_stack_trend
setups (stack, AND-composed): untouched_anchor_setup, ema_bounce_counter_setup, ...
trigger: reclaim_anchor, touch_anchor
blockers: no_blockers, counter_candle_blocker, rsi_lookback_extreme_blocker
exits: atr_stop_loss, atr_take_profit, constant_usd_stop_loss, constant_usd_take_profit,
       rsi_signal_exit, ema_close_loss_exit, ema_cross_loss_exit
time_stop (future)
risk: no_risk_filter
```

External instance JSON uses `strategy.setups[]` (non-empty). Each entry has `instance_id`,
`component_id`, and params (flat or nested `params` per catalog). Legacy singleton
`strategy.setup` is accepted **only** at load time and normalized to a one-element `setups`
list. Signal trace stores internals under `internals.setups[instance_id]` (no `internals.setup`).

Example dual setup:

```json
"setups": [
  {
    "instance_id": "untouched_anchor",
    "component_id": "untouched_anchor_setup",
    "lookback": 50,
    "active_bars": 3
  },
  {
    "instance_id": "bounce_counter",
    "component_id": "ema_bounce_counter_setup",
    "params": {
      "fast_ema": 50,
      "anchor_ema": 200,
      "slow_ema": 500,
      "max_bounces": 3,
      "raw_touch_mode": "range_cross",
      "touch_lookback_bars": 10,
      "trend_start_confirmation_bars": 1,
      "trend_break_confirmation_bars": 1
    }
  }
]
```

RSI и EMA для exits считаются в feature layer по `FeaturePlan`; компоненты получают
готовые колонки (`rsi_col`, `ema_col`, `fast_col` / `slow_col` — см. `execution/exits.py`).

### EMA trend signal exits (v1)

**`ema_close_loss_exit`** — base `close` против aligned EMA: long выходит, если `close < EMA`
`confirm_bars` **base-свечей** подряд; short зеркально. `ema.timeframe` задаёт TF расчёта EMA
(после align на base index). HTF-candle confirmation (три 1h-close на 5m base) **не** v1.

**`ema_cross_loss_exit`** — fast/slow EMA на **одном** timeframe, `source=close`, `fast.period < slow.period`.
`confirm_bars=1`: классический cross на base bar. `confirm_bars>1`: cross в окне последних N base bars
**и** adverse side (`fast < slow` для long) удерживается N base bars подряд (без cross — не выходим).

Контрактный default `confirm_bars=1`. Для close loss в экспериментах часто ставят `2`–`3`.

**Profile placement:** правила можно добавить в любой слот `exit_policy` (`always_on`, `aligned`,
`countertrend`, `neutral`). Типичный trend-hold пример — `profiles.aligned.exits`, но это не ограничение API.

Пример instance (nested `ema`):

```yaml
- instance_id: ema_close_aligned
  component_id: ema_close_loss_exit
  ema:
    timeframe: 1h
    source: close
    period: 200
  confirm_bars: 3
```

`rsi_lookback_extreme_blocker` — не лонговать после overbought-extreme / не шортить после
oversold-extreme в окне `lookback` (параметры `long_block_above`, `short_block_below`).
Высокий RSI сам по себе не блокирует short; низкий RSI не блокирует long. Lookback проверяет
наличие экстремума на одном из предыдущих баров (rolling max), а не только на текущем.

## Запуск

Из корня репозитория (с research-зависимостями, например `pip install -e ".[research]"`):

```bash
python research/strategies/ema_pullback/run.py --config research/experiments/configs/ema_pullback/ema_pullback_batch_001_step14.yaml
```

Опционально указать SQLite:

```bash
python research/strategies/ema_pullback/run.py --config path/to/experiment.yaml --db-path path/to/custom.sqlite
```

`symbol`, `timeframe`, `execution.*` задаются в experiment-конфиге, а не через CLI.

Успешный прогон печатает summary-строку (`family`, `experiment_id`, `symbol`, `timeframe`,
`candles`, `variants`), затем side-aware stdout comparison table и пути артефактов:

```text
variant | config_id | fast | anchor | slow | long_trades | long_pnl | long_return_pct | long_profit_factor | long_win_rate | short_trades | short_pnl | short_return_pct | short_profit_factor | short_win_rate | total_trades | total_pnl | total_return_pct | total_profit_factor | total_win_rate | total_sharpe | total_max_drawdown | open_trades_long | open_trades_short | open_trades_total
```

Колонки `fast | anchor | slow` — это периоды из `strategy_spec["anchor_stack"]`.
Side-aware метрики разделены на `long`, `short`, `total`; открытые сделки
выведены отдельно как `open_trades_*`. Полный spec (включая tuples компонентов,
RSI rules и distance exits) лежит только в JSON.

## JSON-отчёт

Прогон пишет:

- `research/results/latest.json` — последний прогон (перезаписывается)
- `research/results/runs/<run_id>.json` — тот же payload, имя по `run_id`

Top-level payload содержит `report_schema_version: 3`. Variant payload содержит:

```text
variant
config_id
symbol
timeframe
strategy_spec
metrics
component_counters
trade_records
```

Top-level также содержит `run_id`, `created_at`, `candles`, `data_range`,
`variants_count`, `variants`. При запуске через external config дополнительно
появляется `batch_metadata` с `experiment_id`, `source_file`, `entries`,
`validation_phase_status` и aggregate counters.

`metrics` имеет side-aware форму:

```text
metrics.long
metrics.short
metrics.total
metrics.open_trades
```

При успехе `run.py` печатает пути `results_artifact=` и `run_artifact=`, затем
`status=ok`.
