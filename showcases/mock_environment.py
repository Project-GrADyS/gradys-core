"""A minimal environment used by the runnable showcases.

The environment declares capabilities, builds an InjectionPackage, and decides when
accepted commands execute. It is deliberately small, not a simulator implementation.
"""

from collections import defaultdict, deque
from collections.abc import Callable
from typing import cast

from gradys_core.capabilities.lifecycle import SimulationInitializationEvent
from gradys_core.capabilities.mobility import GotoCoords, PositionUpdate
from gradys_core.command import BaseCommand
from gradys_core.event import BaseEvent
from gradys_core.protocol import BaseProtocol, InjectionPackage


class MobilityHandler:
    """Accept movement requests and publish position observations."""

    commands = frozenset({GotoCoords})
    events = frozenset({PositionUpdate})

    def handle(self, command: BaseCommand, emit: Callable[[BaseEvent], None]) -> None:
        if not isinstance(command, GotoCoords):
            raise TypeError(f"Unsupported mobility command: {type(command).__name__}")
        emit(PositionUpdate(command.x, command.y, command.z))


class MockEnvironment:
    def __init__(self, *, mobility: bool = True) -> None:
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
        protocol._inject(InjectionPackage(
            command_sender=self.send,
            command_checker=lambda command_type: command_type in self._command_handlers,
            event_subscriber=self.subscribe,
            event_checker=lambda event_type: event_type in self._event_types,
        ))

    def subscribe[E: BaseEvent](self, event_type: type[E], handler: Callable[[E], None]) -> None:
        # Event type and handler stay paired; storage erases only the generic type.
        self._subscribers[event_type].append(cast(Callable[[BaseEvent], None], handler))

    def emit(self, event: BaseEvent) -> None:
        for handler in tuple(self._subscribers[type(event)]):
            handler(event)

    def send(self, command: BaseCommand) -> None:
        """Accept a command; execution waits until the environment starts."""
        self._pending_commands.append(command)
        if self._running:
            self._drain()

    def start(self) -> None:
        if self._running:
            raise RuntimeError("Environment has already started.")
        self.emit(SimulationInitializationEvent())
        self._running = True
        self._drain()

    def _drain(self) -> None:
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
