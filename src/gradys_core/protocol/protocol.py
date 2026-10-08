"""User-facing protocol base class."""

from gradys_core.command import BaseCommand, CommandHandle
from gradys_core.event import BaseEvent, EventHandle

from .connection import InjectionPackage, _Connection


class BaseProtocol:
    _connection_instance: _Connection | None = None

    @property
    def _connection(self) -> _Connection:
        """
        Get the connection instance, creating it if it doesn't exist yet.
        """
        if self._connection_instance is None:
            self._connection_instance = _Connection()
        return self._connection_instance

    def require_command[C: BaseCommand](self, command_type: type[C]) -> CommandHandle[C]:
        """Require a command capability and return its sending handle."""
        self._connection.require_command(command_type)
        return CommandHandle(command_type, self._connection.send)

    def require_event[E: BaseEvent](self, event_type: type[E]) -> EventHandle[E]:
        """Require an event capability and return its subscription handle."""
        self._connection.require_event(event_type)
        return EventHandle(event_type, self._connection.subscribe)

    def _inject(self, package: InjectionPackage) -> None:
        """Attach environment functions; the environment controls startup readiness."""
        self._connection.inject(package)
