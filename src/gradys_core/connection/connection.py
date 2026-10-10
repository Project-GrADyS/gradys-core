"""The protocol's connection to an execution environment.

Handles keep a reference to ``Connection`` throughout their lifetime. The object
delegates to pending, connected, or failed state. A handle made during construction
continues to target the same object after injection. Replay has external effects;
failure invalidates the connection rather than permitting a retry.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from gradys_core.environment import Environment
from gradys_core.primitives import BaseCommand, BaseEvent, EventHandler

from .binding import (
    validate_command_type,
    validate_event_type,
)
from .sender import Sender
from .subscriber import Subscriber, SubscriptionOptions


class _ConnectionSubscription[E: BaseEvent]:
    """Keep a registration and its replaceable cancellation operation together.

    While pending, cancellation removes this object from the buffer. On succesful
    connection cancellation is replaced by the environment's callback . Failed 
    injection replaces it with a raiser.

    Attributes:
        unsubscribe_impl: Current removal operation for this registration.
        event_type: Event class retained for registration with other states.
        handler: Callback paired with ``event_type`` for registration with other states.
        options: Delivery options retained  for registration with other states.
    """
    def __init__(self, 
                 unsubscribe: Callable[[], None], 
                 event_type: type[E], 
                 handler: EventHandler[E],
                 options: SubscriptionOptions) -> None:
        """Retain the typed registration and its initial removal callback."""
        self.unsubscribe_impl = unsubscribe
        self.event_type = event_type
        self.handler = handler
        self.options = options

    def unsubscribe(self) -> None:
        """Invoke the current removal operation."""
        self.unsubscribe_impl()

class _PendingConnection:
    """Collect protocol requests until an environment is available."""

    def __init__(self) -> None:
        """Create ordered operation buffers and deduplicated requirement sets."""
        self.commands: list[BaseCommand] = []
        self.subscriptions: list[_ConnectionSubscription[Any]] = []
        self.command_requirements: set[type[BaseCommand]] = set()
        self.event_requirements: set[type[BaseEvent]] = set()

    def require_command(self, command_type: type[BaseCommand]) -> None:
        """Record a command capability to validate before replay."""
        self.command_requirements.add(command_type)

    def require_event(self, event_type: type[BaseEvent]) -> None:
        """Record an event capability to validate before replay."""
        self.event_requirements.add(event_type)

    def send(self, command: BaseCommand) -> None:
        """Append to the shared command queue in sending order."""
        self.commands.append(command)

    def subscribe[E: BaseEvent](self, 
                                event: type[E], 
                                handler: EventHandler[E],
                                options: SubscriptionOptions) -> _ConnectionSubscription[E]:
        """Buffer a registration and return a subscription object whose cancellation removes it from the buffer."""
        # The pair retains the relationship between the event type and its handler.
        subscription = _ConnectionSubscription(
            lambda: self.subscriptions.remove(subscription), event, handler, options)
        self.subscriptions.append(subscription)
        return subscription

    def connect(self, environment: Environment) -> _ConnectedConnection:
        """Validate all requirements, install subscriptions, then forward commands."""
        try:
            connected = _ConnectedConnection(environment)
            for command_type in self.command_requirements:
                connected.require_command(command_type)
            for event_type in self.event_requirements:
                connected.require_event(event_type)
            for subscription in self.subscriptions:
                new_sub = connected.subscribe(subscription.event_type, subscription.handler, subscription.options)
                # Keep the original token usable after its buffered registration 
                # is installed.
                subscription.unsubscribe_impl = new_sub.unsubscribe
            for command in self.commands:
                connected.send(command)
        except:
            # Partial replay may have external effects; tokens must not 
            # suggest retryability.
            def _raise() -> None:
                """Reject cancellation through a token invalidated by failed replay."""
                raise RuntimeError("Protocol injection failed. Create a new protocol instance.")
            for subscription in self.subscriptions:
                subscription.unsubscribe_impl = _raise
            raise

        return connected


class _ConnectedConnection:
    """Forward protocol requests to the injected environment."""

    def __init__(self, environment: Environment) -> None:
        """Retain the environment used for immediate forwarding and validation."""
        self._environment = environment

    def require_command(self, command_type: type[BaseCommand]) -> None:
        """Validate a newly requested command capability immediately."""
        validate_command_type(self._environment, command_type)

    def require_event(self, event_type: type[BaseEvent]) -> None:
        """Validate a newly requested event capability immediately."""
        validate_event_type(self._environment, event_type)

    def send(self, command: BaseCommand) -> None:
        """Let the environment accept a command without further type validation."""
        self._environment.command_sender(command)

    def subscribe[E: BaseEvent](self, event: type[E], handler: EventHandler[E], options: SubscriptionOptions) -> _ConnectionSubscription[E]:
        """Register immediately, guarding one-shot handlers against repeated delivery.

        Normally one-shot removal precedes the user callback. If registration
        itself delivers an event, the removal callback is not yet available;
        cleanup waits for registration to return successfully.
        """
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
        
        unsubscription_callback = self._environment.event_subscriber(event, handler)

        # If registration delivered an event, cleanup had to wait for its return value.
        if options.once and has_been_called:
            unsubscription_callback()

        return _ConnectionSubscription(unsubscription_callback, event, handler, options)


class _FailedConnection:
    """Reject use of a protocol whose injection stopped partway through."""

    @staticmethod
    def _raise() -> None:
        """Require a fresh protocol after a partially completed injection."""
        raise RuntimeError("Protocol injection failed. Create a new protocol instance.")

    def require_command(self, _command_type: type[BaseCommand]) -> None:
        self._raise()

    def require_event(self, _event_type: type[BaseEvent]) -> None:
        self._raise()

    def send(self, _command: BaseCommand) -> None:
        self._raise()

    def subscribe[E: BaseEvent](self, _event: type[E], _handler: EventHandler[E], _options: SubscriptionOptions) -> _ConnectionSubscription[E]:
        self._raise()
        return _ConnectionSubscription(lambda: None, _event, _handler, _options)


type _ConnectionState = _PendingConnection | _ConnectedConnection | _FailedConnection
"""States through which a stable connection delegates protocol operations."""


class Connection(Sender, Subscriber):
    """Buffer protocol operations until an environment is injected once.

    Requirements are validated before subscriptions are installed and commands
    are forwarded. After successful injection, new operations go directly to
    the environment. Injection failure permanently rejects further operations,
    since already performed environment callbacks cannot safely be replayed.

    Requirements are explicit: ``send`` and ``subscribe`` do not declare or
    validate them. 
    """

    def __init__(self) -> None:
        """Create an unbound connection with empty operation buffers."""
        self._state: _ConnectionState = _PendingConnection()

    def require_command(self, command_type: type[BaseCommand]) -> None:
        """Record a command requirement, or check it immediately when connected.

        Duplicate pending requirements are deduplicated.

        Raises:
            ProtocolSetUpException: If a connected environment rejects the type.
            RuntimeError: If an earlier injection failed.
        """
        self._state.require_command(command_type)

    def require_event(self, event_type: type[BaseEvent]) -> None:
        """Record an event requirement, or check it immediately when connected.

        Duplicate pending requirements are deduplicated.

        Raises:
            ProtocolSetUpException: If a connected environment rejects the type.
            RuntimeError: If an earlier injection failed.
        """
        self._state.require_event(event_type)

    def send(self, command: BaseCommand) -> None:
        """Queue a command before injection, otherwise forward it immediately.

        All handles share the same command queue, preserving send order during
        replay. Forwarding does not imply execution; the environment owns that
        scheduling and its exceptions propagate to the caller.

        Raises:
            RuntimeError: If an earlier injection failed.
        """
        self._state.send(command)

    def subscribe[E: BaseEvent](self, 
                                event: type[E], 
                                handler: EventHandler[E], 
                                options: SubscriptionOptions | None = None) -> _ConnectionSubscription[E]:
        """Queue or immediately install a handler and return a cancellation token.

        Connected registration may deliver events synchronously before this
        method returns. One-shot subscriptions guard against repeated delivery
        and arrange automatic removal after their first event. Tokens do not
        guarantee idempotent cancellation.

        Args:
            event: Event class to register for; matching is adapter-defined.
            handler: Callback accepting an instance of that event type.
            options: Delivery options; ``None`` selects an ongoing subscription.

        Returns:
            A token that cancels the queued or installed registration.

        Raises:
            RuntimeError: If an earlier injection failed.
        """
        if options is None:
            options = SubscriptionOptions()
        return self._state.subscribe(event, handler, options)

    def inject(self, environment: Environment) -> None:
        """Attach an environment and replay buffered operations once.

        All declared capabilities are checked before any buffered registrations
        or commands are forwarded. Subscriptions are installed in registration
        order, then commands are forwarded in send order. This does not start
        the environment or emit lifecycle events.

        Exceptions from validation, registration, or sending propagate and
        permanently invalidate this connection. Partial environment effects
        are not rolled back; create a new protocol instance after failure.

        Raises:
            TypeError: If injection has already succeeded or failed.
            ProtocolSetUpException: If a declared capability is unsupported.
        """
        if not isinstance(self._state, _PendingConnection):
            raise TypeError("Protocol has already been injected.")

        pending = self._state
        try:
            self._state = pending.connect(environment)
        except BaseException:
            # Environment callbacks may already have had effects; never retry them.
            self._state = _FailedConnection()
            raise
