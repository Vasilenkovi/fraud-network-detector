import pytest
from generator.generator import make_event, generate_base_entities

def test_make_event_structure():
    client = {"client_id": "c-1", "account_id": "a-1"}
    
    event = make_event(
        event_type="transfer", 
        client=client, 
        target_account="a-2", 
        amount=5000
    )
    
    assert event["event_type"] == "transfer"
    assert event["client_id"] == "c-1"
    assert event["account_id"] == "a-1"
    assert event["target_account_id"] == "a-2"
    assert event["amount"] == 5000
    assert "event_id" in event
    assert "timestamp" in event

def test_generate_entities():
    clients = generate_base_entities(num_clients=5)
    assert len(clients) == 5
    assert "client_id" in clients[0]
    assert "devices" in clients[0]