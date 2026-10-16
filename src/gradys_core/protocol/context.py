"""Capability access shared by a protocol and its plugins."""

from gradys_core.connection import Connection
from gradys_core.primitives import BaseCommand, BaseEvent, QueryDefinition

from .handles import CommandHandle, EventHandle, QueryHandle


class ProtocolContext:
    """Validate requirements and create typed handles on an available connection.

    Environment adapters construct the context before calling a protocol's start
    method. Plugins may share that context. Unsupported requirements raise
    ProtocolSetUpException immediately; earlier operations are not rolled back.
    """

    def __init__(self, connection: Connection) -> None:
        """Retain the connection used by all handles created by this context."""
        self._connection = connection

    def require_command[C: BaseCommand](self, command_type: type[C]) -> CommandHandle[C]:
        """Validate command support and return a handle without sending anything.

        Raises:
            ProtocolSetUpException: If the environment rejects the command type.
        """
        self._connection.require_command(command_type)
        return CommandHandle(command_type, self._connection)

    def require_event[E: BaseEvent](self, event_type: type[E]) -> EventHandle[E]:
        """Validate event support and return a handle without subscribing yet.

        Raises:
            ProtocolSetUpException: If the environment rejects the event type.
        """
        self._connection.require_event(event_type)
        return EventHandle(event_type, self._connection)

    def require_query[C: BaseCommand, R: BaseEvent](
        self, query_type: type[QueryDefinition[C, R]]
    ) -> QueryHandle[C, R]:
        """Validate the query command and response types without sending a request.

        Checks run in command-then-response order. Queries retain synchronous
        callback delivery; the handle does not provide response correlation.

        Raises:
            ProtocolSetUpException: If the environment rejects either type.
        """
        command_type, response_type = query_type.query_types()
        self._connection.require_command(command_type)
        self._connection.require_event(response_type)
        return QueryHandle(command_type, response_type, self._connection)
