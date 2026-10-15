"""Typed command, event, and query handles used by protocol implementations."""

from typing import Protocol

from gradys_core.connection import Sender, Subscriber, Subscription
from gradys_core.connection.subscriber import SubscriptionOptions
from gradys_core.primitives import BaseCommand, BaseEvent, EventHandler


class CommandHandle[C: BaseCommand]:
    """Send instances of one command class through a sender.

    Normally obtained from ``ProtocolContext.require_command``. Both static typing
    and a runtime instance check constrain commands to ``C`` or its subclasses.
    """

    def __init__(self, command_type: type[C], sender: Sender) -> None:
        """Bind the accepted command class to its forwarding target.

        Direct construction does not declare or validate environment support;
        ``ProtocolContext.require_command`` performs that step.
        """
        self._command = command_type
        self._sender = sender

    def send(self, command: C) -> None:
        """Forward a command to the connected environment.

        Execution timing and completion belong to the environment. Exceptions
        from the sender propagate to the caller.

        Raises:
            TypeError: If the command is not an instance of the bound class.
        """
        if not isinstance(command, self._command):
            raise TypeError(f"Command must be of type {self._command.__name__}, got {type(command).__name__}")
        self._sender.send(command)


class EventHandle[E: BaseEvent]:
    """Subscribe typed handlers to one event class through a subscriber.

    Normally obtained from ``ProtocolContext.require_event``. The environment
    determines which instances match the event class and when they arrive.
    """

    def __init__(self, event_type: type[E], subscriber: Subscriber):
        """Bind an event class to its subscription target.

        Direct construction does not declare or validate environment support;
        ``ProtocolContext.require_event`` performs that step.
        """
        self._event = event_type
        self._subscriber = subscriber

    def subscribe(self, handler: EventHandler[E], *, options: SubscriptionOptions | None = None) -> Subscription:
        """Register a handler and return its subscription.

        A connected environment may deliver events before this call returns.
        The returned token can cancel the registration. ``None`` options create
        an ongoing subscription; ``once=True`` options arrange delivery of at
        most one event.
        """
        return self._subscriber.subscribe(self._event, handler, options)

class _SenderSubscriber(Sender, Subscriber, Protocol):
    """Require both operations on the same target for query registration and send."""

class QueryHandle[C: BaseCommand, R: BaseEvent]:
    """Pair a command class with a response event class for one-shot requests.

    Normally obtained from ``ProtocolContext.require_query``. Each request listens
    for the next matching event; there is no request-ID correlation or timeout.
    Concurrent requests for the same response type may receive the same event.
    """
    def __init__(self, query_type: type[C], response_type: type[R], querier: _SenderSubscriber):
        """Bind query and response classes to a shared sending/subscription target.

        Direct construction does not validate either environment capability;
        ``ProtocolContext.require_query`` declares both requirements.
        """
        self._query = query_type
        self._response = response_type
        self._querier = querier

    def request(self, command: C, on_response: EventHandler[R]) -> Subscription:
        """Send a query command and redirect it's response to the on_response callback.

        The first matching event consumes this request's subscription, even if
        caused by another request. A response may arrive before this method
        returns. If no response arrives, the subscription remains active until
        canceled.

        Args:
            command: Query command instance to send.
            on_response: Callback for the next matching response event.

        Returns:
            The subscription token, which may already have been consumed by a
            synchronous response. Cancel only while it remains active.

        Raises:
            TypeError: If the command is not an instance of the bound query class.
        """
        if not isinstance(command, self._query):
            raise TypeError(f"Query must be of type {self._query.__name__}, got {type(command).__name__}")
        
        subscription = self._querier.subscribe(self._response,
                                               on_response, 
                                               options=SubscriptionOptions(once=True))
        self._querier.send(command)
        return subscription
