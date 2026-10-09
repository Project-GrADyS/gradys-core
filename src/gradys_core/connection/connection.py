"""The protocol's connection to an execution environment.

Handles keep a reference to ``Connection`` throughout their lifetime. The object
delegates to one of three states, so a handle made during construction continues to
work after injection without exposing partially completed setup.
"""

from __future__ import annotations
from typing import Any, Callable, Optional

from gradys_core.command import BaseCommand
from gradys_core.environment import Environment
from gradys_core.event import BaseEvent, EventHandler

from .binding import (
    validate_command_type,
    validate_event_type,
)
from .subscription import Subscriber, SubscriptionOption

class _ConnectionSubscription[E: BaseEvent]:
    """A subscription to an event type in an environment."""
    def __init__(self, 
                 unsubscribe: Callable[[], None], 
                 event_type: type[E], 
                 handler: EventHandler[E],
                 options: SubscriptionOption) -> None:
        self.unsubscribe_impl = unsubscribe
        self.event_type = event_type
        self.handler = handler
        self.options = options

    def unsubscribe(self) -> None:
        """Unregister the subscription from the environment."""
        self.unsubscribe_impl()

class _PendingConnection:
    """Collect protocol requests until an environment is available."""

    def __init__(self) -> None:
        self.commands: list[BaseCommand] = []
        self.subscriptions: list[_ConnectionSubscription[Any]] = []
        self.command_requirements: set[type[BaseCommand]] = set()
        self.event_requirements: set[type[BaseEvent]] = set()

    def require_command(self, command_type: type[BaseCommand]) -> None:
        self.command_requirements.add(command_type)

    def require_event(self, event_type: type[BaseEvent]) -> None:
        self.event_requirements.add(event_type)

    def send(self, command: BaseCommand) -> None:
        self.commands.append(command)

    def subscribe[E: BaseEvent](self, 
                                event: type[E], 
                                handler: EventHandler[E],
                                options: SubscriptionOption) -> _ConnectionSubscription[E]:
        # The pair retains the relationship between the event type and its handler.
        subscription = _ConnectionSubscription(
            lambda: self.subscriptions.remove(subscription), event, handler, options)
        self.subscriptions.append(subscription)
        return subscription

    def connect(self, environment: Environment) -> _ConnectedConnection:
        try:
            connected = _ConnectedConnection(environment)
            for command_type in self.command_requirements:
                connected.require_command(command_type)
            for event_type in self.event_requirements:
                connected.require_event(event_type)
            for subscription in self.subscriptions:
                new_sub = connected.subscribe(subscription.event_type, subscription.handler, subscription.options)
                # Update the unsubscribe implemementation for the subscription object that was already handed out
                subscription.unsubscribe_impl = new_sub.unsubscribe
            for command in self.commands:
                connected.send(command)
        except:
            # Invalidate subscriptions in case of failure
            def _raise() -> None:
                raise RuntimeError("Protocol injection failed. Create a new protocol instance.")
            for subscription in self.subscriptions:
                subscription.unsubscribe_impl = _raise
            raise

        return connected


class _ConnectedConnection:
    """Forward protocol requests to the injected environment."""

    def __init__(self, environment: Environment) -> None:
        self._environment = environment

    def require_command(self, command_type: type[BaseCommand]) -> None:
        validate_command_type(self._environment, command_type)

    def require_event(self, event_type: type[BaseEvent]) -> None:
        validate_event_type(self._environment, event_type)

    def send(self, command: BaseCommand) -> None:
        self._environment.command_sender(command)

    def subscribe[E: BaseEvent](self, event: type[E], handler: EventHandler[E], options: SubscriptionOption) -> _ConnectionSubscription[E]:
        unsubscription_callback: Optional[Callable[[], None]] = None
        has_been_called = False
        if options.once:
            # Wrapping original handler to unsubscribe after first invocation
            original_handler = handler
            def once_callback(event: E) -> None:
                nonlocal has_been_called, unsubscription_callback
                if has_been_called:
                    return

                has_been_called = True
                if unsubscription_callback is not None:
                    unsubscription_callback()

                original_handler(event)
            handler = once_callback
        
        unsubscription_callback = self._environment.event_subscriber(event, handler)

        # If registration delivered an event, cleanup had to wait for its return value.
        if options.once and has_been_called:
            unsubscription_callback()

        return _ConnectionSubscription(unsubscription_callback, event, handler, options)


class _FailedConnection:
    """Reject use of a protocol whose injection stopped partway through."""

    @staticmethod
    def _raise() -> None:
        raise RuntimeError("Protocol injection failed. Create a new protocol instance.")

    def require_command(self, _command_type: type[BaseCommand]) -> None:
        self._raise()

    def require_event(self, _event_type: type[BaseEvent]) -> None:
        self._raise()

    def send(self, _command: BaseCommand) -> None:
        self._raise()

    def subscribe[E: BaseEvent](self, _event: type[E], _handler: EventHandler[E], _options: SubscriptionOption) -> _ConnectionSubscription[E]:
        self._raise()
        return _ConnectionSubscription(lambda: None, _event, _handler, _options)


type _ConnectionState = _PendingConnection | _ConnectedConnection | _FailedConnection


class Connection(Subscriber):
    """Stable target for handles while the protocol changes connection state."""

    def __init__(self) -> None:
        self._state: _ConnectionState = _PendingConnection()

    def require_command(self, command_type: type[BaseCommand]) -> None:
        self._state.require_command(command_type)

    def require_event(self, event_type: type[BaseEvent]) -> None:
        self._state.require_event(event_type)

    def send(self, command: BaseCommand) -> None:
        self._state.send(command)

    def subscribe[E: BaseEvent](self, 
                                event: type[E], 
                                handler: EventHandler[E], 
                                options: Optional[SubscriptionOption] = None) -> _ConnectionSubscription[E]:
        if options is None:
            options = SubscriptionOption()
        return self._state.subscribe(event, handler, options)

    def inject(self, environment: Environment) -> None:
        if not isinstance(self._state, _PendingConnection):
            raise RuntimeError("Protocol has already been injected.")

        pending = self._state
        try:
            self._state = pending.connect(environment)
        except BaseException:
            # Environment callbacks may already have had effects; never retry them.
            self._state = _FailedConnection()
            raise
