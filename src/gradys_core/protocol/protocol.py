from dataclasses import dataclass
from collections import deque
from typing import Type, cast

from gradys_core.command import BaseCommand, CommandHandle, CommandSender
from gradys_core.event import BaseEvent, EventHandle, EventHandler, EventSubscriber


@dataclass
class InjectionPackage:
    """
    Methods that connect a protocol to its environment. These are provided by the environment and injected into
     the protocol.
    """

    command_sender: CommandSender
    event_subscriber: EventSubscriber


class _Connection:
    """Bridge handles created before a protocol is attached to its environment."""

    def __init__(self) -> None:
        self._package: InjectionPackage | None = None
        """
        Stores the injected environment package. If None, the protocol is not yet injected and commands/events are 
        buffered.
        """

        # These lists store commands and subscriptions that are buffered before the protocol is injected into the
        # environment. These list will be emptied once the protocol is injected and the buffered commands/subscriptions
        # are sent/registered.
        self._buffered_commands: list[BaseCommand] = []
        self._unfulfilled_subscriptions: list[tuple[type[BaseEvent], EventHandler[BaseEvent]]] = []

    def send(self, command: BaseCommand) -> None:
        # Buffers commands before injection, or sends them directly if already injected
        if self._package is None:
            self._buffered_commands.append(command)
        else:
            self._package.command_sender(command)

    def subscribe[E: BaseEvent](self, event: type[E], handler: EventHandler[E]) -> None:
        # Buffers subscriptions before injection, or subscribes them directly if already injected
        if self._package is None:
            self._unfulfilled_subscriptions.append((event, handler))
        else:
            self._package.event_subscriber(event, handler)

    def inject(self, package: InjectionPackage) -> None:
        """Attach once; a failed attempt cannot be retried because callbacks may have run."""
        if self._package is not None:
            raise RuntimeError("Protocol is already injected.")

        for event, handler in self._unfulfilled_subscriptions:
            package.event_subscriber(event, handler)
        self._unfulfilled_subscriptions.clear()

        for command in self._buffered_commands:
            package.command_sender(command)
        self._buffered_commands.clear()

        self._package = package


class BaseProtocol:
    def __init__(self) -> None:
        self._connection = _Connection()

    def require_command[C: BaseCommand](self, command_type: Type[C]) -> CommandHandle[C]:
        return CommandHandle[C](command_type, self._connection.send)

    def require_event[E: BaseEvent](self, event_type: Type[E]) -> EventHandle[E]:
        return EventHandle[E](event_type, self._connection.subscribe)

    def _inject(self, package: InjectionPackage) -> None:
        """Attach environment callbacks; startup readiness remains the environment's responsibility."""
        self._connection.inject(package)
