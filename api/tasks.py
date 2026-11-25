from celery import shared_task
from django.utils import timezone

from events.fraud_detection import detect_and_persist
from .models import ReplayRun


@shared_task(bind=True, name="api.replay_events")
def replay_events(self, replay_run_id: str):
    run = ReplayRun.objects.get(pk=replay_run_id)
    run.status = ReplayRun.Status.RUNNING
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at"])
    try:
        result = detect_and_persist(start_time=run.start_time, end_time=run.end_time)
        run.status = ReplayRun.Status.SUCCEEDED
        run.result = result
        return result
    except Exception as exc:
        run.status = ReplayRun.Status.FAILED
        run.error = str(exc)[:5000]
        raise
    finally:
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "result", "error", "finished_at"])
