import collections
from datetime import timedelta
from django.core.management.base import BaseCommand
from events.models import EventLog


class Command(BaseCommand):
    help = "Анализирует журнал событий в БД и выявляет мошеннические графовые схемы (Shared Device, Fast Chain, Cycle)"

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Запуск аналитического модуля Fraud Graph..."))

        # Загружаем все события из базы данных для анализа, отсортированные по времени
        events = list(EventLog.objects.all().order_by('event_time'))
        if not events:
            self.stdout.write(self.style.WARNING("Журнал событий пуст. Запустите генератор и консьюмер!"))
            return

        self.stdout.write(f"Загружено для анализа событий: {len(events)}")

        # Запуск детекторов аномалий
        self._detect_shared_devices(events)
        self._detect_fast_chains_and_cycles(events)

    def _detect_shared_devices(self, events):
        self.stdout.write(self.style.MIGRATE_LABEL("\n--- Проверка схемы 1: Shared Device (Общие устройства) ---"))

        # Группируем уникальных клиентов по устройствам
        device_to_clients = collections.defaultdict(set)
        for ev in events:
            device_id = ev.payload.get('device_id')
            if device_id:
                device_to_clients[device_id].add(ev.client_id)

        found = False
        for device_id, clients in device_to_clients.items():
            # Если с одного устройства заходило 3 или более разных клиентов
            if len(clients) >= 3:
                found = True
                self.stdout.write(self.style.WARNING(
                    f"⚠️ Обнаружено подозрительное устройство! ID: {device_id}\n"
                    f"   С него зафиксирован вход {len(clients)} клиентов: {list(clients)}"
                ))
        if not found:
            self.stdout.write(self.style.SUCCESS("Схем Shared Device не обнаружено."))

    def _detect_fast_chains_and_cycles(self, events):
        self.stdout.write(self.style.MIGRATE_LABEL("\n--- Проверка схем 2 и 3: Быстрые цепочки и Замкнутые круги ---"))

        # Отфильтруем только транзакции перевода денег
        transfers = [ev for ev in events if ev.event_type == 'transfer']

        # Карта для быстрого поиска владельца счета (client_id) по его account_id
        account_to_client = {}
        for ev in events:
            account_to_client[ev.account_id] = ev.client_id

        chains_found = 0
        cycles_found = 0

        for t1 in transfers:
            t1_target_acc = t1.payload.get('target_account_id')
            t1_recipient = account_to_client.get(t1_target_acc)
            if not t1_recipient or not t1_target_acc:
                continue

            # Шаг 2: Ищем перевод денег со счета получателя t1 к кому-то еще
            for t2 in transfers:
                if t2.event_type == 'transfer' and t2.account_id == t1_target_acc:
                    time_diff1 = t2.event_time - t1.event_time
                    if timedelta(0) < time_diff1 <= timedelta(seconds=2):

                        t2_target_acc = t2.payload.get('target_account_id')
                        t2_recipient = account_to_client.get(t2_target_acc)
                        if not t2_recipient or not t2_target_acc:
                            continue

                        # Шаг 3: Ищем перевод денег со счета получателя t2 к кому-то еще
                        for t3 in transfers:
                            if t3.event_type == 'transfer' and t3.account_id == t2_target_acc:
                                time_diff2 = t3.event_time - t2.event_time
                                if timedelta(0) < time_diff2 <= timedelta(seconds=2):

                                    t3_target_acc = t3.payload.get('target_account_id')
                                    t3_recipient = account_to_client.get(t3_target_acc)

                                    # Проверяем на Цикл (Схема 3: A -> B -> C -> A)
                                    if t3_recipient == t1.client_id:
                                        cycles_found += 1
                                        self.stdout.write(self.style.WARNING(
                                            f"   ВЫЯВЛЕН МОШЕННИЧЕСКИЙ ЦИКЛ ПЕРЕВОДОВ!\n"
                                            f"   Цепочка клиентов: {t1.client_id} -> {t2.client_id} -> {t3.client_id} -> {t1.client_id}\n"
                                            f"   Цепочка счетов:   {t1.account_id} -> {t2.account_id} -> {t3.account_id} -> {t1.account_id}"
                                        ))
                                    # Иначе это быстрая цепочка транзита (Схема 2: A -> B -> C -> D)
                                    elif t3_recipient:
                                        chains_found += 1
                                        self.stdout.write(self.style.WARNING(
                                            f"⚠️ ВЫЯВЛЕНА БЫСТРАЯ ЦЕПОЧКА ТРАНЗИТА (Подозрение на обналичивание)!\n"
                                            f"   Траектория клиентов: {t1.client_id} -> {t2.client_id} -> {t3.client_id} -> {t3_recipient}"
                                        ))

        if chains_found == 0:
            self.stdout.write(self.style.SUCCESS("Быстрых цепочек транзита не обнаружено."))
        if cycles_found == 0:
            self.stdout.write(self.style.SUCCESS("Замкнутых кругов перевода не обнаружено."))
