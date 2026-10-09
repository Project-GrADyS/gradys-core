"""The protocol's connection to an execution environment.

Handles keep a reference to ``Connection`` throughout their lifetime. The object
delegates to one of three states, so a handle made during construction continues to
work after injection without exposing partially completed setup.
"""

from __future__ import annotations

from gradys_core.command import BaseCommand
from gradys_core.environment import Environment
from gradys_core.event import BaseEvent, EventHandler

from .binding import (
    validate_command_type,
    validate_event_type,
)


class _PendingConnection:
    """Collect protocol requests until an environment is available."""

    def __init__(self) -> None:
        self.commands: list[BaseCommand] = []
        self.subscriptions: list[tuple[type[BaseEvent], EventHandler[BaseEvent]]] = []
        self.command_requirements: set[type[BaseCommand]] = set()
        self.event_requirements: set[type[BaseEvent]] = set()

    def require_command(self, command_type: type[BaseCommand]) -> None:
        self.command_requirements.add(command_type)

    def require_event(self, event_type: type[BaseEvent]) -> None:
        self.event_requirements.add(event_type)

    def send(self, command: BaseCommand) -> None:
        self.commands.append(command)

    def subscribe[E: BaseEvent](self, event: type[E], handler: EventHandler[E]) -> None:
        # The pair retains the relationship between the event type and its handler.
        self.subscriptions.append((event, handler))

    def connect(self, environment: Environment) -> _ConnectedConnection:
        connected = _ConnectedConnection(environment)
        for command_type in self.command_requirements:
            connected.require_command(command_type)
        for event_type in self.event_requirements:
            connected.require_event(event_type)
        for event, handler in self.subscriptions:
            connected.subscribe(event, handler)
        for command in self.commands:
            connected.send(command)

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

    def subscribe[E: BaseEvent](self, event: type[E], handler: EventHandler[E]) -> None:
        self._environment.event_subscriber(event, handler)


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

    def subscribe[E: BaseEvent](self, _event: type[E], _handler: EventHandler[E]) -> None:
        self._raise()


type _ConnectionState = _PendingConnection | _ConnectedConnection | _FailedConnection


class Connection:
    """Stable target for handles while the protocol changes connection state."""

    def __init__(self) -> None:
        self._state: _ConnectionState = _PendingConnection()

    def require_command(self, command_type: type[BaseCommand]) -> None:
        self._state.require_command(command_type)

    def require_event(self, event_type: type[BaseEvent]) -> None:
        self._state.require_event(event_type)

    def send(self, command: BaseCommand) -> None:
        self._state.send(command)

    def subscribe[E: BaseEvent](self, event: type[E], handler: EventHandler[E]) -> None:
        self._state.subscribe(event, handler)

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
