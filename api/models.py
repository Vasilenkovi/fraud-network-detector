import uuid

from django.conf import settings
from django.db import models


class FraudAlert(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Новый"
        IN_REVIEW = "in_review", "На проверке"
        CONFIRMED = "confirmed", "Подтверждён"
        REJECTED = "rejected", "Отклонён"

    alert_id = models.CharField(max_length=64, unique=True, db_index=True)
    fingerprint = models.CharField(max_length=64, unique=True)
    scheme = models.CharField(max_length=32, db_index=True)
    # Пока ML/rule-risk калибровка не определена, score остаётся NULL.
    risk_score = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW, db_index=True)
    reason = models.TextField()
    features = models.JSONField(default=list)
    participants = models.JSONField(default=list)
    graph_ref = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self):
        return f"{self.alert_id}: {self.scheme} ({self.status})"


class FraudAlertDecision(models.Model):
    alert = models.ForeignKey(FraudAlert, on_delete=models.CASCADE, related_name="decisions")
    analyst = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="fraud_alert_decisions")
    status = models.CharField(max_length=20, choices=[
        (FraudAlert.Status.CONFIRMED, "Подтверждён"),
        (FraudAlert.Status.REJECTED, "Отклонён"),
    ])
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class ReplayRun(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "В очереди"
        RUNNING = "running", "Выполняется"
        SUCCEEDED = "succeeded", "Завершено"
        FAILED = "failed", "Ошибка"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED, db_index=True)
    result = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
