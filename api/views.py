from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone

from .models import FraudAlert, ReplayRun
from .serializers import (
    AlertDecisionSerializer,
    AlertFullSerializer,
    AlertShortSerializer,
    ReplayCreateSerializer,
    ReplayRunSerializer,
)
from .services import get_alert_graph, record_decision


class AlertListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = FraudAlert.objects.all()
        alert_status = request.query_params.get("status")
        if alert_status:
            if alert_status not in FraudAlert.Status.values:
                return Response({"detail": "Недопустимый status."}, status=status.HTTP_400_BAD_REQUEST)
            queryset = queryset.filter(status=alert_status)
        scheme = request.query_params.get("scheme")
        if scheme:
            queryset = queryset.filter(scheme=scheme)

        try:
            limit = min(max(int(request.query_params.get("limit", 50)), 1), 200)
            offset = max(int(request.query_params.get("offset", 0)), 0)
        except ValueError:
            return Response({"detail": "limit и offset должны быть целыми числами."}, status=status.HTTP_400_BAD_REQUEST)

        total = queryset.count()
        items = queryset[offset:offset + limit]
        return Response({
            "count": total,
            "limit": limit,
            "offset": offset,
            "results": AlertShortSerializer(items, many=True).data,
        })


class AlertDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, alert_id):
        alert = get_object_or_404(FraudAlert, alert_id=alert_id)
        data = AlertFullSerializer(alert).data
        try:
            data["graph"] = get_alert_graph(alert)
        except Exception:
            # Не маскируем проблему как 404: запись инцидента остаётся доступной,
            # а отсутствие графового хранилища явно отражается в ответе.
            return Response({"detail": "Не удалось получить подграф из Neo4j."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(data)


class AlertDecisionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, alert_id):
        alert = get_object_or_404(FraudAlert, alert_id=alert_id)
        serializer = AlertDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        decision = record_decision(
            alert=alert,
            analyst=request.user,
            status=serializer.validated_data["status"],
            comment=serializer.validated_data.get("comment", ""),
        )
        return Response({
            "id": alert.alert_id,
            "status": decision.status,
            "decision_id": decision.pk,
            "created_at": decision.created_at,
        }, status=status.HTTP_200_OK)


class ReplayCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ReplayCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = ReplayRun.objects.create(
            requested_by=request.user,
            start_time=serializer.validated_data["start_time"],
            end_time=serializer.validated_data["end_time"],
        )
        from .tasks import replay_events
        try:
            replay_events.apply_async(args=[str(run.pk)], task_id=str(run.pk))
        except Exception:
            run.status = ReplayRun.Status.FAILED
            run.error = "Не удалось поставить задачу в очередь. Проверьте доступность Redis/Celery."
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "error", "finished_at"])
            return Response(ReplayRunSerializer(run).data, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(ReplayRunSerializer(run).data, status=status.HTTP_202_ACCEPTED)


class ReplayDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, task_id):
        run = get_object_or_404(ReplayRun, pk=task_id)
        return Response(ReplayRunSerializer(run).data)
