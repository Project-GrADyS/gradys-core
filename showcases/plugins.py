"""Plugins that receive a protocol and register their own requirements on it.

Run from the repository root with ``python -m showcases.plugins``.

A plugin has no connection of its own: every subscription and command goes through the
protocol it was given. Two cases are shown:

- disjoint: the plugin requires capabilities the protocol never asked for. They become
  the protocol's requirements, so a missing one rejects the whole protocol at binding.
- intersection: protocol and plugin require the same event and command. Requirements
  are deduplicated, both commands execute in send order, and every event reaches both
  subscribers regardless of whose command caused it.
"""

from gradys_core.capabilities.lifecycle import SimulationInitializationEvent
from gradys_core.capabilities.mobility import GotoCoords, PositionUpdate
from gradys_core.errors import ProtocolSetUpException
from gradys_core.protocol import BaseProtocol

from .checks import check
from .mock_environment import MockEnvironment


class MovementPlugin:
    """Add mobility requirements and position handling to a supplied protocol.

    Attributes:
        notifications: Position descriptions received by this plugin.
        move: Command handle obtained through the owning protocol.
    """

    def __init__(
        self,
        protocol: BaseProtocol,
        destination: tuple[float, float, float],
        log: list[str] | None = None,
    ) -> None:
        """Subscribe to positions and queue movement through the owning protocol.

        Args:
            protocol: Protocol whose requirements and connection the plugin uses.
            destination: Cartesian destination for the initial movement command.
            log: Optional shared list recording protocol/plugin delivery order.
        """
        self.notifications: list[str] = []
        self._log = log
        protocol.require_event(PositionUpdate).subscribe(self.on_position)
        self.move = protocol.require_command(GotoCoords)
        self.move.send(GotoCoords(*destination))

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
        """Queue initialization handling and construct a plugin on this protocol."""
        self.notifications: list[str] = []
        self.require_event(SimulationInitializationEvent).subscribe(self.on_start)
        self.plugin = MovementPlugin(self, (1.0, 2.0, 3.0))

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
        """Queue the protocol's subscriptions and movement before the plugin's."""
        self.notifications: list[str] = []
        self.log: list[str] = []  # Shared with the plugin to record delivery order.
        self.require_event(SimulationInitializationEvent).subscribe(self.on_start)
        self.require_event(PositionUpdate).subscribe(self.on_position)
        self.move = self.require_command(GotoCoords)
        self.move.send(GotoCoords(1.0, 2.0, 3.0))
        self.plugin = MovementPlugin(self, (4.0, 5.0, 6.0), self.log)

    def on_start(self, event: SimulationInitializationEvent) -> None:
        """Record initialization before the environment executes queued movement."""
        self.notifications.append("started")

    def on_position(self, event: PositionUpdate) -> None:
        """Record a position locally and in the shared delivery-order log."""
        notification = f"position: ({event.x}, {event.y}, {event.z})"
        self.notifications.append(notification)
        self.log.append(f"protocol {notification}")


def disjoint() -> None:
    """Check that plugin requirements join the protocol's binding requirements."""
    print("Disjoint: plugin adds mobility to a lifecycle-only protocol")
    environment = MockEnvironment()
    protocol = LifecycleProtocol()
    environment.bind(protocol)
    environment.start()
    check(protocol.notifications == ["started"], "protocol gets only its own events")
    check(protocol.plugin.notifications == ["position: (1.0, 2.0, 3.0)"], "plugin gets its events")
    check(environment.executed == [GotoCoords(1.0, 2.0, 3.0)], "plugin command executes")

    rejected = LifecycleProtocol()
    try:
        MockEnvironment(mobility=False).bind(rejected)
    except ProtocolSetUpException as error:
        check("GotoCoords" in error.message or "PositionUpdate" in error.message,
              "missing plugin capability rejects the protocol")
    else:
        raise AssertionError("Binding should reject the plugin's mobility requirements")

    try:
        rejected.require_event(SimulationInitializationEvent)
    except RuntimeError:
        check(True, "rejected protocol is unusable")
    else:
        raise AssertionError("A failed connection should reject the protocol's own requests")


def intersection() -> None:
    """Check shared capabilities, command order, and delivery to both subscribers."""
    print("\nIntersection: protocol and plugin share PositionUpdate and GotoCoords")
    environment = MockEnvironment()
    protocol = SharedMovementProtocol()
    environment.bind(protocol)
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

    protocol.move.send(GotoCoords(7.0, 8.0, 9.0))
    protocol.plugin.move.send(GotoCoords(0.0, 0.0, 0.0))
    check(protocol.log[-4:] == [
        "protocol position: (7.0, 8.0, 9.0)",
        "plugin position: (7.0, 8.0, 9.0)",
        "protocol position: (0.0, 0.0, 0.0)",
        "plugin position: (0.0, 0.0, 0.0)",
    ], "both handles still work after binding")


def main() -> None:
    """Run the disjoint and overlapping plugin requirement demonstrations."""
    disjoint()
    intersection()


if __name__ == "__main__":
    main()
