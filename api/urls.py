from django.urls import path

from .views import (
    AlertDecisionView,
    AlertDetailView,
    AlertListView,
    ReplayCreateView,
    ReplayDetailView,
)

urlpatterns = [
    path("alerts/", AlertListView.as_view(), name="alert-list"),
    path("alerts/<str:alert_id>/", AlertDetailView.as_view(), name="alert-detail"),
    path("alerts/<str:alert_id>/decision/", AlertDecisionView.as_view(), name="alert-decision"),
    path("replay/", ReplayCreateView.as_view(), name="replay-create"),
    path("replay/<uuid:task_id>/", ReplayDetailView.as_view(), name="replay-detail"),
]
