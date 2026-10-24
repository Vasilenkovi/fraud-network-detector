import logging
from typing import List
from django.db import transaction, close_old_connections
from .contracts import EventSink, IncomingEvent, Rejection, SaveResult
from .models import EventLog, RejectedEvent

logger = logging.getLogger('events')


class DjangoEventSink(EventSink):
    def __init__(self, source: str = 'kafka'):
        self.source = source

    def save_batch(self, events: List[IncomingEvent]) -> SaveResult:
        if not events:
            return SaveResult(0, 0)

        # 1. Закрываем устаревшие соединения
        close_old_connections()

        # 2. Локальная дедупликация внутри пришедшей пачки (оставляем первое вхождение)
        unique_events = {}
        for ev in events:
            if ev.event_id not in unique_events:
                unique_events[ev.event_id] = ev

        event_ids = list(unique_events.keys())

        with transaction.atomic():
            # 3. Находим ID событий, которые уже есть в базе данных
            existing_ids = set(
                EventLog.objects.filter(event_id__in=event_ids)
                .values_list('event_id', flat=True)
            )

            # 4. Формируем список объектов для bulk_create
            to_insert = []
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

            if to_insert:
                EventLog.objects.bulk_create(to_insert, ignore_conflicts=True)

            inserted = len(to_insert)
            duplicates = len(events) - inserted

            logger.info(f"Сохранено событий: {inserted}, дубликатов отброшено: {duplicates}")
            return SaveResult(inserted, duplicates)

    def save_rejected(self, rejections: List[Rejection]) -> None:
        if not rejections:
            return

        close_old_connections()
        to_insert = []
        for r in rejections:
            # Безопасное декодирование строк из байтов
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
