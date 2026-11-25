# Схема графа Neo4j

## Назначение и источник данных

Neo4j хранит граф клиентов, счетов, устройств и переводов. Заполнение выполняет `events/neo4j_client.py` (`Neo4jGraphClient.sync_batch`) при обработке валидных событий Kafka Consumer.

Текущая схема формируется инкрементально из событий. PostgreSQL `events_eventlog` остаётся журналом принятых событий и источником для текущего Rule-based детектора.

## Узлы

| Label | Ключевое свойство | Назначение |
|---|---|---|
| `Client` | `client_id` | Клиент |
| `Account` | `account_id` | Банковский счёт |
| `Device` | `device_id` | Устройство |

В коде узлы создаются через `MERGE`, поэтому повторная обработка события не должна создавать повторный узел с тем же идентификатором.

## Связи

| Тип | Направление | Свойства, задаваемые кодом | Назначение |
|---|---|---|---|
| `OWNER_OF` | `(:Client)-[:OWNER_OF]->(:Account)` | нет | Счёт, связанный с клиентом |
| `USED` | `(:Client)-[:USED]->(:Device)` | `last_seen` | Клиент использовал устройство |
| `TRANSFER_TO` | `(:Account)-[:TRANSFER_TO]->(:Account)` | `event_id`, `amount`, `event_time` | Перевод между счетами |

`USED` обновляет `last_seen` при поступлении нового события с тем же клиентом и устройством.

`TRANSFER_TO` создаётся только для события `transfer`, если в payload присутствует `target_account_id`. Связь ищется/создаётся через `MERGE` с ключом `event_id`; затем обновляются сумма и время события.

## Ограничения и индексы

Метод `Neo4jGraphClient._init_constraints()` выполняет следующие уникальные ограничения:

```cypher
CREATE CONSTRAINT client_id_unique IF NOT EXISTS
FOR (c:Client) REQUIRE c.client_id IS UNIQUE;

CREATE CONSTRAINT account_id_unique IF NOT EXISTS
FOR (a:Account) REQUIRE a.account_id IS UNIQUE;

CREATE CONSTRAINT device_id_unique IF NOT EXISTS
FOR (d:Device) REQUIRE d.device_id IS UNIQUE;
```

В текущем методе инициализации **не создаётся** индекс по `TRANSFER_TO.event_time` и не создаётся отдельное ограничение уникальности для `TRANSFER_TO.event_id`. Такие индексы/ограничения нельзя считать частью автоматически разворачиваемой схемы без отдельной миграции/изменения кода.

## Получение подграфа инцидента

`api/services.py:get_alert_graph()` передаёт сохранённые в `FraudAlert.graph_ref` идентификаторы в `Neo4jGraphClient.get_subgraph()`.

Метод выбирает узлы по спискам `client_ids`, `account_ids`, `device_ids`, затем возвращает связи между выбранными узлами. Для `TRANSFER_TO` дополнительно применяется фильтр по `event_ids`; для остальных типов связей фильтр по `event_id` не применяется.

Формат результата:

```json
{
  "nodes": [
    {"id": "client:...", "type": "client", "label": "..."}
  ],
  "edges": [
    {
      "id": "...",
      "source": "account:...",
      "target": "account:...",
      "type": "transfer_to"
    }
  ]
}
```

Узлы возвращаются с идентификатором, типом и текстовой меткой. Рёбра возвращаются с идентификатором, source, target и типом. Текущий API не отдаёт в графовом ответе сумму и время перевода, хотя эти свойства хранятся на отношениях Neo4j.

## Важные особенности и ограничения

- `get_subgraph()` не выполняет обход графа на заданную глубину: он возвращает связи между узлами, уже перечисленными в `graph_ref`.
- Размер подграфа зависит от числа идентификаторов, сохранённых в инциденте. В текущем запросе нет явного `LIMIT`.
- Для цепочек переводов `graph_ref` содержит клиентов, счета и event IDs, но список устройств обычно пуст. Для `shared_device` сохраняется идентификатор устройства.
- Инициализация ограничений вызывается при создании клиента с `initialize_constraints=True`; ошибки создания ограничений логируются, но не пробрасываются наружу.
- В DOCX-материале ранее был приведён индекс `TRANSFER_TO.event_time`; текущий код его не создаёт. Ориентироваться следует на этот файл и фактический метод `_init_constraints()`.

## Полезные команды Neo4j Browser

Количество узлов по меткам:

```cypher
MATCH (n)
RETURN labels(n) AS labels, count(*) AS count;
```

Количество связей по типам:

```cypher
MATCH ()-[r]->()
RETURN type(r) AS relationship, count(*) AS count;
```

Пример выборки небольшого фрагмента:

```cypher
MATCH (n)
RETURN n
LIMIT 50;
```
