import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="FraudAlert",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("alert_id", models.CharField(db_index=True, max_length=64, unique=True)),
                ("fingerprint", models.CharField(max_length=64, unique=True)),
                ("scheme", models.CharField(db_index=True, max_length=32)),
                ("risk_score", models.FloatField(blank=True, null=True)),
                ("status", models.CharField(choices=[("new", "Новый"), ("in_review", "На проверке"), ("confirmed", "Подтверждён"), ("rejected", "Отклонён")], db_index=True, default="new", max_length=20)),
                ("reason", models.TextField()),
                ("features", models.JSONField(default=list)),
                ("participants", models.JSONField(default=list)),
                ("graph_ref", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="ReplayRun",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("start_time", models.DateTimeField()),
                ("end_time", models.DateTimeField()),
                ("status", models.CharField(choices=[("queued", "В очереди"), ("running", "Выполняется"), ("succeeded", "Завершено"), ("failed", "Ошибка")], db_index=True, default="queued", max_length=16)),
                ("result", models.JSONField(blank=True, default=dict)),
                ("error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("requested_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="FraudAlertDecision",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("confirmed", "Подтверждён"), ("rejected", "Отклонён")], max_length=20)),
                ("comment", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("alert", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="decisions", to="api.fraudalert")),
                ("analyst", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="fraud_alert_decisions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="fraudalert",
            index=models.Index(fields=["status", "created_at"], name="api_frauda_status_5b2a23_idx"),
        ),
    ]
