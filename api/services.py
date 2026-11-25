from django.db import transaction
from django.utils import timezone

from events.neo4j_client import Neo4jGraphClient
from .models import FraudAlert, FraudAlertDecision


def get_alert_graph(alert: FraudAlert) -> dict:
    """Fetch only the graph fragment referenced by this alert from Neo4j."""
    ref = alert.graph_ref or {}
    client = Neo4jGraphClient(initialize_constraints=False)
    try:
        return client.get_subgraph(
            client_ids=ref.get("client_ids", []),
            account_ids=ref.get("account_ids", []),
            device_ids=ref.get("device_ids", []),
            event_ids=ref.get("event_ids", []),
        )
    finally:
        client.close()


@transaction.atomic
def record_decision(*, alert: FraudAlert, analyst, status: str, comment: str) -> FraudAlertDecision:
    alert = FraudAlert.objects.select_for_update().get(pk=alert.pk)
    decision = FraudAlertDecision.objects.create(
        alert=alert, analyst=analyst, status=status, comment=comment
    )
    alert.status = status
    alert.save(update_fields=["status", "updated_at"])
    return decision
