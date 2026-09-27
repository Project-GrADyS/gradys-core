from typing import ClassVar, Callable, Protocol

type EventId = str

class BaseEvent:
    event_id: ClassVar[EventId]

type EventHandler[E: BaseEvent] = Callable[[E], None]

class EventSubscriber(Protocol):
    def __call__[E: BaseEvent](self, event: type[E], handler: Callable[[E], None], /) -> None: ...

class EventHandle[E: BaseEvent]:
    """
    A handle to subscribe to events of a specific type. The handle is created by the protocol and can be used to
    subscribe to events of the specified type from the environment.
    """

    def __init__(self, event: type[E], subscribe: Callable[[type[E], Callable[[E], None]], None]):
        self._event = event
        self._subscribe = subscribe

    def subscribe(self, handler: Callable[[E], None]) -> None:
        self._subscribe(self._event, handler)