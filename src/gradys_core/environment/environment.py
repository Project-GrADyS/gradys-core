"""Structural interface between an execution environment and a connection."""

from collections.abc import Callable
from typing import Protocol

from gradys_core.primitives import BaseCommand, BaseEvent, EventHandler


class Environment(Protocol):
    """Services supplied by an external environment to one protocol connection.

    Implementations can satisfy this interface without inheriting from it. The
    environment controls when accepted commands execute and events are delivered.
    """

    async def send_command(self, command: BaseCommand, /) -> None:
        """Accept a command for execution."""
        ...

    def check_command(self, command_type: type[BaseCommand], /) -> bool:
        """Report support for a command type without executing a command."""
        ...

    def subscribe_to_event[E: BaseEvent](
        self, event_type: type[E], handler: EventHandler[E], /
    ) -> Callable[[], None]:
        """Register an event handler and return its unsubscription callback.

        Args:
            event_type: Event class whose deliveries the handler receives.
            handler: Callback accepting an instance of that event type.

        Returns:
            A callable that unregisters this registration.
        """
        ...

    def check_event(self, event_type: type[BaseEvent], /) -> bool:
        """Report support for an event type without registering a handler."""
        ...
