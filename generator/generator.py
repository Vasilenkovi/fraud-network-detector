import json
import time
import random
import uuid
import argparse
import os
from datetime import datetime
from faker import Faker
from kafka import KafkaProducer

KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
KAFKA_TOPIC = os.getenv('KAFKA_TOPIC', 'fraud-events')
MANIFEST_FILE = 'fraud_manifest.json'

fake = Faker('ru_RU')

def setup_kafka():
    """Настройка подключения к Kafka"""
    try:
        producer = KafkaProducer(
            bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            linger_ms=10
        )
        print(f"✅ Подключено к Kafka: {KAFKA_BOOTSTRAP_SERVERS}")
        return producer
    except Exception as e:
        print(f"❌ Ошибка подключения к Kafka: {e}")
        print("Убедитесь, что Kafka запущена (docker-compose up).")
        exit(1)

def generate_base_entities(num_clients=20):
    """Создает базовый справочник клиентов, счетов и устройств"""
    clients = []
    for _ in range(num_clients):
        client_id = str(uuid.uuid4())
        clients.append({
            "client_id": client_id,
            "name": fake.name(),
            "account_id": str(uuid.uuid4()),
            "devices": [str(uuid.uuid4()) for _ in range(random.randint(1, 2))],
            "ips": [fake.ipv4() for _ in range(random.randint(1, 2))]
        })
    return clients

def make_event(event_type, client, target_account=None, device=None, ip=None, amount=None):
    """Формирует структуру события"""
    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "timestamp": int(datetime.now().timestamp() * 1000), 
        "client_id": client["client_id"],
        "account_id": client["account_id"],
    }
    if device: event["device_id"] = device
    if ip: event["ip_address"] = ip
    if target_account: event["target_account_id"] = target_account
    if amount: event["amount"] = amount
    return event

def send_event(producer, event):
    """Отправка в Kafka"""
    producer.send(KAFKA_TOPIC, event)
    return event

def scenario_shared_device(producer, clients):
    """Схема 1: 3 клиента заходят с одного устройства (Shared Device)"""
    fraud_device = str(uuid.uuid4())
    fraud_ip = fake.ipv4()
    victims = random.sample(clients, 3)
    
    events = []
    for client in victims:
        ev = make_event("login", client, device=fraud_device, ip=fraud_ip)
        send_event(producer, ev)
        events.append(ev["event_id"])
        time.sleep(0.1)
        
    return {
        "type": "shared_device",
        "participants": [c["client_id"] for c in victims],
        "events": events,
        "device_id": fraud_device
    }

def scenario_fast_chain(producer, clients):
    """Схема 2: Быстрая цепочка переводов (A -> B -> C -> D)"""
    chain = random.sample(clients, 4)
    amount = 100000
    events = []
    
    for i in range(3):
        source = chain[i]
        target = chain[i+1]
        ev = make_event(
            "transfer", source, target_account=target["account_id"], 
            amount=amount, device=source["devices"][0], ip=source["ips"][0]
        )
        send_event(producer, ev)
        events.append(ev["event_id"])
        time.sleep(0.1)
        
    return {
        "type": "fast_chain",
        "participants": [c["client_id"] for c in chain],
        "events": events
    }

def scenario_cycle(producer, clients):
    """Схема 3: Замкнутый круг (A -> B -> C -> A)"""
    cycle = random.sample(clients, 3)
    amount = 50000
    events = []
    
    for i in range(3):
        source = cycle[i]
        target = cycle[(i + 1) % 3]
        ev = make_event(
            "transfer", source, target_account=target["account_id"], 
            amount=amount, device=source["devices"][0], ip=source["ips"][0]
        )
        send_event(producer, ev)
        events.append(ev["event_id"])
        time.sleep(0.1)
        
    return {
        "type": "cycle_transfer",
        "participants": [c["client_id"] for c in cycle],
        "events": events
    }

def normal_behavior(producer, clients):
    """Обычное поведение (шум)"""
    client = random.choice(clients)
    device = random.choice(client["devices"])
    ip = random.choice(client["ips"])
    
    send_event(producer, make_event("login", client, device=device, ip=ip))
    
    target = random.choice([c for c in clients if c["client_id"] != client["client_id"]])
    send_event(producer, make_event(
        "transfer", client, target_account=target["account_id"], 
        amount=random.randint(100, 5000)
    ))


def main():
    parser = argparse.ArgumentParser(description="Генератор событий для Fraud Graph")
    parser.add_argument("--seed", type=int, help="Seed для повторяемости (ФТ-52)", default=None)
    parser.add_argument("--clients", type=int, default=20, help="Кол-во клиентов")
    parser.add_argument("--fraud-rate", type=float, default=0.15, help="Доля мошенничества (0.0 - 1.0)")
    parser.add_argument("--duration", type=int, default=60, help="Время работы в секундах (0 = бесконечно)")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)
        Faker.seed(args.seed)
        print(f"🎲 Используется Seed: {args.seed}")

    producer = setup_kafka()
    clients = generate_base_entities(args.clients)
    
    manifest = {"schemes": []}
    start_time = time.time()
    
    print(f"🚀 Генерация запущена (клиентов: {args.clients}, доля мошенничества: {args.fraud_rate*100}%)")
    print(f"📁 Манифест будет сохранен в: {MANIFEST_FILE}")
    
    try:
        while True:
            if args.duration > 0 and (time.time() - start_time) > args.duration:
                print("⏱️ Время работы вышло.")
                break
                
            r = random.random()
            
            if r < (1.0 - args.fraud_rate):
                normal_behavior(producer, clients)
            else:
                fraud_type = random.choice(["shared_device", "fast_chain", "cycle"])
                
                if fraud_type == "shared_device":
                    scheme = scenario_shared_device(producer, clients)
                elif fraud_type == "fast_chain":
                    scheme = scenario_fast_chain(producer, clients)
                else:
                    scheme = scenario_cycle(producer, clients)
                    
                print(f"⚠️ Внедрена схема: {scheme['type']}")
                manifest["schemes"].append(scheme)
                
            time.sleep(random.uniform(0.1, 0.5))
            
    except KeyboardInterrupt:
        print("\n🛑 Остановка по Ctrl+C...")
    finally:
        producer.flush()
        producer.close()
        
        with open(MANIFEST_FILE, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        print(f"💾 Манифест сохранен (схем: {len(manifest['schemes'])})")

if __name__ == "__main__":
    main()