import signal
import threading
from django.core.management.base import BaseCommand
from django.conf import settings
from events.sink import DjangoEventSink
from events.consumer import build_consumer


class Command(BaseCommand):
    help = "Читает входящие финансовые события из брокера Kafka и записывает их в журнал"

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            help='Переопределить размер пачки обработки сообщений'
        )

    def handle(self, *args, **options):
        config = settings.KAFKA.copy()
        if options['batch_size']:
            config['BATCH_SIZE'] = options['batch_size']

        self.stdout.write(self.style.SUCCESS(
            f"Запуск Consumer. Слушаем топик: {config['TOPIC']}"
        ))

        stop_event = threading.Event()

        # Корректный перехват системных сигналов для плавного завершения (Graceful Shutdown)
        def handler(signum, frame):
            self.stdout.write(self.style.WARNING(
                "\nПолучен сигнал остановки. Дорабатываем текущую пачку и завершаем работу..."
            ))
            stop_event.set()

        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

        try:
            # Вызываем фабрику сборки консьюмера
            consumer = build_consumer(sink=DjangoEventSink(source='kafka'), config=config)
            consumer.run(stop_event)
        except NotImplementedError as e:
            self.stdout.write(self.style.ERROR(f"Ошибка: {e}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Критический сбой: {e}"))

        self.stdout.write(self.style.SUCCESS("Работа скрипта приёма успешно завершена."))
