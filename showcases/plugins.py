"""Plugins sharing the protocol's connected context.

Run from the repository root with ``python -m showcases.plugins``.
Requirements are checked individually, including overlapping requirements.
Events reach all matching subscribers regardless of who sent a command.
"""

import asyncio

from gradys_core.capabilities.lifecycle import SimulationInitializationEvent
from gradys_core.capabilities.mobility import GotoCoords, PositionUpdate
from gradys_core.errors import ProtocolSetUpException
from gradys_core.protocol import BaseProtocol, ProtocolContext

from .checks import check
from .mock_environment import MockEnvironment


class MovementPlugin:
    """Add mobility requirements and position handling to a supplied context.

    Attributes:
        notifications: Position descriptions received by this plugin.
        move: Command handle obtained through the shared context.
    """

    def __init__(
        self,
        context: ProtocolContext,
        destination: tuple[float, float, float],
        log: list[str] | None = None,
    ) -> None:
        """Subscribe to positions and retain a handle on the shared context.

        Args:
            context: Connected capability access shared with the protocol.
            destination: Cartesian destination for the initial movement command.
            log: Optional shared list recording protocol/plugin delivery order.
        """
        self.notifications: list[str] = []
        self.destination = destination
        self._log = log
        context.require_event(PositionUpdate).subscribe(self.on_position)
        self.move = context.require_command(GotoCoords)

    async def move_to_destination(self) -> None:
        """Await acceptance of this plugin's initial movement command."""
        await self.move.send(GotoCoords(*self.destination))

    def on_position(self, event: PositionUpdate) -> None:
        """Record an observation and append it to the shared log when supplied."""
        notification = f"position: ({event.x}, {event.y}, {event.z})"
        self.notifications.append(notification)
        if self._log is not None:
            self._log.append(f"plugin {notification}")


class LifecycleProtocol(BaseProtocol):
    """Require lifecycle events directly and mobility through a plugin.

    Attributes:
        notifications: Initialization notifications received by the protocol.
        plugin: Plugin whose mobility requirements join this protocol's own.
    """

    def __init__(self) -> None:
        """Initialize local state."""
        self.notifications: list[str] = []

    async def run(self, context: ProtocolContext) -> None:
        """Register lifecycle handling and initialize the plugin."""
        context.require_event(SimulationInitializationEvent).subscribe(self.on_start)
        self.plugin = MovementPlugin(context, (1.0, 2.0, 3.0))

    def on_start(self, event: SimulationInitializationEvent) -> None:
        """Record the environment's initialization notification."""
        self.notifications.append("started")


class SharedMovementProtocol(BaseProtocol):
    """Require the same mobility event and command as an attached plugin.

    Attributes:
        notifications: Lifecycle and position descriptions received here.
        log: Shared protocol/plugin log used to demonstrate delivery order.
        move: Protocol's sending handle for movement commands.
        plugin: Plugin with its own handlers and a handle on the same connection.
    """

    def __init__(self) -> None:
        """Initialize local state."""
        self.notifications: list[str] = []
        self.log: list[str] = []  # Shared with the plugin to record delivery order.

    async def run(self, context: ProtocolContext) -> None:
        """Register subscriptions and movement through the shared context."""
        context.require_event(SimulationInitializationEvent).subscribe(self.on_start)
        context.require_event(PositionUpdate).subscribe(self.on_position)
        self.move = context.require_command(GotoCoords)
        self.plugin = MovementPlugin(context, (4.0, 5.0, 6.0), self.log)

    def on_start(self, event: SimulationInitializationEvent) -> None:
        """Record initialization before the environment executes queued movement."""
        self.notifications.append("started")

    def on_position(self, event: PositionUpdate) -> None:
        """Record a position locally and in the shared delivery-order log."""
        notification = f"position: ({event.x}, {event.y}, {event.z})"
        self.notifications.append(notification)
        self.log.append(f"protocol {notification}")


async def disjoint() -> None:
    """Check that plugin requirements are validated through the shared context."""
    print("Disjoint: plugin adds mobility to a lifecycle-only protocol")
    environment = MockEnvironment()
    protocol = LifecycleProtocol()
    await environment.bind(protocol)
    await protocol.plugin.move_to_destination()
    environment.start()
    check(protocol.notifications == ["started"], "protocol gets only its own events")
    check(protocol.plugin.notifications == ["position: (1.0, 2.0, 3.0)"], "plugin gets its events")
    check(environment.executed == [GotoCoords(1.0, 2.0, 3.0)], "plugin command executes")

    rejected = LifecycleProtocol()
    try:
        await MockEnvironment(mobility=False).bind(rejected)
    except ProtocolSetUpException as error:
        check("GotoCoords" in error.message or "PositionUpdate" in error.message,
              "missing plugin capability rejects the protocol")
    else:
        raise AssertionError("Binding should reject the plugin's mobility requirements")


async def intersection() -> None:
    """Check shared capabilities, command order, and delivery to both subscribers."""
    print("\nIntersection: protocol and plugin share PositionUpdate and GotoCoords")
    environment = MockEnvironment()
    protocol = SharedMovementProtocol()
    await environment.bind(protocol)
    await protocol.move.send(GotoCoords(1.0, 2.0, 3.0))
    await protocol.plugin.move_to_destination()
    environment.start()
    check(environment.executed == [GotoCoords(1.0, 2.0, 3.0), GotoCoords(4.0, 5.0, 6.0)],
          "both commands execute in send order")
    check(protocol.notifications[1:] == protocol.plugin.notifications == [
        "position: (1.0, 2.0, 3.0)",
        "position: (4.0, 5.0, 6.0)",
    ], "both sides get every update")
    check(protocol.log == [
        "protocol position: (1.0, 2.0, 3.0)",
        "plugin position: (1.0, 2.0, 3.0)",
        "protocol position: (4.0, 5.0, 6.0)",
        "plugin position: (4.0, 5.0, 6.0)",
    ], "handlers run in subscription order")

    await protocol.move.send(GotoCoords(7.0, 8.0, 9.0))
    await protocol.plugin.move.send(GotoCoords(0.0, 0.0, 0.0))
    check(protocol.log[-4:] == [
        "protocol position: (7.0, 8.0, 9.0)",
        "plugin position: (7.0, 8.0, 9.0)",
        "protocol position: (0.0, 0.0, 0.0)",
        "plugin position: (0.0, 0.0, 0.0)",
    ], "both handles still work after binding")


async def main() -> None:
    """Run the disjoint and overlapping plugin requirement demonstrations."""
    await disjoint()
    await intersection()


if __name__ == "__main__":
    asyncio.run(main())
