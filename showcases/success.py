"""Successful binding, constructor commands, events, and later requirements.

Run from the repository root with ``python -m showcases.success``.
"""

from gradys_core.capabilities.lifecycle import SimulationInitializationEvent
from gradys_core.capabilities.mobility import GotoCoords, PositionUpdate
from gradys_core.protocol import BaseProtocol

from .mock_environment import MockEnvironment


class MoveProtocol(BaseProtocol):
    def __init__(self, destination: tuple[float, float, float]) -> None:
        self.notifications: list[str] = []
        self.require_event(SimulationInitializationEvent).subscribe(self.on_start)
        self.require_event(PositionUpdate).subscribe(self.on_position)
        self.move = self.require_command(GotoCoords)
        self.move.send(GotoCoords(*destination))

    def on_start(self, event: SimulationInitializationEvent) -> None:
        self.notifications.append("started")

    def on_position(self, event: PositionUpdate) -> None:
        self.notifications.append(f"position: ({event.x}, {event.y}, {event.z})")


def main() -> None:
    environment = MockEnvironment()
    protocol = MoveProtocol((1.0, 2.0, 3.0))

    environment.bind(protocol)
    assert environment.executed == []  # Injection accepts the command; startup executes it.
    environment.start()
    assert protocol.notifications == ["started", "position: (1.0, 2.0, 3.0)"]

    # Requirements made after binding are checked immediately and remain usable.
    later_move = protocol.require_command(GotoCoords)
    later_move.send(GotoCoords(4.0, 5.0, 6.0))
    assert protocol.notifications[-1] == "position: (4.0, 5.0, 6.0)"

    for notification in protocol.notifications:
        print(notification)
    print(f"executed commands: {len(environment.executed)}")


if __name__ == "__main__":
    main()
