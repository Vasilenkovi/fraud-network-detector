from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from api.models import FraudAlert, FraudAlertDecision


class AlertApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="analyst", password="test-password-123")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.alert = FraudAlert.objects.create(
            alert_id="AL-TEST", fingerprint="a" * 64, scheme="shared_device",
            reason="Тестовое общее устройство", graph_ref={},
        )

    def test_list_requires_authentication(self):
        client = APIClient()
        response = client.get("/api/alerts/")
        self.assertEqual(response.status_code, 403)

    def test_list_returns_alert(self):
        response = self.client.get("/api/alerts/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["id"], "AL-TEST")

    def test_rejected_decision_requires_comment(self):
        response = self.client.post(
            "/api/alerts/AL-TEST/decision/", {"status": "rejected", "comment": ""}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(FraudAlertDecision.objects.count(), 0)

    def test_confirmed_decision_is_audited(self):
        response = self.client.post(
            "/api/alerts/AL-TEST/decision/", {"status": "confirmed", "comment": "Проверено"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.status, FraudAlert.Status.CONFIRMED)
        self.assertEqual(FraudAlertDecision.objects.count(), 1)
