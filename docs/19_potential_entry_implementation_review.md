# Potential Entry touch-anchor v1 — implementation review

## Итог

Реализация агента была архитектурно близка к правильной и не превратила Strategy Engine в новый execution-комбайн:

- основной EMA Pullback pipeline выполняется один раз;
- `PotentialEntry` остаётся отдельной узкой проекцией;
- ATR не рассчитывается повторно;
- существующий exit-policy wire contract не расширен raw-distance полями;
- Runtime и Abi зависимости в Strategy Engine не добавлены.

Однако зелёных 152 тестов оказалось недостаточно. Реальный bar-to-bar API-прогон обнаружил торговую ошибку, а тест non-touch сценария был связан одновременно с raw spec и вручную собранными trigger fixtures, поэтому не защищал новый seam от рассинхронизации.

После review-pass реализация исправлена и покрыта 154 тестами.

## Найденная семантическая ошибка

Первоначальный projector использовал только:

```text
SideSetupEvaluation.pre_trigger_allowed
+ anchor
+ raw stop/take distances
```

На реальном BTCUSDT 1h баре это позволило сформировать short potential entry ниже текущего close:

```text
close  = 70 542.90
anchor = 70 534.26375
short potential entry = 70 534.26375
```

Для ожидающего short touch-плана anchor должен находиться не ниже текущего рынка. Иначе sell-limit на такой цене становится немедленно marketable вместо ожидания возврата цены к anchor.

При этом trigger pipeline уже рассчитывал нужное условие:

```text
touch_anchor.trace.close_ok
```

Для long оно означает `close >= anchor`, для short — `close <= anchor`.

Исправленный projector использует:

```text
pre_trigger_allowed
AND evaluated touch_anchor.close_ok
```

Он по-прежнему не требует самого `touch` и не использует `trigger.allowed`, поэтому potential triple остаётся доступным и на баре, где touch уже состоялся и final entry стал true.

## Чистота зависимостей

Первоначальная реализация повторно разбирала `raw_spec`, чтобы определить trigger type. Это создавало второй источник истины рядом с уже рассчитанным `SideTriggerEvaluation`.

После исправления projector получает готовые trigger evaluations:

```text
existing setup evaluation
existing trigger evaluation
existing feature frame
existing exit-policy evaluation
→ PotentialEntry projection
```

Trigger-модуль сам владеет типизированным чтением собственного `close_ok` output. `PotentialEntry` не знает структуру raw spec и не вычисляет trigger geometry заново.

## Состав модели

Модель оставлена минимальной:

```text
PotentialEntry
- side
- entry_price[]
- stop_price[]
- take_price[]
```

Не добавлены:

- `armed`;
- `allowed`;
- `global_entry_allowed`;
- order type;
- trigger type;
- plan ID;
- config hash;
- market-data hash.

На каждом баре действует инвариант:

```text
entry, stop, take присутствуют вместе
или
все три отсутствуют
```

## Raw exit distances

Добавление raw stop/take distances в `ExitPolicyEvaluation` признано оправданным. Оно не дублирует ATR calculation и сохраняет одно место выбора exit rules:

```text
exit-policy selection
├─ legacy ratio = distance / close
└─ raw distance for PotentialEntry
```

Potential price geometry рассчитывается только из уже выбранных distance vectors:

```text
long:  stop = anchor - distance, take = anchor + distance
short: stop = anchor + distance, take = anchor - distance
```

Существующий `ExitPolicyEvaluation.to_wire()` raw distances не публикует.

## Python 3.9 / 3.12

Проект уже нормативно требует Python 3.12+:

- `requires-python = ">=3.12"`;
- Ruff target `py312`;
- mypy target `3.12`.

Проблема была в operational tooling: Makefile вызывал bare `python`, `ruff`, `mypy` и `uvicorn`, которые могли принадлежать разным installations.

Review-pass добавляет:

- `.python-version` со значением `3.12`;
- явную проверку минимальной версии;
- запуск всех инструментов через один `$(PYTHON) -m ...`;
- README-инструкцию для отдельного `.venv` на Python 3.12;
- Python cache/venv entries в `.gitignore`.

Это не делает код совместимым с Python 3.9. Наоборот, Python 3.9 теперь должен завершаться немедленной понятной ошибкой до запуска тестов или сервиса.

## Реальный API probe

Использованы пять реальных BTCUSDT 1h свечей за 24 марта 2026 года. Каждый следующий запрос имитировал новый closed-bar webhook и расширял range на один бар.

Проверено:

- HTTP 200 на каждом цикле;
- ровно один market-data read на range request;
- `potential_entries: {}` для non-touch trigger;
- только enabled-side keys;
- complete-or-null triple;
- long plan не выше close;
- short plan не ниже close;
- корректная side-relative stop/take geometry;
- potential triple сохраняется на touch-баре вместе с final entry.

Полный machine-readable результат сохранён отдельно как `potential_entry_real_data_probe.json`.

## Оставшийся числовой долг

Реальный probe показал существующую float-особенность Engine:

```text
68456.00687499999
```

Такие значения возникают ещё в indicator/ATR float pipeline и затем честно сериализуются через `Decimal(str(float))`. Это не дефект только нового projector-а и не следует лечить случайным округлением внутри `PotentialEntry`.

Перед передачей цен в реальную биржу нужен отдельный явный контракт numeric normalization:

- instrument tick size;
- side-aware exchange rounding;
- место ответственности между Engine и Abi.

До этого момента output семантически корректен, но не является готовой exchange-quantized ценой.

## Mypy baseline

Не рекомендуется расширять этот OpenSpec на исправление 26 repository-wide pre-existing mypy ошибок. В самом репозитории уже есть более ранние OpenSpec tasks, оставленные открытыми из-за отсутствия полного Ruff/mypy/build окружения.

Текущий change должен сохранять честный статус:

```text
feature semantics and tests: complete
repository-wide typecheck baseline: separate debt
```

Задачу `Existing repository verification passes` нельзя отмечать выполненной, пока полный `make verify` действительно не станет зелёным в едином Python 3.12 environment.
