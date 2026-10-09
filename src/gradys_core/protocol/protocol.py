"""User-facing protocol base class."""

from gradys_core.connection import Connection
from gradys_core.environment import Environment
from gradys_core.primitives import BaseCommand, BaseEvent

from .handles import CommandHandle, EventHandle


class BaseProtocol:
    _connection_instance: Connection | None = None

    @property
    def _connection(self) -> Connection:
        """
        Get the connection instance, creating it if it doesn't exist yet.
        """
        if self._connection_instance is None:
            self._connection_instance = Connection()
        return self._connection_instance

    def require_command[C: BaseCommand](self, command_type: type[C]) -> CommandHandle[C]:
        """Require a command capability and return its sending handle."""
        self._connection.require_command(command_type)
        return CommandHandle(command_type, self._connection)

    def require_event[E: BaseEvent](self, event_type: type[E]) -> EventHandle[E]:
        """Require an event capability and return its subscription handle."""
        self._connection.require_event(event_type)
        return EventHandle(event_type, self._connection)

    def _inject(self, environment: Environment) -> None:
        """Attach an environment; the environment controls startup readiness."""
        self._connection.inject(environment)
