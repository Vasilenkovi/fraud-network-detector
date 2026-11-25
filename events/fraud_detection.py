"""Reusable rule-based detectors; shared by the CLI command and API Replay."""
import hashlib
from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from .models import EventLog
from api.models import FraudAlert


def _fingerprint(scheme, event_ids, extra=None):
    raw = "|".join([scheme, *(sorted(event_ids)), str(extra or "")])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _candidate(scheme, reason, features, participants, client_ids, account_ids, device_ids=None, event_ids=None):
    event_ids = sorted(set(event_ids or []))
    client_ids = sorted(set(filter(None, client_ids)))
    account_ids = sorted(set(filter(None, account_ids)))
    device_ids = sorted(set(filter(None, device_ids or [])))
    fingerprint_events = [] if scheme == "shared_device" else event_ids
    fp = _fingerprint(scheme, fingerprint_events, ",".join(device_ids + client_ids))
    return {
        "fingerprint": fp,
        "alert_id": f"AL-{fp[:12].upper()}",
        "scheme": scheme,
        "reason": reason,
        "features": features,
        "participants": participants,
        "graph_ref": {
            "client_ids": client_ids,
            "account_ids": account_ids,
            "device_ids": device_ids,
            "event_ids": event_ids,
        },
    }


def detect_candidates(events):
    events = list(events)
    candidates = []

    # Scheme 1: at least three distinct clients observed from one device.
    device_clients = defaultdict(set)
    device_events = defaultdict(list)
    for event in events:
        device_id = event.payload.get("device_id")
        if device_id:
            device_clients[device_id].add(event.client_id)
            device_events[device_id].append(event)

    for device_id, clients in device_clients.items():
        if len(clients) >= 3:
            related = device_events[device_id]
            client_ids = sorted(clients)
            candidates.append(_candidate(
                scheme="shared_device",
                reason=f"С одного устройства {device_id} зафиксирована активность {len(clients)} клиентов",
                features=[{"name": "shared_device", "description": f"{len(clients)} клиентов используют одно устройство"}],
                participants=[{"client_id": cid, "role": "Участник"} for cid in client_ids],
                client_ids=client_ids,
                account_ids=[e.account_id for e in related],
                device_ids=[device_id],
                event_ids=[e.event_id for e in related],
            ))

    # Schemes 2 and 3: A->B->C->D and A->B->C->A, with <=2 sec per hop.
    transfers = sorted((e for e in events if e.event_type == "transfer"), key=lambda e: e.event_time)
    account_to_client = {}
    for event in events:
        account_to_client[event.account_id] = event.client_id

    for first in transfers:
        acc_b = first.payload.get("target_account_id")
        client_b = account_to_client.get(acc_b)
        if not acc_b or not client_b:
            continue
        for second in transfers:
            if second.account_id != acc_b:
                continue
            delta_1 = second.event_time - first.event_time
            if not (0 < delta_1.total_seconds() <= 2):
                continue
            acc_c = second.payload.get("target_account_id")
            client_c = account_to_client.get(acc_c)
            if not acc_c or not client_c:
                continue
            for third in transfers:
                if third.account_id != acc_c:
                    continue
                delta_2 = third.event_time - second.event_time
                if not (0 < delta_2.total_seconds() <= 2):
                    continue
                acc_d = third.payload.get("target_account_id")
                client_d = account_to_client.get(acc_d)
                if not acc_d or not client_d:
                    continue

                is_cycle = client_d == first.client_id
                scheme = "cycle_transfer" if is_cycle else "fast_chain"
                client_path = [first.client_id, client_b, client_c] + ([first.client_id] if is_cycle else [client_d])
                account_path = [first.account_id, acc_b, acc_c] + ([first.account_id] if is_cycle else [acc_d])
                related_events = [first, second, third]
                description = "Замкнутый круг A→B→C→A" if is_cycle else "Быстрый транзит A→B→C→D"
                candidates.append(_candidate(
                    scheme=scheme,
                    reason=f"Обнаружена схема {description} с интервалом не более 2 секунд между переводами",
                    features=[{"name": scheme, "description": description}],
                    participants=[{"client_id": cid, "role": "Участник"} for cid in sorted(set(client_path))],
                    client_ids=client_path,
                    account_ids=account_path,
                    event_ids=[e.event_id for e in related_events],
                ))

    # The same three transfers can be reached through repeated loops; persist once.
    unique = {item["fingerprint"]: item for item in candidates}
    return list(unique.values())


@transaction.atomic
def persist_candidates(candidates):
    created = 0
    updated = 0
    for item in candidates:
        _, was_created = FraudAlert.objects.update_or_create(
            fingerprint=item["fingerprint"],
            defaults={
                "alert_id": item["alert_id"],
                "scheme": item["scheme"],
                "reason": item["reason"],
                "features": item["features"],
                "participants": item["participants"],
                "graph_ref": item["graph_ref"],
            },
        )
        created += int(was_created)
        updated += int(not was_created)
    return {"detected": len(candidates), "created": created, "updated": updated}


def detect_and_persist(start_time=None, end_time=None):
    queryset = EventLog.objects.all().order_by("event_time", "seq")
    if start_time is not None:
        queryset = queryset.filter(event_time__gte=start_time)
    if end_time is not None:
        queryset = queryset.filter(event_time__lte=end_time)
    events = list(queryset)
    candidates = detect_candidates(events)
    result = persist_candidates(candidates)
    result["events_analyzed"] = len(events)
    result["analyzed_at"] = timezone.now().isoformat()
    return result
