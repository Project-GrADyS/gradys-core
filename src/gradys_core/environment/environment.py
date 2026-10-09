"""Structural interface between an execution environment and a connection."""

from typing import Callable, Protocol

from gradys_core.command import BaseCommand
from gradys_core.event import BaseEvent, EventHandler


class Environment(Protocol):
    """Services supplied by an external environment to one protocol connection.

    Implementations can satisfy this interface without inheriting from it. The
    environment controls when accepted commands execute and events are delivered.
    """

    def command_sender(self, command: BaseCommand, /) -> None:
        """Accept a command for execution."""
        ...

    def command_checker(self, command_type: type[BaseCommand], /) -> bool:
        """Report whether the environment supports a command type."""
        ...

    def event_subscriber[E: BaseEvent](
        self, event_type: type[E], handler: EventHandler[E], /
    ) -> Callable[[], None]:
        """
        Register a handler for the matching event type.

        Returns:
            A callable that, when invoked, unregisters the handler.
        """
        ...

    def event_checker(self, event_type: type[BaseEvent], /) -> bool:
        """Report whether the environment supports an event type."""
        ...
