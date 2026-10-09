"""Event definitions shared by protocols and environments."""

from typing import ClassVar, Callable

type EventId = str


class BaseEvent:
    event_id: ClassVar[EventId]


type EventHandler[E: BaseEvent] = Callable[[E], None]
