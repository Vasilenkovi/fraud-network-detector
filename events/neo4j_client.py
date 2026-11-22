import logging
from typing import List
from neo4j import GraphDatabase
from django.conf import settings
from .contracts import IncomingEvent

logger = logging.getLogger('events')


class Neo4jGraphClient:
    def __init__(self):
        cfg = settings.NEO4J
        self.driver = GraphDatabase.driver(
            cfg["URI"],
            auth=(cfg["USER"], cfg["PASSWORD"])
        )
        self._init_constraints()

    def _init_constraints(self):
        """Создает уникальные ограничения (индексы) для быстрой идемпотентной вставки"""
        queries = [
            "CREATE CONSTRAINT client_id_unique IF NOT EXISTS FOR (c:Client) REQUIRE c.client_id IS UNIQUE",
            "CREATE CONSTRAINT account_id_unique IF NOT EXISTS FOR (a:Account) REQUIRE a.account_id IS UNIQUE",
            "CREATE CONSTRAINT device_id_unique IF NOT EXISTS FOR (d:Device) REQUIRE d.device_id IS UNIQUE",
        ]
        try:
            with self.driver.session() as session:
                for q in queries:
                    session.run(q)
        except Exception as e:
            logger.error(f"Ошибка инициализации ограничений Neo4j: {e}")

    def sync_batch(self, events: List[IncomingEvent]):
        """Пакетное инкрементальное обновление графа из списка валидных событий"""
        if not events:
            return

        # Подготавливаем плоские словари для передачи в Cypher UNWIND
        batch_data = []
        for ev in events:
            batch_data.append({
                "event_id": ev.event_id,
                "event_type": ev.event_type,
                "event_time": ev.event_time.isoformat(),
                "client_id": ev.client_id,
                "account_id": ev.account_id,
                "device_id": ev.payload.get("device_id"),
                "target_account_id": ev.payload.get("target_account_id"),
                "amount": ev.payload.get("amount", 0.0)
            })

        cypher_query = """
        UNWIND $batch AS row

        // 1. Создаем/находим Клиента и его Счет
        MERGE (c:Client {client_id: row.client_id})
        MERGE (a:Account {account_id: row.account_id})
        MERGE (c)-[:OWNER_OF]->(a)

        // 2. Если есть устройство, привязываем Клиента к Устройству
        FOREACH (_ IN CASE WHEN row.device_id IS NOT NULL THEN [1] ELSE [] END |
            MERGE (d:Device {device_id: row.device_id})
            MERGE (c)-[u:USED]->(d)
            SET u.last_seen = datetime(row.event_time)
        )

        // 3. Если это перевод (transfer), создаем направленное ребро между счетами
        FOREACH (_ IN CASE WHEN row.event_type = 'transfer' AND row.target_account_id IS NOT NULL THEN [1] ELSE [] END |
            MERGE (target:Account {account_id: row.target_account_id})
            MERGE (a)-[t:TRANSFER_TO {event_id: row.event_id}]->(target)
            SET t.amount = toFloat(row.amount),
                t.event_time = datetime(row.event_time)
        )
        """

        with self.driver.session() as session:
            session.run(cypher_query, batch=batch_data)

    def close(self):
        self.driver.close()
