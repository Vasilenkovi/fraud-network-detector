import json
import logging
import threading
from typing import List
from confluent_kafka import Consumer, KafkaError, KafkaException
from events.contracts import EventSink, RawMessage, IncomingEvent, Rejection, BaseEventSchema

logger = logging.getLogger('events')


class KafkaEventConsumer:
    def __init__(self, sink: EventSink, config: dict):
        self.sink = sink
        self.topic = config['TOPIC']
        self.batch_size = config['BATCH_SIZE']
        self.poll_timeout = config['POLL_TIMEOUT']

        # Настройки для подключения к confluent-kafka
        kafka_config = {
            'bootstrap.servers': config['BOOTSTRAP_SERVERS'],
            'group.id': config['GROUP_ID'],
            'auto.offset.reset': 'earliest',
            'enable.auto.commit': False  # Будем контролировать коммиты вручную
        }
        self.consumer = Consumer(kafka_config)

    def run(self, stop_event: threading.Event):
        try:
            self.consumer.subscribe([self.topic])
            logger.info(f"Успешная подписка на топик Kafka: {self.topic}")

            while not stop_event.is_set():
                # Читаем пачку сообщений из брокера
                messages = self.consumer.consume(num_messages=self.batch_size, timeout=self.poll_timeout)
                if not messages:
                    continue

                valid_events: List[IncomingEvent] = []
                rejected_events: List[Rejection] = []

                for msg in messages:
                    if msg.error():
                        if msg.error().code() == KafkaError._PARTITION_EOF:
                            continue
                        else:
                            raise KafkaException(msg.error())

                    # Формируем промежуточный Raw-объект
                    raw_msg = RawMessage(
                        value=msg.value(),
                        topic=msg.topic(),
                        partition=msg.partition(),
                        offset=msg.offset()
                    )

                    try:
                        # 1. Декодируем и парсим JSON
                        data = json.loads(msg.value().decode('utf-8'))

                        # 2. Валидируем через Pydantic-схему
                        validated_data = BaseEventSchema.model_validate(data)

                        # 3. Преобразуем в контракт IncomingEvent
                        valid_events.append(validated_data.to_incoming_event())
                    except Exception as e:
                        # Если упали на любой стадии (битый JSON, нет обязательных полей)
                        reason = f"Ошибка валидации схемы: {str(e)}"
                        rejected_events.append(Rejection(raw=raw_msg, reason=reason))

                # Записываем валидные события в БД
                if valid_events:
                    self.sink.save_batch(valid_events)

                # Записываем отклонённые сообщения в БД (DLQ)
                if rejected_events:
                    self.sink.save_rejected(rejected_events)

                # Фиксируем смещение (офсеты) в Kafka только после успешной записи всей пачки в БД
                self.consumer.commit(asynchronous=False)

        finally:
            self.consumer.close()
            logger.info("Соединение с брокером Kafka закрыто.")


def build_consumer(sink: EventSink, config: dict) -> KafkaEventConsumer:
    """Фабричный метод для сборки и возврата объекта консьюмера"""
    return KafkaEventConsumer(sink=sink, config=config)
