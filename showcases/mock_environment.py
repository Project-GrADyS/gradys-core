"""A minimal environment used by the runnable showcases.

The environment declares capabilities, implements the Environment interface, and decides when
accepted commands execute. It is deliberately small, not a simulator implementation.
"""

from collections import defaultdict, deque
from collections.abc import Callable
from typing import cast

from gradys_core.capabilities.lifecycle import SimulationInitializationEvent
from gradys_core.capabilities.mobility import GotoCoords, PositionUpdate
from gradys_core.connection import Connection
from gradys_core.primitives import BaseCommand, BaseEvent, BaseQuery
from gradys_core.protocol import BaseProtocol, ProtocolContext


class GetPosition(BaseQuery[PositionUpdate]):
    """Ask for the example environment's current position."""

    command_id = "GetPosition"

    @classmethod
    def response_type(cls) -> type[PositionUpdate]:
        """Pair this query with a position response event."""
        return PositionUpdate


class MobilityHandler:
    """Accept movement requests and publish position observations."""

    commands = frozenset({GotoCoords, GetPosition})
    """Command classes handled by this example mobility implementation."""
    events = frozenset({PositionUpdate})
    """Event classes this handler can publish."""

    def __init__(self) -> None:
        """Initialize the current position at the origin."""
        self._position = PositionUpdate(0.0, 0.0, 0.0)

    def handle(self, command: BaseCommand, emit: Callable[[BaseEvent], None]) -> None:
        """Report a movement destination or answer a position query.

        This example reports the destination without simulating motion.

        Args:
            command: Movement or position request to execute.
            emit: Callback used to publish the resulting position event.

        Raises:
            TypeError: If the command is not a supported mobility request.
        """
        if isinstance(command, GotoCoords):
            self._position = PositionUpdate(command.x, command.y, command.z)
        elif not isinstance(command, GetPosition):
            raise TypeError(f"Unsupported mobility command: {type(command).__name__}")
        emit(self._position)


class MockEnvironment:
    """Queue commands until startup and dispatch exact event types synchronously.

    This showcase adapter demonstrates capability checks and execution timing.
    Awaited sends are accepted immediately; this adapter queues accepted
    commands until start() to demonstrate environment-owned scheduling.

    Attributes:
        executed: Commands removed from the queue for execution, in order.
    """

    def __init__(self, *, mobility: bool = True) -> None:
        """Create a stopped environment, optionally exposing mobility support."""
        self._handlers = [MobilityHandler()] if mobility else []
        self._command_handlers: dict[type[BaseCommand], MobilityHandler] = {
            command_type: handler
            for handler in self._handlers
            for command_type in handler.commands
        }
        self._event_types: set[type[BaseEvent]] = {SimulationInitializationEvent}
        for handler in self._handlers:
            self._event_types.update(handler.events)

        self._subscribers: dict[type[BaseEvent], list[Callable[[BaseEvent], None]]] = defaultdict(list)
        self._pending_commands: deque[BaseCommand] = deque()
        self._running = False
        self._draining = False
        self.executed: list[BaseCommand] = []

    def bind(self, protocol: BaseProtocol) -> ProtocolContext:
        """Run the protocol with an available context and return that context."""
        context = ProtocolContext(Connection(self))
        protocol.run(context)
        return context

    def check_command(self, command_type: type[BaseCommand]) -> bool:
        """Return whether this exact command class has a registered handler."""
        return command_type in self._command_handlers

    def check_event(self, event_type: type[BaseEvent]) -> bool:
        """Return whether this exact event class is advertised by the environment."""
        return event_type in self._event_types

    def subscribe_to_event[E: BaseEvent](self, event_type: type[E], handler: Callable[[E], None]) -> Callable[[], None]:
        """Register an exact-type handler and return its removal callback."""
        # Event type and handler stay paired; storage erases only the generic type.
        erased = cast(Callable[[BaseEvent], None], handler)
        self._subscribers[event_type].append(erased)
        return lambda: self._subscribers[event_type].remove(erased)

    def emit(self, event: BaseEvent) -> None:
        """Deliver to a snapshot of exact-type handlers in registration order.

        Newly registered handlers wait for a later emission. Handler exceptions
        propagate immediately and stop the current delivery loop.
        """
        for handler in tuple(self._subscribers[type(event)]):
            handler(event)

    async def send_command(self, command: BaseCommand) -> None:
        """Accept a command; execution waits until the environment starts."""
        self._pending_commands.append(command)
        if self._running:
            self._drain()

    def start(self) -> None:
        """Emit initialization, mark the runtime running, and drain queued commands.

        Initialization handlers run before queued commands are drained.

        Raises:
            RuntimeError: If the environment is already running.
        """
        if self._running:
            raise RuntimeError("Environment has already started.")
        self.emit(SimulationInitializationEvent())
        self._running = True
        self._drain()

    def _drain(self) -> None:
        """Execute queued commands in order, including commands added by callbacks.

        The guard prevents nested drains during event delivery. Reset it even
        when execution or event delivery raises.
        """
        if self._draining:
            return
        self._draining = True
        try:
            while self._pending_commands:
                command = self._pending_commands.popleft()
                self.executed.append(command)
                self._command_handlers[type(command)].handle(command, self.emit)
        finally:
            self._draining = False
