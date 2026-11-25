import typing_extensions
from typing import List, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timezone
from pydantic import BaseModel, Field, field_validator, ConfigDict


@dataclass(frozen=True)
class RawMessage:
    value: bytes
    topic: str
    partition: int
    offset: int

@dataclass(frozen=True)
class IncomingEvent:
    event_id: str
    event_type: str
    event_time: datetime
    client_id: str
    account_id: str
    payload: dict

@dataclass(frozen=True)
class Rejection:
    raw: RawMessage
    reason: str

@dataclass(frozen=True)
class SaveResult:
    inserted: int
    duplicates: int

@typing_extensions.runtime_checkable
class EventSink(typing_extensions.Protocol):
    def save_batch(self, events: List[IncomingEvent]) -> SaveResult: ...
    def save_rejected(self, rejections: List[Rejection]) -> None: ...

# --- Новые Pydantic-схемы для валидации структуры генератора ---

class BaseEventSchema(BaseModel):
    # Разрешаем любые дополнительные поля от генератора
    model_config = ConfigDict(extra='allow')

    event_id: str
    event_type: str
    timestamp: int  # Оставляем строго int, никаких валидаторов на изменение типа!
    client_id: str
    account_id: str

    # Опциональные поля
    device_id: Optional[str] = None
    ip_address: Optional[str] = None
    target_account_id: Optional[str] = None
    amount: Optional[float] = None

    def to_incoming_event(self) -> IncomingEvent:
        # Конвертируем миллисекунды в datetime прямо здесь, не трогая тип в схеме
        dt_object = datetime.fromtimestamp(self.timestamp / 1000.0, tz=timezone.utc)

        return IncomingEvent(
            event_id=self.event_id,
            event_type=self.event_type,
            event_time=dt_object,
            client_id=self.client_id,
            account_id=self.account_id,
            payload=self.model_dump()  # Теперь model_dump отработает идеально без варнингов
        )