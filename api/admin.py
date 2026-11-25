from django.contrib import admin
from .models import FraudAlert, FraudAlertDecision, ReplayRun


class FraudAlertDecisionInline(admin.TabularInline):
    model = FraudAlertDecision
    extra = 0
    readonly_fields = ("analyst", "status", "comment", "created_at")


@admin.register(FraudAlert)
class FraudAlertAdmin(admin.ModelAdmin):
    list_display = ("alert_id", "scheme", "status", "risk_score", "created_at")
    list_filter = ("scheme", "status")
    search_fields = ("alert_id", "reason")
    readonly_fields = ("fingerprint", "created_at", "updated_at")
    inlines = (FraudAlertDecisionInline,)


@admin.register(ReplayRun)
class ReplayRunAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "start_time", "end_time", "created_at")
    readonly_fields = ("id", "created_at", "started_at", "finished_at")
