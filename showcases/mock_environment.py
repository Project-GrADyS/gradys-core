"""A minimal environment used by the runnable showcases.

The environment declares capabilities, implements the Environment interface, and decides when
accepted commands execute. It is deliberately small, not a simulator implementation.
"""

from collections import defaultdict, deque
from collections.abc import Callable
from typing import cast

from gradys_core.capabilities.lifecycle import SimulationInitializationEvent
from gradys_core.capabilities.mobility import GotoCoords, PositionUpdate
from gradys_core.primitives import BaseCommand, BaseEvent
from gradys_core.protocol import BaseProtocol


class MobilityHandler:
    """Accept movement requests and publish position observations."""

    commands = frozenset({GotoCoords})
    """Command classes handled by this example mobility implementation."""
    events = frozenset({PositionUpdate})
    """Event classes this handler can publish."""

    def handle(self, command: BaseCommand, emit: Callable[[BaseEvent], None]) -> None:
        """Turn a movement command into an immediate position update.

        This example reports the destination without simulating motion.

        Args:
            command: Movement request to execute.
            emit: Callback used to publish the resulting position event.

        Raises:
            TypeError: If the command is not a ``GotoCoords`` instance.
        """
        if not isinstance(command, GotoCoords):
            raise TypeError(f"Unsupported mobility command: {type(command).__name__}")
        emit(PositionUpdate(command.x, command.y, command.z))


class MockEnvironment:
    """Queue commands until startup and dispatch exact event types synchronously.

    This showcase adapter demonstrates capability checks and execution timing.
    Its ``event_subscriber`` does not return an unsubscription callback, so it
    does not satisfy the full ``Environment`` contract and cannot demonstrate
    cancellation or one-shot cleanup.

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

    def bind(self, protocol: BaseProtocol) -> None:
        """Validate capabilities and connect a protocol to this environment."""
        protocol._inject(self)

    def command_checker(self, command_type: type[BaseCommand]) -> bool:
        """Return whether this exact command class has a registered handler."""
        return command_type in self._command_handlers

    def event_checker(self, event_type: type[BaseEvent]) -> bool:
        """Return whether this exact event class is advertised by the environment."""
        return event_type in self._event_types

    def event_subscriber[E: BaseEvent](self, event_type: type[E], handler: Callable[[E], None]) -> None:
        """Append a handler for exact-type delivery without cancellation support."""
        # Event type and handler stay paired; storage erases only the generic type.
        self._subscribers[event_type].append(cast(Callable[[BaseEvent], None], handler))

    def emit(self, event: BaseEvent) -> None:
        """Deliver to a snapshot of exact-type handlers in registration order.

        Newly registered handlers wait for a later emission. Handler exceptions
        propagate immediately and stop the current delivery loop.
        """
        for handler in tuple(self._subscribers[type(event)]):
            handler(event)

    def command_sender(self, command: BaseCommand) -> None:
        """Accept a command; execution waits until the environment starts."""
        self._pending_commands.append(command)
        if self._running:
            self._drain()

    def start(self) -> None:
        """Emit initialization, mark the runtime running, and drain queued commands.

        Commands sent by initialization handlers join the queue before draining.

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

        The guard lets the outer loop handle reentrant sends without recursive
        draining. Reset it even when execution or event delivery raises.
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
