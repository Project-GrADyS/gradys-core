"""Typed command and event primitives used by protocol implementations."""

from typing import Optional, Protocol

from gradys_core.connection import Sender, Subscriber, Subscription
from gradys_core.connection.subscriber import SubscriptionOptions
from gradys_core.primitives import BaseCommand, BaseEvent, EventHandler


class CommandHandle[C: BaseCommand]:
    """
    A handle to send commands of a specific type. The handle is created by the protocol and can be used to send commands
    of the specified type to the environment. The handle is type-safe and ensures that only commands of the specified
    type can be sent.
    """

    def __init__(self, command_type: type[C], sender: Sender) -> None:
        self._command = command_type
        self._sender = sender

    def send(self, command: C) -> None:
        if not isinstance(command, self._command):
            raise TypeError(f"Command must be of type {self._command.__name__}, got {type(command).__name__}")
        self._sender.send(command)


class EventHandle[E: BaseEvent]:
    """
    A handle to subscribe to events of a specific type. The handle is created by the protocol and can be used to
    subscribe to events of the specified type from the environment.
    """

    def __init__(self, event_type: type[E], subscriber: Subscriber):
        self._event = event_type
        self._subscriber = subscriber

    def subscribe(self, handler: EventHandler[E], *, options: Optional[SubscriptionOptions] = None) -> Subscription:
        return self._subscriber.subscribe(self._event, handler, options)

class _SenderSubscriber(Sender, Subscriber, Protocol): ...

class QueryHandle[C: BaseCommand, R: BaseEvent]:
    """
    A handle to send queries of a specific type. The handle is created by the protocol and
    can be used to send queries of the specified type to the environment. The handle is type-safe and ensures that
    only queries of the specified type can be sent.
    """
    def __init__(self, query_type: type[C], response_type: type[R], querier: _SenderSubscriber):
        self._query = query_type
        self._response = response_type
        self._querier = querier

    def request(self, command: C, on_response: EventHandler[R]) -> Subscription:
        """Send a query and deliver the next response event to the handler."""
        if not isinstance(command, self._query):
            raise TypeError(f"Query must be of type {self._query.__name__}, got {type(command).__name__}")
        
        subscription = self._querier.subscribe(self._response,
                                               on_response, 
                                               options=SubscriptionOptions(once=True))
        self._querier.send(command)
        return subscription
