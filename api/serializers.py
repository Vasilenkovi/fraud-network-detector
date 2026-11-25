from rest_framework import serializers

from .models import FraudAlert, FraudAlertDecision, ReplayRun


class AlertShortSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="alert_id", read_only=True)

    class Meta:
        model = FraudAlert
        fields = ("id", "risk_score", "status", "reason", "created_at")


class AlertFullSerializer(AlertShortSerializer):
    class Meta(AlertShortSerializer.Meta):
        fields = AlertShortSerializer.Meta.fields + ("features", "participants")


class AlertDecisionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=(FraudAlert.Status.CONFIRMED, FraudAlert.Status.REJECTED))
    comment = serializers.CharField(required=False, allow_blank=True, max_length=5000)

    def validate(self, attrs):
        if attrs["status"] == FraudAlert.Status.REJECTED and not attrs.get("comment", "").strip():
            raise serializers.ValidationError({"comment": "Комментарий обязателен при отклонении инцидента."})
        return attrs


class ReplayCreateSerializer(serializers.Serializer):
    start_time = serializers.DateTimeField()
    end_time = serializers.DateTimeField()

    def validate(self, attrs):
        if attrs["end_time"] <= attrs["start_time"]:
            raise serializers.ValidationError({"end_time": "Время окончания должно быть позже времени начала."})
        return attrs


class ReplayRunSerializer(serializers.ModelSerializer):
    task_id = serializers.UUIDField(source="id", read_only=True)

    class Meta:
        model = ReplayRun
        fields = ("task_id", "start_time", "end_time", "status", "result", "error", "created_at", "started_at", "finished_at")
