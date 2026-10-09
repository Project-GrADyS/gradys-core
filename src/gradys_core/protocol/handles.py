"""Typed command and event primitives used by protocol implementations."""

from typing import Callable

from gradys_core.command import BaseCommand
from gradys_core.connection import Subscriber, Subscription
from gradys_core.event import BaseEvent, EventHandler


class CommandHandle[C: BaseCommand]:
    """
    A handle to send commands of a specific type. The handle is created by the protocol and can be used to send commands
    of the specified type to the environment. The handle is type-safe and ensures that only commands of the specified
    type can be sent.
    """

    def __init__(self, command_type: type[C], sender: Callable[[C], None]) -> None:
        self._command = command_type
        self._sender = sender

    def send(self, command: C) -> None:
        if not isinstance(command, self._command):
            raise TypeError(f"Command must be of type {self._command.__name__}, got {type(command).__name__}")
        self._sender(command)


class EventHandle[E: BaseEvent]:
    """
    A handle to subscribe to events of a specific type. The handle is created by the protocol and can be used to
    subscribe to events of the specified type from the environment.
    """

    def __init__(self, event: type[E], subscriber: Subscriber):
        self._event = event
        self._subscriber = subscriber


    def subscribe(self, handler: EventHandler[E]) -> Subscription:
        return self._subscriber.subscribe(self._event, handler)
