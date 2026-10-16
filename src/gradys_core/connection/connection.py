"""Synchronous connection to an available execution environment."""

from collections.abc import Callable

from gradys_core.environment import Environment
from gradys_core.primitives import BaseCommand, BaseEvent, EventHandler

from .binding import validate_command_type, validate_event_type
from .sender import Sender
from .subscriber import Subscriber, Subscription, SubscriptionOptions


class _ConnectionSubscription:
    """Delegate cancellation to the environment."""

    def __init__(self, unsubscribe: Callable[[], None]) -> None:
        """Retain the registration's removal callback."""
        self._unsubscribe = unsubscribe

    def unsubscribe(self) -> None:
        """Remove the registration according to the environment's contract."""
        self._unsubscribe()


class Connection(Sender, Subscriber):
    """Forward operations to an environment supplied at construction.

    Capability checks are immediate. Sending and subscribing do not implicitly
    declare requirements; ProtocolContext performs those checks before returning
    handles. Commands are accepted according to the environment's scheduling.
    No operations are buffered or replayed by this connection.
    """

    def __init__(self, environment: Environment) -> None:
        """Retain the environment used for immediate forwarding and validation."""
        self._environment = environment

    def require_command(self, command_type: type[BaseCommand]) -> None:
        """Validate a newly requested command capability immediately."""
        validate_command_type(self._environment, command_type)

    def require_event(self, event_type: type[BaseEvent]) -> None:
        """Validate a newly requested event capability immediately."""
        validate_event_type(self._environment, event_type)

    async def send(self, command: BaseCommand) -> None:
        """Let the environment accept a command without further type validation."""
        await self._environment.send_command(command)

    def subscribe[E: BaseEvent](self, event: type[E], handler: EventHandler[E], options: SubscriptionOptions | None = None) -> Subscription:
        """Register immediately, guarding one-shot handlers against repeated delivery.

        Normally one-shot removal precedes the user callback. If registration
        itself delivers an event, the removal callback is not yet available;
        cleanup waits for registration to return successfully.
        """
        if options is None:
            options = SubscriptionOptions()
        unsubscription_callback: Callable[[], None] | None = None
        has_been_called = False
        if options.once:
            # Set the guard before calling adapter or user code: either may deliver again.
            original_handler = handler
            def once_callback(event: E) -> None:
                """Consume the first event even if removal or the handler reenters."""
                nonlocal has_been_called, unsubscription_callback
                if has_been_called:
                    return

                has_been_called = True
                if unsubscription_callback is not None:
                    unsubscription_callback()

                original_handler(event)
            handler = once_callback
        
        unsubscription_callback = self._environment.subscribe_to_event(event, handler)

        # If registration delivered an event, cleanup had to wait for its return value.
        if options.once and has_been_called:
            unsubscription_callback()

        return _ConnectionSubscription(unsubscription_callback)
