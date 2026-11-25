# API рабочего места аналитика

Этот документ описывает фактическую реализацию интеграционного слоя в Django-приложении `api`. Общий порядок установки Python, запуска Docker Compose, миграций и сервисов приведён в корневом `README.md`; здесь он не дублируется.

## Состав реализации

- `api/models.py` — модели `FraudAlert`, `FraudAlertDecision`, `ReplayRun`.
- `api/views.py` — REST endpoints.
- `api/serializers.py` — валидация и сериализация запросов/ответов.
- `api/services.py` — фиксация решения аналитика и получение подграфа из Neo4j.
- `api/tasks.py` — Celery-задача `api.replay_events`.
- `events/fraud_detection.py` — общий детектор, используемый CLI и Replay.
- `schemes/api_contract_v1.1.yaml` — OpenAPI-контракт.

## Маршруты

Маршруты подключены под префиксом `/api/` в `config/urls.py`.

| Метод | Endpoint | Реальное поведение |
|---|---|---|
| `GET` | `/api/alerts/` | Список инцидентов с фильтрами и offset-пагинацией |
| `GET` | `/api/alerts/{alert_id}/` | Данные инцидента и подграф из Neo4j |
| `POST` | `/api/alerts/{alert_id}/decision/` | Сохранение решения аналитика и обновление статуса |
| `POST` | `/api/replay/` | Создание ReplayRun и постановка Celery-задачи |
| `GET` | `/api/replay/{task_id}/` | Получение состояния ReplayRun |

### Список инцидентов

Поддерживаемые query-параметры:

- `status`: одно из `new`, `in_review`, `confirmed`, `rejected`;
- `scheme`: строковый фильтр по типу схемы;
- `limit`: целое число, ограничивается диапазоном 1–200, по умолчанию 50;
- `offset`: целое число не меньше 0, по умолчанию 0.

Формат ответа:

```json
{
  "count": 145,
  "limit": 50,
  "offset": 0,
  "results": [
    {
      "id": "AL-...",
      "risk_score": null,
      "status": "new",
      "reason": "...",
      "created_at": "..."
    }
  ]
}
```

Недопустимый `status` или некорректные `limit`/`offset` приводят к HTTP 400. Значение `scheme` сейчас применяется как фильтр без отдельной проверки по перечислению.

### Детали инцидента

`GET /api/alerts/{alert_id}/` возвращает поля краткого представления, `features`, `participants` и `graph`.

Граф запрашивается из Neo4j по идентификаторам, сохранённым в `FraudAlert.graph_ref`. Если Neo4j или получение подграфа завершается ошибкой, endpoint возвращает HTTP 503. Неизвестный `alert_id` возвращает HTTP 404.

Фактический формат `graph`:

```json
{
  "nodes": [
    {"id": "client:client_001", "type": "client", "label": "client_001"}
  ],
  "edges": [
    {
      "id": "...",
      "source": "account:account_001",
      "target": "account:account_002",
      "type": "transfer_to"
    }
  ]
}
```

В текущем ответе графа не передаются все свойства Neo4j-отношений (например, `amount` и `event_time`). Подграф ограничивается заранее сохранёнными идентификаторами инцидента; динамического раскрытия соседей и параметра глубины пока нет.

### Решение аналитика

Тело запроса:

```json
{
  "status": "confirmed",
  "comment": "Проверено аналитиком"
}
```

Допустимые статусы: `confirmed`, `rejected`. Для `rejected` непустой комментарий обязателен. Для `confirmed` комментарий необязателен.

Решение создаёт отдельную запись `FraudAlertDecision` и обновляет текущий `FraudAlert.status`. История решений сохраняется.

### Replay

Тело запроса:

```json
{
  "start_time": "2026-01-01T00:00:00Z",
  "end_time": "2026-01-02T00:00:00Z"
}
```

`end_time` должен быть позже `start_time`. При успешной постановке задачи endpoint возвращает HTTP 202 и сериализованную запись `ReplayRun` с `task_id`.

Celery task имеет имя `api.replay_events`. Она вызывает общий `detect_and_persist(start_time, end_time)` и обновляет статус ReplayRun. Для проверки состояния используется `GET /api/replay/{task_id}/`.

Важно: задача повторно анализирует события, чьё `event_time` попадает в выбранный интервал включительно. Она не читает Kafka повторно и не добавляет контекстные события за пределами периода.

## Аутентификация и CSRF

В `config/settings.py` для DRF задан `SessionAuthentication` и глобальное разрешение `IsAuthenticated`.

- Вход в Django выполняется через `/accounts/login/`.
- Для браузерных POST-запросов требуется CSRF-токен (`X-CSRFToken`).
- Административная панель доступна по `/admin/`.

API не настроен как публичный или token-based endpoint.

## Ограничения и известные особенности

1. `FraudAlert.risk_score` допускает `NULL`; текущий детектор не вычисляет числовой risk score.
2. Статус `in_review` предусмотрен моделью и фильтром списка, но отдельного endpoint для перевода инцидента в этот статус в текущем API нет.
3. Список инцидентов использует offset-пагинацию `{count, limit, offset, results}`.
4. Получение графа зависит от доступности Neo4j. Подграф формируется по `graph_ref`, без обхода на заданную глубину и без явного `LIMIT` в Cypher-запросе.
5. Replay выполняется Celery через Redis; если постановка задачи завершается ошибкой, API сохраняет `failed` в ReplayRun и возвращает HTTP 503.
6. В Celery task состояние `running` и время начала сохраняются перед анализом; `finished_at` записывается в блоке `finally`.
7. Rule-based детектор и его ограничения описаны в `fraud_detection.md`.

## Согласование с OpenAPI

`api_contract_v1.1.yaml` следует считать описанием контракта, а не заменой исходного кода. При изменении serializers, views или URL-маршрутов необходимо синхронно обновлять YAML и проверять, что типы, обязательные поля, коды ответов и формат `graph` совпадают с фактическим поведением.
