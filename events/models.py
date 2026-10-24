from django.db import models


class EventLog(models.Model):
    class EventTypes(models.TextChoices):
        TRANSACTION = 'transfer', 'Перевод'
        LOGIN = 'login', 'Вход'
        ACCOUNT_OPENED = 'account_opened', 'Открытие счета'

    seq = models.BigAutoField(
        primary_key=True,
        verbose_name="Порядковый номер приёма"
    )
    event_id = models.CharField(
        max_length=64,
        unique=True,
        verbose_name="ID события"
    )
    event_type = models.CharField(
        max_length=32,
        choices=EventTypes.choices,
        verbose_name="Тип события"
    )
    event_time = models.DateTimeField(
        db_index=True,
        verbose_name="Время события (UTC)"
    )

    # Индексируемые поля для быстрого построения Fraud-графа прямо из БД
    client_id = models.CharField(
        max_length=64,
        db_index=True,
        verbose_name="ID клиента"
    )
    account_id = models.CharField(
        max_length=64,
        db_index=True,
        verbose_name="ID счета"
    )

    payload = models.JSONField(
        verbose_name="Исходное сообщение целиком"
    )
    source = models.CharField(
        max_length=16,
        default='kafka',
        verbose_name="Источник"
    )
    received_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Время приёма системой"
    )

    class Meta:
        verbose_name = "Журнал событий"
        verbose_name_plural = "Журнал событий"
        ordering = ['seq']
        # Составной индекс для эффективного анализа цепочек фрода по времени
        indexes = [
            models.Index(fields=['event_type', 'event_time']),
        ]

    def __str__(self):
        return f"{self.get_event_type_display()} #{self.seq} ({self.event_id})"


class RejectedEvent(models.Model):
    raw = models.TextField(
        verbose_name="Исходный текст сообщения"
    )
    reason = models.TextField(
        verbose_name="Причина отказа"
    )
    topic = models.CharField(
        max_length=255,
        verbose_name="Топик Kafka"
    )
    partition = models.IntegerField(
        verbose_name="Партиция"
    )
    offset = models.BigIntegerField(
        verbose_name="Офсет"
    )
    received_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Время приёма"
    )

    class Meta:
        verbose_name = "Отклонённое событие"
        verbose_name_plural = "Отклонённые события"
        ordering = ['-received_at']

    def __str__(self):
        return f"Отказ {self.id}: {self.reason[:30]}..."
