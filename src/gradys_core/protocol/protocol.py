"""User-facing protocol base class."""

from gradys_core.connection import Connection
from gradys_core.environment import Environment
from gradys_core.primitives import BaseCommand, BaseEvent, QueryDefinition

from .handles import CommandHandle, EventHandle, QueryHandle


class BaseProtocol:
    """Declare capabilities and obtain typed handles for an algorithm instance.

    Requirements and operations may be registered during subclass construction;
    no call to a base constructor is required. A connection is created lazily
    for each instance. Plugins can add requirements through the same protocol.

    Before injection, requirements are deduplicated and commands/subscriptions
    are buffered. Injection validates requirements, installs subscriptions, and
    forwards queued commands. Later requirements are validated immediately.
    Environment startup and actual command execution remain adapter concerns.
    """

    _connection_instance: Connection | None = None

    @property
    def _connection(self) -> Connection:
        """Create this instance's stable connection on its first use.

        Assignment shadows the class-level ``None`` sentinel. Each protocol
        instance has its own connection; plugins using that protocol share it.
        """
        if self._connection_instance is None:
            self._connection_instance = Connection()
        return self._connection_instance

    def require_command[C: BaseCommand](self, command_type: type[C]) -> CommandHandle[C]:
        """Declare a command requirement and return its typed sending handle.

        Support is checked at injection, or immediately if already connected.
        Repeated declarations are allowed and do not send a command.

        Raises:
            ProtocolSetUpException: If a connected environment rejects the type.
            RuntimeError: If an earlier injection failed.
        """
        self._connection.require_command(command_type)
        return CommandHandle(command_type, self._connection)

    def require_event[E: BaseEvent](self, event_type: type[E]) -> EventHandle[E]:
        """Declare an event requirement and return its typed subscription handle.

        Support is checked at injection, or immediately if already connected.
        Repeated declarations are allowed and do not register a handler until
        the returned handle's ``subscribe`` method is called.

        Raises:
            ProtocolSetUpException: If a connected environment rejects the type.
            RuntimeError: If an earlier injection failed.
        """
        self._connection.require_event(event_type)
        return EventHandle(event_type, self._connection)

    def require_query[C: BaseCommand, R: BaseEvent](self, query_type: type[QueryDefinition[C, R]]) -> QueryHandle[C, R]:
        """Declare a query's command and response requirements and return a handle.

        ``query_type.query_types()`` supplies the command and response classes.
        Requirements are checked in that order and are not declared atomically:
        a rejected response requirement does not undo the command requirement.
        No request is sent until the handle's ``request`` method is called.

        Raises:
            ProtocolSetUpException: If a connected environment rejects either type.
            RuntimeError: If an earlier injection failed.
        """
        command_type, response_type = query_type.query_types()
        self._connection.require_command(command_type)
        self._connection.require_event(response_type)
        return QueryHandle(command_type, response_type, self._connection)

    def _inject(self, environment: Environment) -> None:
        """Attach an environment once and replay buffered registrations and sends.

        Called by environment integration code. This neither starts the runtime
        nor emits lifecycle events. Failure permanently invalidates the connection
        because callbacks may already have caused external effects.

        Raises:
            TypeError: If injection has already succeeded or failed.
            ProtocolSetUpException: If a buffered capability is unsupported.
        """
        self._connection.inject(environment)
