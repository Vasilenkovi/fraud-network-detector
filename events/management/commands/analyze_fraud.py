from django.core.management.base import BaseCommand

from events.fraud_detection import detect_and_persist


class Command(BaseCommand):
    help = "Анализирует журнал событий и сохраняет найденные мошеннические группы в PostgreSQL"

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Запуск аналитического модуля Fraud Graph..."))
        result = detect_and_persist()
        self.stdout.write(f"Проанализировано событий: {result['events_analyzed']}")
        self.stdout.write(f"Обнаружено групп: {result['detected']}")
        self.stdout.write(self.style.SUCCESS(
            f"Новых: {result['created']}; обновлено: {result['updated']}"
        ))
