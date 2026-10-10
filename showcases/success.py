"""Successful binding, constructor commands, events, and later requirements.

Run from the repository root with ``python -m showcases.success``.
"""

from gradys_core.capabilities.lifecycle import SimulationInitializationEvent
from gradys_core.capabilities.mobility import GotoCoords, PositionUpdate
from gradys_core.protocol import BaseProtocol

from .checks import check
from .mock_environment import MockEnvironment


class MoveProtocol(BaseProtocol):
    """Queue movement during construction and record lifecycle/position events.

    Attributes:
        notifications: Event descriptions in delivery order.
        move: Sending handle for this protocol's movement requirement.
    """

    def __init__(self, destination: tuple[float, float, float]) -> None:
        """Subscribe to initialization and positions, then queue the destination."""
        self.notifications: list[str] = []
        self.require_event(SimulationInitializationEvent).subscribe(self.on_start)
        self.require_event(PositionUpdate).subscribe(self.on_position)
        self.move = self.require_command(GotoCoords)
        self.move.send(GotoCoords(*destination))

    def on_start(self, event: SimulationInitializationEvent) -> None:
        """Record the environment's initialization notification."""
        self.notifications.append("started")

    def on_position(self, event: PositionUpdate) -> None:
        """Record a delivered position as a readable coordinate triple."""
        self.notifications.append(f"position: ({event.x}, {event.y}, {event.z})")


def main() -> None:
    """Check buffered construction requests and handles used after binding."""
    print("Binding: constructor requirements, events and commands")
    environment = MockEnvironment()
    protocol = MoveProtocol((1.0, 2.0, 3.0))

    environment.bind(protocol)
    check(environment.executed == [], "commands wait until start")
    environment.start()
    check(protocol.notifications == ["started", "position: (1.0, 2.0, 3.0)"],
          "start delivers lifecycle and position events")

    later_move = protocol.require_command(GotoCoords)
    later_move.send(GotoCoords(4.0, 5.0, 6.0))
    check(protocol.notifications[-1] == "position: (4.0, 5.0, 6.0)", "requirement after binding works")
    check(len(environment.executed) == 2, "every command executes")


if __name__ == "__main__":
    main()
