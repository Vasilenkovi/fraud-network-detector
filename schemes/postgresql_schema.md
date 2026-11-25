# Схема PostgreSQL

## Назначение

PostgreSQL используется Django-приложением как реляционное хранилище:

- принятых событий Kafka;
- отклонённых сообщений;
- обнаруженных инцидентов;
- решений аналитиков;
- запусков Replay.

Фактическая схема определяется Django-моделями и миграциями в `events/` и `api/`. Ниже описаны поля, присутствующие в текущем коде.

## Приложение `events`

### `events_eventlog` — журнал принятых событий

Модель: `events.models.EventLog`.

| Поле | Тип Django | Ограничения / назначение |
|---|---|---|
| `seq` | `BigAutoField` | Первичный ключ, порядковый номер записи |
| `event_id` | `CharField(64)` | Уникальный идентификатор события |
| `event_type` | `CharField(32)` | Тип: `transfer`, `login`, `account_opened` |
| `event_time` | `DateTimeField` | Время события; индексируется |
| `client_id` | `CharField(64)` | Идентификатор клиента; индексируется |
| `account_id` | `CharField(64)` | Идентификатор счёта; индексируется |
| `payload` | `JSONField` | Полное исходное сообщение |
| `source` | `CharField(16)` | Источник; по умолчанию `kafka` |
| `received_at` | `DateTimeField` | Время записи в БД (`auto_now_add`) |

Дополнительный составной индекс создаётся Django по полям `(event_type, event_time)`.

`event_id` защищает от повторной вставки на уровне уникального ограничения. Consumer/sink использует пакетную вставку с игнорированием конфликтов.

### `events_rejectedevent` — отклонённые сообщения

Модель: `events.models.RejectedEvent`.

| Поле | Тип Django | Назначение |
|---|---|---|
| `id` | `BigAutoField` | Первичный ключ |
| `raw` | `TextField` | Исходный текст сообщения |
| `reason` | `TextField` | Причина отклонения/ошибка валидации |
| `topic` | `CharField(255)` | Kafka topic |
| `partition` | `IntegerField` | Партиция Kafka |
| `offset` | `BigIntegerField` | Offset сообщения |
| `received_at` | `DateTimeField` | Время записи в БД |

Модель хранит диагностические сведения о сообщениях, не прошедших валидацию.

## Приложение `api`

### `api_fraudalert` — обнаруженные инциденты

Модель: `api.models.FraudAlert`.

| Поле | Тип Django | Назначение |
|---|---|---|
| `id` | `BigAutoField` | Первичный ключ |
| `alert_id` | `CharField(64)` | Внешний идентификатор инцидента, уникальный |
| `fingerprint` | `CharField(64)` | Уникальный fingerprint для дедупликации |
| `scheme` | `CharField(32)` | Тип схемы: `shared_device`, `fast_chain`, `cycle_transfer` |
| `risk_score` | `FloatField`, nullable | Сейчас остаётся `NULL` |
| `status` | `CharField(20)` | `new`, `in_review`, `confirmed`, `rejected` |
| `reason` | `TextField` | Причина обнаружения |
| `features` | `JSONField` | Список признаков/описаний сработавшего правила |
| `participants` | `JSONField` | Участники инцидента |
| `graph_ref` | `JSONField` | Идентификаторы узлов и событий для получения подграфа Neo4j |
| `created_at` | `DateTimeField` | Время создания |
| `updated_at` | `DateTimeField` | Время последнего обновления |

Индексы: уникальные индексы `alert_id` и `fingerprint`; индексы по `scheme`, `status`, `created_at`, а также составной индекс `(status, created_at)`.

### `api_fraudalertdecision` — история решений аналитика

Модель: `api.models.FraudAlertDecision`.

| Поле | Тип Django | Назначение |
|---|---|---|
| `id` | `BigAutoField` | Первичный ключ |
| `alert_id` | `ForeignKey` | Ссылка на `FraudAlert`, `CASCADE` |
| `analyst_id` | `ForeignKey` | Пользователь Django, `PROTECT` |
| `status` | `CharField(20)` | Решение `confirmed` или `rejected` |
| `comment` | `TextField` | Комментарий; может быть пустым для подтверждения |
| `created_at` | `DateTimeField` | Время решения |

Каждое решение записывается отдельной строкой. Текущий статус инцидента также обновляется в `FraudAlert.status`.

### `api_replayrun` — задания повторного анализа

Модель: `api.models.ReplayRun`.

| Поле | Тип Django | Назначение |
|---|---|---|
| `id` | `UUIDField` | Первичный ключ и task ID |
| `requested_by_id` | `ForeignKey`, nullable | Пользователь, запросивший Replay; `SET_NULL` |
| `start_time` | `DateTimeField` | Начало анализируемого интервала |
| `end_time` | `DateTimeField` | Конец анализируемого интервала |
| `status` | `CharField(16)` | `queued`, `running`, `succeeded`, `failed` |
| `result` | `JSONField` | Результат выполнения |
| `error` | `TextField` | Текст ошибки |
| `created_at` | `DateTimeField` | Создание задания |
| `started_at` | `DateTimeField`, nullable | Начало выполнения |
| `finished_at` | `DateTimeField`, nullable | Завершение выполнения |

## Связи между таблицами

- `FraudAlertDecision.alert_id → FraudAlert.id`: при удалении инцидента история решений удаляется (`CASCADE`).
- `FraudAlertDecision.analyst_id → AUTH_USER_MODEL.id`: пользователь не удаляется автоматически при наличии решений (`PROTECT`).
- `ReplayRun.requested_by_id → AUTH_USER_MODEL.id`: при удалении пользователя поле обнуляется (`SET_NULL`).

## Проверка актуальной схемы

После изменения Django-моделей создавайте миграции и применяйте их:

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py showmigrations
```

Для просмотра SQL конкретной миграции:

```bash
python manage.py sqlmigrate events 0001
python manage.py sqlmigrate api 0001
```

Физические имена индексов могут зависеть от миграций. Источником истины для текущей БД являются модели и применённые миграции, а не старые схемы из офисных документов.
