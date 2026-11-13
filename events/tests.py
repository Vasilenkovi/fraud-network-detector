import pytest
from datetime import datetime, timezone
from events.sink import DjangoEventSink
from events.contracts import IncomingEvent
from events.models import EventLog
from unittest.mock import MagicMock

@pytest.mark.django_db
def test_save_batch_and_ignore_duplicates():
    
    sink = DjangoEventSink()
    
    event = IncomingEvent(
        event_id="test-unique-id-123",
        event_type="transfer",
        event_time=datetime.now(timezone.utc),
        client_id="client-1",
        account_id="acc-1",
        payload={"amount": 100}
    )
   
    result1 = sink.save_batch([event])
    assert result1.inserted == 1
    assert result1.duplicates == 0
    assert EventLog.objects.count() == 1
    
    result2 = sink.save_batch([event])
    assert result2.inserted == 0
    assert result2.duplicates == 1
    assert EventLog.objects.count() == 1

@pytest.mark.django_db
def test_save_rejected_events():
    
    sink = DjangoEventSink()
    
    from events.contracts import RawMessage, Rejection
    raw = RawMessage(value=b'{"broken_json":', topic="events", partition=0, offset=10)
    rejection = Rejection(raw=raw, reason="Ошибка парсинга JSON")
    
    sink.save_rejected([rejection])
    
    from events.models import RejectedEvent
    assert RejectedEvent.objects.count() == 1
    assert RejectedEvent.objects.first().reason == "Ошибка парсинга JSON"

    from unittest.mock import MagicMock
from events.consumer import KafkaEventConsumer
import json

def test_consumer_processes_messages():

    mock_sink = MagicMock()
    
    config = {
        'TOPIC': 'test-topic',
        'BATCH_SIZE': 10,
        'POLL_TIMEOUT': 0.1,
        'BOOTSTRAP_SERVERS': 'localhost:9092',
        'GROUP_ID': 'test-group'
    }
    
    consumer = KafkaEventConsumer(sink=mock_sink, config=config)
    
    fake_msg = MagicMock()
    fake_msg.value.return_value = json.dumps({
        "event_id": "ev-1", "event_type": "login", 
        "timestamp": 1700000000000, "client_id": "c-1", "account_id": "a-1"
    }).encode('utf-8')
    fake_msg.error.return_value = None
    fake_msg.topic.return_value = "test-topic"
    fake_msg.partition.return_value = 0
    fake_msg.offset.return_value = 100
    
    consumer.consumer = MagicMock()
    consumer.consumer.consume.side_effect = [[fake_msg], []]
    
    import threading
    stop_event = threading.Event()
    
    def stop_after_first(*args, **kwargs):
        stop_event.set()
    
    mock_sink.save_batch.side_effect = stop_after_first
    
    consumer.run(stop_event)
    
    assert mock_sink.save_batch.call_count == 1
    args, _ = mock_sink.save_batch.call_args
    incoming_events = args[0]
    
    assert len(incoming_events) == 1
    assert incoming_events[0].event_id == "ev-1"
    assert incoming_events[0].event_type == "login"