import logging
from typing import List
from django.db import transaction, close_old_connections
from .contracts import EventSink, IncomingEvent, Rejection, SaveResult
from .models import EventLog, RejectedEvent
from .neo4j_client import Neo4jGraphClient

logger = logging.getLogger('events')


class DjangoEventSink(EventSink):
    def __init__(self, source: str = 'kafka'):
        self.source = source
        self.graph_client = Neo4jGraphClient()

    def save_batch(self, events: List[IncomingEvent]) -> SaveResult:
        if not events:
            return SaveResult(0, 0)

        close_old_connections()

        unique_events = {}
        for ev in events:
            if ev.event_id not in unique_events:
                unique_events[ev.event_id] = ev

        event_ids = list(unique_events.keys())

        with transaction.atomic():
            existing_ids = set(
                EventLog.objects.filter(event_id__in=event_ids)
                .select_for_update()
                .values_list('event_id', flat=True)
            )

            to_insert = []
            new_incoming_events = []
            for eid, ev in unique_events.items():
                if eid not in existing_ids:
                    to_insert.append(EventLog(
                        event_id=ev.event_id,
                        event_type=ev.event_type,
                        event_time=ev.event_time,
                        client_id=ev.client_id,
                        account_id=ev.account_id,
                        payload=ev.payload,
                        source=self.source
                    ))
                    new_incoming_events.append(ev)

            inserted = 0
            if to_insert:
                created_objs = EventLog.objects.bulk_create(to_insert, ignore_conflicts=True)
                inserted = len(created_objs)

            # Синхронизируем только новые события с графом Neo4j
            if new_incoming_events:
                self.graph_client.sync_batch(new_incoming_events)

            duplicates = len(events) - inserted
            logger.info(f"Сохранено в БД и Neo4j: {inserted}, дубликатов отброшено: {duplicates}")
            return SaveResult(inserted, duplicates)

    def save_rejected(self, rejections: List[Rejection]) -> None:
        if not rejections:
            return

        close_old_connections()
        to_insert = []
        for r in rejections:
            raw_text = r.raw.value.decode('utf-8', errors='replace') if r.raw.value else ""
            to_insert.append(RejectedEvent(
                raw=raw_text,
                reason=r.reason,
                topic=r.raw.topic,
                partition=r.raw.partition,
                offset=r.raw.offset
            ))

        if to_insert:
            RejectedEvent.objects.bulk_create(to_insert)
        logger.warning(f"Записано в DLQ (отклонено) сообщений: {len(to_insert)}")
