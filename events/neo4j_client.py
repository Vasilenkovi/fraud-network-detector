import logging
from typing import List
from neo4j import GraphDatabase
from django.conf import settings
from .contracts import IncomingEvent

logger = logging.getLogger('events')


class Neo4jGraphClient:
    def __init__(self, initialize_constraints=True):
        cfg = settings.NEO4J
        self.driver = GraphDatabase.driver(
            cfg["URI"],
            auth=(cfg["USER"], cfg["PASSWORD"])
        )
        if initialize_constraints:
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

    def get_subgraph(self, client_ids=None, account_ids=None, device_ids=None, event_ids=None):
        """Return a JSON-ready subgraph restricted to identifiers stored on an alert."""
        params = {
            "client_ids": client_ids or [],
            "account_ids": account_ids or [],
            "device_ids": device_ids or [],
            "event_ids": event_ids or [],
        }
        if not any(params.values()):
            return {"nodes": [], "edges": []}

        query = """
        MATCH (n)
        WHERE (n:Client AND n.client_id IN $client_ids)
           OR (n:Account AND n.account_id IN $account_ids)
           OR (n:Device AND n.device_id IN $device_ids)
        WITH collect(DISTINCT n) AS selected
        UNWIND selected AS n
        OPTIONAL MATCH (n)-[r]-(m)
        WHERE m IN selected
          AND (r.event_id IS NULL OR r.event_id IN $event_ids OR type(r) <> 'TRANSFER_TO')
        RETURN n, r, m
        """
        nodes = {}
        edges = {}
        with self.driver.session() as session:
            records = session.run(query, **params)
            for record in records:
                for node in (record["n"], record["m"]):
                    if node is None:
                        continue
                    labels = list(node.labels)
                    label = labels[0].lower() if labels else "node"
                    props = dict(node)
                    node_id = props.get("client_id") or props.get("account_id") or props.get("device_id")
                    if node_id is None:
                        continue
                    key = f"{label}:{node_id}"
                    nodes[key] = {"id": key, "type": label, "label": str(node_id)}
                rel = record["r"]
                if rel is not None:
                    start_props = dict(rel.start_node)
                    end_props = dict(rel.end_node)
                    source_label = next(iter(rel.start_node.labels), "Node").lower()
                    target_label = next(iter(rel.end_node.labels), "Node").lower()
                    source = start_props.get("client_id") or start_props.get("account_id") or start_props.get("device_id")
                    target = end_props.get("client_id") or end_props.get("account_id") or end_props.get("device_id")
                    if source is None or target is None:
                        continue
                    edge_id = str(getattr(rel, "element_id", f"{source}:{target}:{rel.type}"))
                    edges[edge_id] = {
                        "id": edge_id,
                        "source": f"{source_label}:{source}",
                        "target": f"{target_label}:{target}",
                        "type": rel.type.lower(),
                    }
        return {"nodes": list(nodes.values()), "edges": list(edges.values())}

    def close(self):
        self.driver.close()
