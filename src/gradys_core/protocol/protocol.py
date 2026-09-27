from dataclasses import dataclass
from typing import Type

from gradys_core.command import BaseCommand, CommandHandle, CommandSender
from gradys_core.errors import ProtocolSetUpException
from gradys_core.event import BaseEvent, EventHandle, EventHandler, EventSubscriber
from .binding import CommandCapabilityChecker, EventCapabilityChecker, validate_command_type, validate_event_type


@dataclass
class InjectionPackage:
    """
    Methods that connect a protocol to its environment. These are provided by the environment and injected into
     the protocol.
    """

    command_sender: CommandSender
    command_checker: CommandCapabilityChecker

    event_subscriber: EventSubscriber
    event_checker: EventCapabilityChecker

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

        self._unchecked_command_types: set[type[BaseCommand]] = set()
        self._unchecked_event_types: set[type[BaseEvent]] = set()

    def report_command_requirement(self, command_type: type[BaseCommand]) -> None:
        """
        Reports that a command of the specified type is a requirement for the protocol. This method is called when a
        command handle is created, and it checks if the environment supports sending commands of that type.

        If the protocol is not yet injected, the command type is buffered and will be checked once the protocol is
        injected.
        :param command_type: The type of command that the protocol requires to send.
        """

        # Checks if the environment supports sending commands of a specific type. If the protocol is not yet injected,
        # the command type is buffered and will be checked once the protocol is injected.
        if self._package is None:
            self._unchecked_command_types.add(command_type)
        else:
            validate_command_type(self._package.command_checker, command_type)

    def report_event_requirement(self, event_type: type[BaseEvent]) -> None:
        """
        Reports that an event of the specified type is a requirement for the protocol. This method is called when an
        event handle is created, and it checks if the environment supports subscribing to events of that type.

        If the protocol is not yet injected, the event type is buffered and will be checked once the protocol is
        injected.
        :param event_type: The type of event that the protocol requires to subscribe to.
        """

        # Checks if the environment supports subscribing to events of a specific type. If the protocol is not yet
        # injected, the event type is buffered and will be checked once the protocol is injected.
        if self._package is None:
            self._unchecked_event_types.add(event_type)
        else:
            validate_event_type(self._package.event_checker, event_type)


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

        for command_type in self._unchecked_command_types:
            validate_command_type(package.command_checker, command_type)
        self._unchecked_command_types.clear()

        for event_type in self._unchecked_event_types:
            validate_event_type(package.event_checker, event_type)
        self._unchecked_event_types.clear()

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
        """
        Declares that the protocol requires the ability to send commands of a specific type. This method returns a
        handle that can be used to send commands of the specified type to the environment.
        :param command_type: The type of command that the protocol requires to send.
        :return: A handle that can be used to send commands of the specified type to the environment.
        """
        self._connection.report_command_requirement(command_type)
        return CommandHandle[C](command_type, self._connection.send)

    def require_event[E: BaseEvent](self, event_type: Type[E]) -> EventHandle[E]:
        """
        Declares that the protocol requires the ability to subscribe to events of a specific type. This method returns a
        handle that can be used to subscribe to events of the specified type from the environment.
        :param event_type: The type of event that the protocol requires to subscribe to.
        :return: A handle that can be used to subscribe to events of the specified type from the environment.
        """
        self._connection.report_event_requirement(event_type)
        return EventHandle[E](event_type, self._connection.subscribe)

    def _inject(self, package: InjectionPackage) -> None:
        """Attach environment callbacks; startup readiness remains the environment's responsibility."""
        self._connection.inject(package)
