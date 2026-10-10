"""Event definitions shared by protocols and environments."""

from collections.abc import Callable
from typing import ClassVar

type EventId = str


class BaseEvent:
    event_id: ClassVar[EventId]


type EventHandler[E: BaseEvent] = Callable[[E], None]
