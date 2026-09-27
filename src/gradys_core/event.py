from typing import ClassVar, Callable, Optional

type EventId = str


class BaseEvent:
    event_id: ClassVar[EventId]


type EventHandler[E: BaseEvent] = Callable[[E], None]

type EventSubscriber = Callable[[Callable[[BaseEvent], None]], None]

class EventHandle[E: BaseEvent]:
    def __init__(self, get_subscriber: Callable[[], Optional[EventSubscriber]]):
        self._get_subscriber = get_subscriber

    def subscribe(self, handler: Callable[[E], None]) -> None:
        subscriber = self._get_subscriber()
        if subscriber is None:
            raise RuntimeError("Event subscriber is not set. Protocol might not be linked.")
        subscriber(handler)