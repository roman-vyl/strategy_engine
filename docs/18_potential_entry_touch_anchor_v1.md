# Potential Entry for touch-anchor v1

## Зачем это нужно

Текущий Strategy Engine хорошо рассчитывает стратегию на историческом диапазоне:

```text
features
→ direction
→ blockers
→ setups
→ triggers
→ risk
→ final entries
→ exit policy
```

Этот расчётный pipeline остаётся основным и не меняется.

Для будущего live Runtime нам дополнительно нужен ответ на другой вопрос:

> Если позиция сейчас отсутствует, существует ли на текущем закрытом баре полный потенциальный набор entry, stop и take?

Существующий final entry отвечает уже после срабатывания trigger. Для `touch_anchor` этого недостаточно: live-система должна заранее поставить потенциальную заявку на anchor и обновлять её после каждого нового закрытого бара.

Для этого рядом с существующим расчётом добавляется новая необязательная проекция `PotentialEntry`.

## Что остаётся неизменным

Новая проекция не меняет:

- feature planning;
- расчёт EMA, ATR и других indicators;
- direction semantics;
- blockers;
- setups;
- существующие triggers;
- final entry masks;
- exit-policy ratios, которые уже публикуются наружу;
- существующие range API и их consumers;
- managed replay.

`PotentialEntry` не становится новым execution engine и не заменяет старый результат стратегии. Это дополнительный векторный расчётный артефакт для будущего live adapter.

## Внутренний источник для PotentialEntry

В текущем Engine уже существует точный pre-trigger seam:

```text
SideSetupEvaluation.pre_trigger_allowed
```

Он формируется после direction, blockers, setup calculations и setup context gates, но до применения trigger.

В новой работе это поле не превращается в отдельный публичный статус, новый вектор `global_entry_allowed` или самостоятельную domain-сущность. Оно остаётся существующим внутренним условием, которое `PotentialEntry` projector использует при построении цен.

Разрешение входа кодируется самим результатом:

```text
PotentialEntry существует
→ entry, stop и take рассчитаны

PotentialEntry отсутствует
→ потенциального входа на баре нет
```

Это не то же самое, что локальные поля `armed` внутри отдельных setup-компонентов. Локальный setup может быть armed, но `pre_trigger_allowed` всё ещё может быть false из-за blocker-а, direction или другого setup.

## Scope первой версии

Первая версия поддерживает только:

```text
trigger = touch_anchor
```

Для других trigger-компонентов потенциальная цена входа пока не определяется. Это намеренное ограничение: сначала нужно получить корректную и проверяемую вертикаль для самого понятного случая.

Для `touch_anchor` потенциальная цена входа на каждом баре равна текущему anchor EMA:

```text
potential entry price = anchor EMA
```

Тип биржевой заявки не является ответственностью `PotentialEntry`. Engine возвращает только цену. То, будет ли она интерпретирована как limit order и как именно будет отправлена на биржу, позже определят Runtime/ABI contracts.

## Минимальная сущность PotentialEntry

`PotentialEntry` должен содержать только торговые значения, которые рассчитывает Engine:

```text
side
entry_price[]
stop_price[]
take_price[]
```

Это векторный объект на ширине расчётного диапазона. Для каждого бара существует либо полная тройка цен, либо потенциальный вход отсутствует полностью.

Инвариант:

```text
entry_price[N], stop_price[N], take_price[N]
присутствуют все вместе

или

все три отсутствуют
```

Отдельные поля `allowed`, `trigger_type`, `order_kind`, labels и hashes внутри `PotentialEntry` не требуются.

Идентичность strategy instance, spec, market range и market-data provenance уже принадлежит родительскому evaluation response и не должна дублироваться в каждом торговом векторе.

## Как рассчитывается potential entry

На каждом баре и для каждой стороны проектор использует уже рассчитанные результаты setup- и trigger-этапов:

```text
pre_trigger_allowed
AND touch_anchor.close_ok
AND anchor EMA ready
AND initial stop distance ready
AND initial take distance ready
```

`touch_anchor.close_ok` не означает, что касание уже произошло. Он только подтверждает правильную геометрию ожидающей заявки: для long текущий close находится не ниже anchor, а для short — не выше anchor. Без этого ограничения потенциальная цена anchor могла бы оказаться с неправильной стороны текущего рынка и превратиться в немедленно исполняемую, а не ожидающую touch-заявку.

Если хотя бы одно обязательное значение отсутствует, не является конечным числом или меньше либо равно нулю, `PotentialEntry` на этом баре отсутствует. Те же требования применяются к рассчитанным entry, stop и take.

Если все значения готовы:

```text
entry_price = anchor EMA
```

## Как рассчитываются potential stop и potential take

До открытия сделки работают только initial stop и initial take. Managed stop, runner, take switching и runtime exits к `PotentialEntry` не относятся.

Initial stop/take уже определяются существующим exit-policy pipeline. Для ATR-based правил внутри Engine сначала рассчитывается абсолютная дистанция в цене актива:

```text
stop distance = ATR × stop multiplier
take distance = ATR × take multiplier
```

После этого текущий legacy-compatible output нормализует дистанцию относительно close и публикует ratio. Для `PotentialEntry` использовать этот ratio напрямую нельзя, потому что потенциальный вход находится на anchor, а не на close.

Новая проекция должна получать уже рассчитанную raw distance до её нормализации.

### Long

```text
entry = anchor
stop  = anchor - stop distance
take  = anchor + take distance
```

### Short

```text
entry = anchor
stop  = anchor + stop distance
take  = anchor - take distance
```

`PotentialEntry` не пересчитывает ATR и не читает multipliers из spec. Выбор active initial stop/take rules и расчёт их distance остаются ответственностью существующего exit-policy pipeline.

## Как подключить проекцию без дублирования расчёта

Существующий pipeline должен выполняться один раз.

После него уже рассчитанные промежуточные результаты передаются двум независимым проекциям:

```text
existing vector calculation
        ↓
internal evaluation results
        ├─→ existing StrategyRangeResult
        └─→ PotentialEntry projector
```

Старый projector продолжает формировать прежний публичный range response.

Новый projector использует только:

- `pre_trigger_allowed` по каждой стороне;
- уже вычисленный `touch_anchor.close_ok` из trigger evaluation;
- anchor EMA vector;
- выбранную raw initial stop distance;
- выбранную raw initial take distance.

Он не вычисляет повторно indicators, blockers, setups или exit rules.

Для этого может понадобиться небольшой внутренний structural refactor: перестать держать нужные промежуточные результаты только в локальных переменных одного evaluator-а и собрать их в непубличный evaluation bundle. Такой refactor не должен менять порядок расчёта, торговую семантику или существующие API contracts.

## Поведение от бара к бару

`PotentialEntry` пересчитывается на каждом новом закрытом баре.

Пример:

```text
bar N:
  pre_trigger_allowed = true
  touch_anchor.close_ok = true
  anchor = 60 000
  ATR stop distance = 1 200
  ATR take distance = 3 600

  potential entry = 60 000
  potential stop  = 58 800
  potential take  = 63 600
```

На следующем баре anchor и ATR могут измениться:

```text
bar N+1:
  potential entry = 60 080
  potential stop  = 58 860
  potential take  = 63 740
```

Если blocker, direction или setup запрещают вход:

```text
bar N+2:
  potential entry = absent
  potential stop  = absent
  potential take  = absent
```

Будущий live adapter возьмёт только значения target bar. Но сам `PotentialEntry` остаётся обычным векторным Engine artifact и может использоваться другими consumers и research-инструментами.


## Однозначная форма range-ответа

Поле `potential_entries` присутствует в каждом успешном range response.

Для trigger, который пока не поддерживает потенциальный вход:

```json
{
  "potential_entries": {}
}
```

Для `touch_anchor` внутри объекта присутствуют только включённые стороны. Выключенная сторона полностью отсутствует, а не публикуется как объект из `null`-массивов.

На включённой стороне сами массивы всегда выровнены по барам. Warmup или запрет входа выражается тройкой `null` на соответствующем индексе.

Важно: проектор использует `pre_trigger_allowed`, но не требует, чтобы сам trigger оставался несработавшим. Поэтому на touch-баре одновременно допустимы:

```text
final entry = true
potential entry / stop / take = present
```

Это не означает, что Engine считает позицию открытой. Проекция только публикует рассчитанную ценовую геометрию бара; будущий Runtime сам выберет нужную сущность по своему lifecycle-состоянию.

## Что не входит в эту работу

Первая версия не проектирует и не реализует:

- Runtime lifecycle `armed / entry_pending / in_position`;
- Runtime → Engine HTTP contract;
- Engine → ABI desired-state contract;
- тип биржевой заявки;
- обработку fills и partial fills;
- преобразование исполненного potential entry в managed trade seed;
- управление открытой позицией;
- поддержку `reclaim_anchor` и `strong_reclaim_anchor`;
- изменение backtest execution semantics.

Эти границы будут обсуждаться после того, как внутри Engine появится корректный и протестированный `PotentialEntry` для `touch_anchor`.

## Ожидаемый результат

После реализации Strategy Engine сможет, не меняя существующий расчётный pipeline и старые outputs, дополнительно сформировать на каждом баре:

```text
long PotentialEntry:
  entry / stop / take

short PotentialEntry:
  entry / stop / take
```

Потенциальный вход существует только там, где внутренний `pre_trigger_allowed` разрешает построение плана и все три цены могут быть рассчитаны из уже существующих Engine results. Отдельный публичный статус разрешения не добавляется.
